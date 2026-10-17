"""Phase-0-Spike: Kartenerkennung + OCR auf echten Handyfotos.

Für jedes Foto im Eingabeordner:

1. Bild laden (JPEG/PNG/HEIC), EXIF-Drehung korrigieren, auf max. 1280 px verkleinern.
2. OCR auf dem **ganzen Foto** (robust gegen Hände, Slabs, Hüllen, Screenshots).
3. Zusätzlich: Karte als Viereck suchen (Kanten → Konturen → Kartenformat 63×88 mm),
   entzerren (630×880 px) und dort Name (obere Zone) und Nummer (untere Zone) raten.
4. Messen, ob Soll-Name und Soll-Nummer **im erkannten Text vorkommen** – genau diese
   Information braucht der spätere Abgleich mit dem Katalog.
5. Debug-Bilder und einen Markdown-Bericht schreiben.

OCR: RapidOCR 3 mit dem mitgelieferten PP-OCRv6-Modell (Chinesisch, Englisch, Japanisch,
lateinische Schrift). Mit ``--rec-lang korean`` wird das koreanische PP-OCRv5-Modell
genutzt (wird beim ersten Start heruntergeladen).

Soll-Werte (optional) als CSV ``datei;name;nummer``.

Aufruf (aus ``backend/``)::

    uv run python scripts/spike_scanner.py \\
        --photos ../scanner_testset --expected ../scanner_testset/soll.csv \\
        --out ../docs/spikes/scanner.md
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps

CARD_RATIO = 63 / 88  # Breite / Höhe einer Standard-Pokémon-Karte
RATIO_TOLERANCE = 0.18
MIN_AREA_FRACTION = 0.08
MAX_SIDE = 1280
NORM_WIDTH, NORM_HEIGHT = 630, 880
NAME_ZONE = (0.0, 0.16)  # relativer Höhenbereich (oben)
NUMBER_ZONE = (0.82, 1.0)  # relativer Höhenbereich (unten)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

FRACTION_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)")  # 215/203
CODE_PATTERN = re.compile(r"\b([A-Z]{1,4}\d{0,3}[A-Z]?)\s*[- ]?\s*(\d{1,3})\b")  # SWSH123
NAME_STOPWORDS = {"KP", "HP", "PV", "BASIS", "BASIC", "PHASE", "STAGE", "VMAX", "V", "たね"}

UInt8Image = npt.NDArray[np.uint8]


@dataclass
class OcrLine:
    """Eine erkannte Textzeile mit Position (relativ zur Bildhöhe)."""

    text: str
    score: float
    top: float  # 0 = oben, 1 = unten
    height: float


@dataclass
class PhotoResult:
    """Ergebnis für ein einzelnes Foto."""

    file: str
    card_found: bool
    detected_ratio: float | None
    name_guess: str | None
    number_guess: str | None
    texts: list[str]
    detect_ms: float
    ocr_ms: float
    expected_name: str | None = None
    expected_number: str | None = None

    @property
    def name_ok(self) -> bool | None:
        """Geratener Name passt zum Soll (ohne Leerraum, Groß/Klein egal)."""
        if self.expected_name is None:
            return None
        guess = _compact(self.name_guess)
        expected = _compact(self.expected_name)
        return bool(guess) and (expected in guess or guess in expected)

    @property
    def number_ok(self) -> bool | None:
        """Geratene Nummer passt zum Soll."""
        if self.expected_number is None:
            return None
        return _normalize_number(self.number_guess) == _normalize_number(self.expected_number)

    @property
    def name_in_text(self) -> bool | None:
        """Soll-Name kommt irgendwo im erkannten Text vor."""
        if self.expected_name is None:
            return None
        expected = _compact(self.expected_name)
        return any(expected in _compact(text) for text in self.texts)

    @property
    def number_in_text(self) -> bool | None:
        """Soll-Nummer kommt irgendwo im erkannten Text vor."""
        if self.expected_number is None:
            return None
        return _number_occurs(self.expected_number, self.texts)


def _compact(value: str | None) -> str:
    """Entfernt Leerraum und vereinheitlicht Groß/Klein – OCR verschluckt oft Leerzeichen."""
    return re.sub(r"\s+", "", value or "").casefold()


def _normalize_number(value: str | None) -> str:
    """``"015/203"`` → ``"15"``; ``"SWSH 050"`` → ``"SWSH050"``."""
    if not value:
        return ""
    head = re.split(r"\s*/\s*", value.strip())[0]
    return head.lstrip("0").upper().replace(" ", "")


def _number_occurs(expected: str, texts: list[str]) -> bool:
    """Prüft, ob eine Kartennummer (Bruch wie ``110/098`` oder einzeln wie ``007``) vorkommt."""
    if fraction := FRACTION_PATTERN.search(expected):
        want = (fraction.group(1).lstrip("0"), fraction.group(2).lstrip("0"))
        return any(
            (match.group(1).lstrip("0"), match.group(2).lstrip("0")) == want
            for text in texts
            for match in FRACTION_PATTERN.finditer(text.replace("O", "0"))
        )
    single = re.compile(rf"(?<!\d)0*{re.escape(expected.lstrip('0'))}(?!\d)")
    return any(single.search(text) for text in texts)


# --------------------------------------------------------------------------- Laden


def load_image(path: Path) -> UInt8Image:
    """Lädt ein Foto inkl. HEIC, korrigiert die EXIF-Drehung und verkleinert es (BGR)."""
    if path.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener  # noqa: PLC0415 – nur bei Bedarf

        register_heif_opener()
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    rgb = np.asarray(image, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).astype(np.uint8)


# --------------------------------------------------------------------- Erkennung


def _order_corners(points: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """Sortiert 4 Punkte: oben-links, oben-rechts, unten-rechts, unten-links."""
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).ravel()
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(diffs)],
            points[np.argmax(sums)],
            points[np.argmax(diffs)],
        ],
        dtype=np.float32,
    )


def _quad_ratio(corners: npt.NDArray[np.float32]) -> float:
    """Verhältnis Breite/Höhe eines geordneten Vierecks (immer ≤ 1, hochkant gedacht)."""
    top_left, top_right, bottom_right, bottom_left = corners
    width = (np.linalg.norm(top_right - top_left) + np.linalg.norm(bottom_right - bottom_left)) / 2
    height = (np.linalg.norm(bottom_left - top_left) + np.linalg.norm(bottom_right - top_right)) / 2
    short, long_ = sorted((float(width), float(height)))
    return short / long_ if long_ else 0.0


def find_card_quad(image: UInt8Image) -> npt.NDArray[np.float32] | None:
    """Sucht das größte Viereck mit Kartenformat. Gibt geordnete Ecken zurück oder ``None``."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    min_area = MIN_AREA_FRACTION * image.shape[0] * image.shape[1]

    # Zwei Kantenstrategien: Canny (kontrastreich) und adaptive Schwelle (schwaches Licht).
    edge_maps = [
        cv2.dilate(cv2.Canny(blurred, 40, 140), np.ones((5, 5), np.uint8), iterations=2),
        cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 7
        ),
    ]
    best: tuple[float, npt.NDArray[np.float32]] | None = None
    for edges in edge_maps:
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
            area = cv2.contourArea(contour)
            if area < min_area:
                break
            perimeter = cv2.arcLength(contour, closed=True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, closed=True)
            if len(approx) == 4:
                corners = _order_corners(approx.reshape(4, 2).astype(np.float32))
            else:  # Fallback: kleinstes umschließendes Rechteck
                corners = _order_corners(cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32))
            if abs(_quad_ratio(corners) - CARD_RATIO) <= RATIO_TOLERANCE and (
                best is None or area > best[0]
            ):
                best = (area, corners)
    return best[1] if best else None


def rectify(image: UInt8Image, corners: npt.NDArray[np.float32]) -> UInt8Image:
    """Entzerrt die Karte auf das Normformat (hochkant)."""
    top_left, top_right, _, bottom_left = corners
    if np.linalg.norm(top_right - top_left) > np.linalg.norm(bottom_left - top_left):
        corners = np.roll(corners, -1, axis=0)  # Karte liegt quer → um 90° drehen
    target = np.array(
        [[0, 0], [NORM_WIDTH - 1, 0], [NORM_WIDTH - 1, NORM_HEIGHT - 1], [0, NORM_HEIGHT - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (NORM_WIDTH, NORM_HEIGHT)).astype(np.uint8)


# --------------------------------------------------------------------------- OCR


class Ocr:
    """Dünne, typisierte Hülle um RapidOCR 3 (lädt das Modell einmalig).

    Args:
        rec_lang: ``None`` für das mitgelieferte Mehrsprachen-Modell (CH/EN/JP/Latein),
            sonst ein ``LangRec``-Wert wie ``"korean"`` (Modell wird heruntergeladen).
    """

    def __init__(self, rec_lang: str | None = None) -> None:
        from rapidocr import (  # noqa: PLC0415 – schwerer Import
            LangRec,
            ModelType,
            OCRVersion,
            RapidOCR,
        )

        params: dict[str, Any] = {"Global.log_level": "warning"}
        if rec_lang:
            # Sprachspezifische Modelle gibt es nur als PP-OCRv5 „mobile“. Achtung: RapidOCR
            # lädt das Modell erst beim ersten erkannten Text – Fehler zeigen sich erst dann.
            params |= {
                "Rec.lang_type": LangRec(rec_lang),
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            }
        self._engine: Any = RapidOCR(params=params)

    def read(self, image: UInt8Image) -> list[OcrLine]:
        """Erkennt alle Textzeilen; Positionen relativ zur Bildhöhe."""
        result = self._engine(image)
        if result.boxes is None or result.txts is None:
            return []
        image_height = float(image.shape[0])
        lines: list[OcrLine] = []
        for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
            ys = [float(point[1]) for point in box]
            lines.append(
                OcrLine(
                    text=str(text).strip(),
                    score=float(score),
                    top=min(ys) / image_height,
                    height=(max(ys) - min(ys)) / image_height,
                )
            )
        return lines


def guess_name(lines: list[OcrLine]) -> str | None:
    """Größte Textzeile in der oberen Zone der entzerrten Karte, ohne KP und Stufen-Wörter."""
    candidates = [
        line
        for line in lines
        if NAME_ZONE[0] <= line.top <= NAME_ZONE[1]
        and re.search(r"[^\W\d_]{2,}", line.text)
        and line.text.upper() not in NAME_STOPWORDS
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda line: line.height)
    return re.sub(r"\s*(KP|HP|PV)\s*\d+.*$", "", best.text, flags=re.IGNORECASE).strip()


def guess_number(card_lines: list[OcrLine], photo_lines: list[OcrLine]) -> str | None:
    """Kartennummer: zuerst untere Zone der entzerrten Karte, sonst irgendwo im Foto."""
    bottom = sorted(
        (line for line in card_lines if line.top >= NUMBER_ZONE[0]),
        key=lambda item: item.top,
        reverse=True,
    )
    # Bei Bruchnummern verwechselt OCR gern „O“ mit „0“.
    for line in [*bottom, *photo_lines]:
        if match := FRACTION_PATTERN.search(line.text.replace("O", "0")):
            return f"{match.group(1)}/{match.group(2)}"
    for line in bottom:
        if match := CODE_PATTERN.search(line.text):
            return match.group(0).replace(" ", "")
    return None


# ------------------------------------------------------------------------ Ablauf


def load_expected(path: Path | None) -> dict[str, tuple[str, str]]:
    """Liest Soll-Werte: ``datei;name;nummer`` (Kopfzeile optional)."""
    if path is None:
        return {}
    expected: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter=";"):
            if len(row) >= 3 and row[0].lower() != "datei":
                expected[row[0].strip()] = (row[1].strip(), row[2].strip())
    return expected


def process_photo(path: Path, ocr: Ocr, debug_dir: Path) -> PhotoResult:
    """Führt die komplette Pipeline für ein Foto aus und schreibt Debug-Bilder."""
    image = load_image(path)

    start = time.perf_counter()
    corners = find_card_quad(image)
    detect_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    photo_lines = ocr.read(image)
    card_lines: list[OcrLine] = []
    if corners is not None:
        outlined = image.copy()
        cv2.polylines(
            outlined, [corners.astype(np.int32)], isClosed=True, color=(0, 255, 0), thickness=3
        )
        cv2.imwrite(str(debug_dir / f"{path.stem}_kontur.jpg"), outlined)
        card = rectify(image, corners)
        cv2.imwrite(str(debug_dir / f"{path.stem}_karte.jpg"), card)
        card_lines = ocr.read(card)
    else:
        cv2.imwrite(str(debug_dir / f"{path.stem}_nicht_gefunden.jpg"), image)
    ocr_ms = (time.perf_counter() - start) * 1000

    return PhotoResult(
        file=path.name,
        card_found=corners is not None,
        detected_ratio=round(_quad_ratio(corners), 3) if corners is not None else None,
        name_guess=guess_name(card_lines),
        number_guess=guess_number(card_lines, photo_lines),
        texts=[line.text for line in [*photo_lines, *card_lines]],
        detect_ms=detect_ms,
        ocr_ms=ocr_ms,
    )


def _rate(values: list[bool | None]) -> str:
    known = [value for value in values if value is not None]
    if not known:
        return "– (keine Soll-Werte)"
    return f"{sum(known)}/{len(known)} ({100 * sum(known) / len(known):.0f} %)"


def _mark(value: bool | None) -> str:
    return {True: "✅", False: "❌", None: "–"}[value]


def render_report(results: list[PhotoResult], rec_lang: str | None) -> str:
    """Markdown-Bericht mit Zusammenfassung, Einzelergebnissen und Rohtexten."""
    total = len(results)
    avg_ms = sum(r.detect_ms + r.ocr_ms for r in results) / total if total else 0.0
    lines = [
        "# Spike: Scanner\n",
        f"OCR-Modell: {rec_lang or 'PP-OCRv6 (mitgeliefert, CH/EN/JP/Latein)'}\n",
        "## Zusammenfassung\n",
        f"- Fotos: {total}",
        f"- Kartenkontur gefunden: {sum(r.card_found for r in results)}/{total} "
        "(sagt nichts darüber, ob der Ausschnitt stimmt – siehe Debug-Bilder)",
        f"- **Soll-Name im erkannten Text:** {_rate([r.name_in_text for r in results])}",
        f"- **Soll-Nummer im erkannten Text:** {_rate([r.number_in_text for r in results])}",
        f"- Name automatisch geraten (Zonen-Heuristik): {_rate([r.name_ok for r in results])}",
        f"- Nummer automatisch geraten: {_rate([r.number_ok for r in results])}",
        f"- Ø Zeit pro Foto (Erkennung + OCR): {avg_ms:.0f} ms",
        "",
        "## Einzelergebnisse\n",
        "| Datei | Soll | Name im Text | Nummer im Text | Name geraten | Nummer geraten "
        "| Kontur | ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        expected = f"{r.expected_name} · {r.expected_number}" if r.expected_name else "–"
        lines.append(
            f"| {r.file} | {expected} | {_mark(r.name_in_text)} | {_mark(r.number_in_text)} "
            f"| {r.name_guess or '–'} | {r.number_guess or '–'} "
            f"| {r.detected_ratio or '–'} | {r.detect_ms + r.ocr_ms:.0f} |"
        )
    lines += ["", "## Erkannter Rohtext (ganzes Foto + Kartenausschnitt)\n"]
    for r in results:
        joined = " · ".join(text.replace("|", "/") for text in r.texts[:40])
        lines.append(f"- **{r.file}:** {joined or '–'}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--photos", type=Path, required=True, help="Ordner mit Testfotos")
    parser.add_argument("--out", type=Path, default=Path("../docs/spikes/scanner.md"))
    parser.add_argument("--expected", type=Path, help="CSV mit Soll-Werten (datei;name;nummer)")
    parser.add_argument(
        "--rec-lang", help="Anderes Erkennungsmodell, z. B. 'korean' (wird heruntergeladen)"
    )
    args = parser.parse_args()
    photos_dir: Path = args.photos
    out_path: Path = args.out
    rec_lang: str | None = args.rec_lang

    photos = sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not photos:
        parser.error(f"Keine Fotos in {photos_dir} gefunden.")
    debug_dir = out_path.parent / "scanner_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    expected = load_expected(args.expected)

    ocr = Ocr(rec_lang)
    results: list[PhotoResult] = []
    for index, photo in enumerate(photos, start=1):
        result = process_photo(photo, ocr, debug_dir)
        if photo.name in expected:
            result.expected_name, result.expected_number = expected[photo.name]
        results.append(result)
        print(
            f"[{index}/{len(photos)}] {photo.name}: "
            f"Name im Text {_mark(result.name_in_text)} · Nummer im Text "
            f"{_mark(result.number_in_text)} · geraten: {result.number_guess}"
        )

    out_path.write_text(render_report(results, rec_lang), encoding="utf-8")
    print(f"Bericht geschrieben: {out_path} (Debug-Bilder: {debug_dir})")


if __name__ == "__main__":
    main()
