"""Phase-0-Spike: Identifikation per Bildabgleich gegen TCGdex-Katalogbilder.

Für jedes Testfoto mit Soll-Werten (``scanner_testset/soll.csv``):

1. Kandidaten im TCGdex-Katalog suchen – alle Karten mit passendem Namen in der Sprache
   der Karte (z. B. alle „ルギアV“-Drucke). Das sind bewusst *schwere* Gegner: gleiche
   Figur, andere Sets/Artworks.
2. Katalogbilder der Kandidaten laden (``high.webp``, Cache unter ``docs/spikes/katalog_cache``).
3. SIFT-Merkmale von Foto und Katalogbild vergleichen; Score = Anzahl RANSAC-Inlier
   (robust gegen Perspektive, Hände, Hüllen – kein Kartenausschnitt nötig).
4. Prüfen, auf welchem Rang die richtige Karte (Soll-Nummer) landet.

Aufruf (aus ``backend/``)::

    uv run python scripts/spike_image_match.py \\
        --photos ../scanner_testset --expected ../scanner_testset/soll.csv \\
        --out ../docs/spikes/bildabgleich.md
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import httpx
import numpy as np
import numpy.typing as npt
from PIL import Image

from scripts.spike_scanner import load_image

TCGDEX_BASE = "https://api.tcgdex.net/v2"
USER_AGENT = "PokemonTracker-Spike/0.1 (private Sammel-App, geringe Last)"
MAX_CANDIDATES = 40
RATIO_TEST = 0.75
MIN_GOOD_MATCHES = 8
NAME_SUFFIXES = re.compile(r"\s*(ex|EX|GX|V|VMAX|VSTAR|V-UNION)$")

Features = tuple[tuple[cv2.KeyPoint, ...], cv2.typing.MatLike | None]


@dataclass
class Expected:
    """Soll-Werte eines Testfotos."""

    file: str
    name: str
    number: str
    language: str


@dataclass
class Candidate:
    """Eine Katalogkarte als Kandidat."""

    card_id: str
    local_id: str
    name: str
    image_url: str | None
    score: int = 0


@dataclass
class MatchResult:
    """Ergebnis für ein Testfoto."""

    expected: Expected
    candidates: list[Candidate] = field(default_factory=list)
    note: str = ""
    duration_ms: float = 0.0

    @property
    def ranked(self) -> list[Candidate]:
        return sorted(self.candidates, key=lambda c: c.score, reverse=True)

    @property
    def correct_rank(self) -> int | None:
        """1-basierter Rang der richtigen Karte, ``None`` wenn nicht unter den Kandidaten."""
        want = _number_head(self.expected.number)
        for rank, candidate in enumerate(self.ranked, start=1):
            if _number_head(candidate.local_id) == want:
                return rank
        return None


def _number_head(value: str) -> str:
    """``"110/098"`` → ``"110"``, ``"007"`` → ``"7"``, ``"SV050"`` → ``"SV50"``."""
    head = value.split("/", maxsplit=1)[0].strip().upper()
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", head)


def load_expected(path: Path) -> list[Expected]:
    """Liest ``datei;name;nummer;sprache`` (Kopfzeile erforderlich)."""
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    return [
        Expected(row["datei"], row["name"], row["nummer"], row.get("sprache") or "de")
        for row in rows
        if row.get("datei")
    ]


# ------------------------------------------------------------------- Katalog


def find_candidates(client: httpx.Client, expected: Expected) -> list[Candidate]:
    """Sucht Karten mit passendem Namen; ohne Treffer zweiter Versuch ohne Zusatz (ex/V …)."""
    names = [expected.name]
    if (base := NAME_SUFFIXES.sub("", expected.name)) != expected.name:
        names.append(base)
    for name in names:
        response = client.get(f"{TCGDEX_BASE}/{expected.language}/cards", params={"name": name})
        if response.is_success and (cards := response.json()):
            return [
                Candidate(
                    card_id=card["id"],
                    local_id=str(card.get("localId", "")),
                    name=card.get("name", ""),
                    image_url=card.get("image"),
                )
                for card in cards[:MAX_CANDIDATES]
            ]
    return []


def load_catalog_image(client: httpx.Client, url: str, cache_dir: Path) -> npt.NDArray[np.uint8]:
    """Lädt ein Katalogbild (mit Datei-Cache) als BGR-Array."""
    cache_file = cache_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", url.split("//", 1)[-1]) + ".webp")
    if cache_file.exists():
        data = cache_file.read_bytes()
    else:
        response = client.get(f"{url}/high.webp")
        response.raise_for_status()
        data = response.content
        cache_file.write_bytes(data)
    with Image.open(io.BytesIO(data)) as raw:
        rgb = np.asarray(raw.convert("RGB"), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).astype(np.uint8)


# ----------------------------------------------------------------- Abgleich


def extract_features(image: npt.NDArray[np.uint8], n_features: int = 3000) -> Features:
    """SIFT-Schlüsselpunkte und -Deskriptoren (Graustufen)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    keypoints, descriptors = cv2.SIFT.create(nfeatures=n_features).detectAndCompute(gray, None)
    return tuple(keypoints), descriptors


def match_score(photo: Features, catalog: Features) -> int:
    """Anzahl geometrisch konsistenter Übereinstimmungen (RANSAC-Inlier)."""
    (photo_kp, photo_desc), (cat_kp, cat_desc) = photo, catalog
    if photo_desc is None or cat_desc is None or len(cat_kp) < 2:
        return 0
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(photo_desc, cat_desc, k=2)
    good = [
        first
        for pair in pairs
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < RATIO_TEST * second.distance
    ]
    if len(good) < MIN_GOOD_MATCHES:
        return 0
    src = np.array([photo_kp[m.queryIdx].pt for m in good], dtype=np.float32)
    dst = np.array([cat_kp[m.trainIdx].pt for m in good], dtype=np.float32)
    _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    return int(mask.sum()) if mask is not None else 0


def evaluate_photo(
    client: httpx.Client, expected: Expected, photos_dir: Path, cache_dir: Path
) -> MatchResult:
    """Kandidaten suchen, Bilder laden, abgleichen."""
    result = MatchResult(expected)
    start = time.perf_counter()
    result.candidates = find_candidates(client, expected)
    if not result.candidates:
        result.note = "keine Kandidaten im Katalog gefunden"
        return result

    photo_features = extract_features(load_image(photos_dir / expected.file))
    missing_images = 0
    for candidate in result.candidates:
        if not candidate.image_url:
            missing_images += 1
            continue
        try:
            catalog_image = load_catalog_image(client, candidate.image_url, cache_dir)
        except httpx.HTTPError:
            missing_images += 1
            continue
        candidate.score = match_score(photo_features, extract_features(catalog_image))
    if missing_images:
        result.note = f"{missing_images} Kandidaten ohne Bild"
    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


# ------------------------------------------------------------------- Bericht


def render_report(results: list[MatchResult]) -> str:
    """Markdown-Bericht."""
    with_rank = [r.correct_rank for r in results]
    top1 = sum(rank == 1 for rank in with_rank)
    top5 = sum(rank is not None and rank <= 5 for rank in with_rank)
    in_catalog = sum(rank is not None for rank in with_rank)
    lines = [
        "# Spike: Bildabgleich gegen TCGdex-Katalog\n",
        "## Zusammenfassung\n",
        f"- Fotos: {len(results)}",
        f"- Richtige Karte unter den Kandidaten (Katalogabdeckung): {in_catalog}/{len(results)}",
        f"- **Top-1 (richtige Karte auf Platz 1):** {top1}/{len(results)}",
        f"- Top-5: {top5}/{len(results)}",
        "",
        "## Einzelergebnisse\n",
        "| Datei | Soll | Sprache | Kandidaten | Rang richtig | Platz 1 (Score) "
        "| Platz 2 (Score) | Hinweis | ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ranked = r.ranked
        first = f"{ranked[0].card_id} ({ranked[0].score})" if ranked else "–"
        second = f"{ranked[1].card_id} ({ranked[1].score})" if len(ranked) > 1 else "–"
        lines.append(
            f"| {r.expected.file} | {r.expected.name} · {r.expected.number} "
            f"| {r.expected.language} | {len(r.candidates)} | {r.correct_rank or '–'} "
            f"| {first} | {second} | {r.note or '–'} | {r.duration_ms:.0f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("../docs/spikes/bildabgleich.md"))
    args = parser.parse_args()
    photos_dir: Path = args.photos
    out_path: Path = args.out

    cache_dir = out_path.parent / "katalog_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: list[MatchResult] = []
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for expected in load_expected(args.expected):
            try:
                result = evaluate_photo(client, expected, photos_dir, cache_dir)
            except httpx.HTTPError as exc:
                result = MatchResult(expected, note=f"Fehler: {exc!r}")
            results.append(result)
            print(
                f"{expected.file}: {len(result.candidates)} Kandidaten, "
                f"Rang richtig: {result.correct_rank} {result.note}"
            )
    out_path.write_text(render_report(results), encoding="utf-8")
    print(f"Bericht geschrieben: {out_path}")


if __name__ == "__main__":
    main()
