"""Phase-0-Spike: Kartenerkennung + OCR auf echten Handyfotos.

Für jedes Foto im Eingabeordner:

1. Bild laden (JPEG/PNG/HEIC), EXIF-Drehung korrigieren, auf max. 1280 px verkleinern.
2. Karte als Viereck finden (Kanten → Konturen → Viereck mit Kartenformat 63×88 mm).
3. Perspektive entzerren auf ein Normbild (630×880 px).
4. OCR (RapidOCR) auf dem Normbild; daraus Name (obere Zone) und Kartennummer
   (untere Zone) ableiten.
5. Debug-Bilder (gefundene Kontur, entzerrte Karte) und einen Markdown-Bericht schreiben.

Optional kann eine CSV mit Soll-Werten übergeben werden (``datei;name;nummer``),
dann berechnet der Bericht die Trefferquote.

Aufruf (aus ``backend/``)::

    uv run --group spike python scripts/spike_scanner.py \\
        --photos ../scanner_testset --out ../docs/spikes/scanner.md
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

NUMBER_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b"),  # 215/203
    re.compile(r"\b([A-Z]{1,4}\d{0,3}[A-Z]?)\s*[- ]?\s*(\d{1,3})\b"),  # SWSH123, SV 012
)
NAME_STOPWORDS = {"KP", "HP", "PV", "BASIS", "BASIC", "PHASE", "STAGE", "VMAX", "V"}

UInt8Image = npt.NDArray[np.uint8]


@dataclass
class OcrLine:
    """Eine erkannte Textzeile mit Position (relativ zum Normbild)."""

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
    ocr_lines: int
    detect_ms: float
    ocr_ms: float
    expected_name: str | None = None
    expected_number: str | None = None

    @property
    def name_ok(self) -> bool | None:
        if self.expected_name is None:
            return None
        # OCR verschluckt oft Leerzeichen („NachtaraVMAX“) – daher ohne Leerraum vergleichen.
        guess = _compact(self.name_guess)
        expected = _compact(self.expected_name)
        return expected in guess or (bool(guess) and guess in expected)

    @property
    def number_ok(self) -> bool | None:
        if self.expected_number is None:
            return None
        return _normalize_number(self.number_guess) == _normalize_number(self.expected_number)


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _normalize_number(value: str | None) -> str:
    if not value:
        return ""
    head = re.split(r"\s*/\s*", value.strip())[0]
    return head.lstrip("0").upper().replace(" ", "")


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
    """Dünne, typisierte Hülle um RapidOCR (lädt das Modell einmalig)."""

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415 – schwerer Import

        self._engine: Any = RapidOCR()

    def read(self, card: UInt8Image) -> list[OcrLine]:
        result, _ = self._engine(card)
        lines: list[OcrLine] = []
        for box, text, score in result or []:
            ys = [point[1] for point in box]
            lines.append(
                OcrLine(
                    text=str(text).strip(),
                    score=float(score),
                    top=min(ys) / NORM_HEIGHT,
                    height=(max(ys) - min(ys)) / NORM_HEIGHT,
                )
            )
        return lines


def guess_name(lines: list[OcrLine]) -> str | None:
    """Größte Textzeile in der oberen Zone, ohne KP-Angaben und Stufen-Wörter."""
    candidates = [
        line
        for line in lines
        if NAME_ZONE[0] <= line.top <= NAME_ZONE[1]
        and re.search(r"[^\W\d_]{3,}", line.text)
        and line.text.upper() not in NAME_STOPWORDS
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda line: line.height)
    return re.sub(r"\s*(KP|HP|PV)\s*\d+.*$", "", best.text, flags=re.IGNORECASE).strip()


def guess_number(lines: list[OcrLine]) -> str | None:
    """Erste plausible Kartennummer in der unteren Zone (z. B. ``215/203``)."""
    bottom = sorted(
        (line for line in lines if line.top >= NUMBER_ZONE[0]),
        key=lambda item: item.top,
        reverse=True,
    )
    fraction_pattern, code_pattern = NUMBER_PATTERNS
    for line in bottom:
        # Bei Bruchnummern verwechselt OCR gern „O“ mit „0“.
        if match := fraction_pattern.search(line.text.replace("O", "0")):
            return match.group(0).replace(" ", "")
    for line in bottom:
        if match := code_pattern.search(line.text):
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

    if corners is None:
        cv2.imwrite(str(debug_dir / f"{path.stem}_nicht_gefunden.jpg"), image)
        return PhotoResult(path.name, False, None, None, None, 0, detect_ms, 0.0)

    outlined = image.copy()
    cv2.polylines(
        outlined, [corners.astype(np.int32)], isClosed=True, color=(0, 255, 0), thickness=3
    )
    cv2.imwrite(str(debug_dir / f"{path.stem}_kontur.jpg"), outlined)
    card = rectify(image, corners)
    cv2.imwrite(str(debug_dir / f"{path.stem}_karte.jpg"), card)

    start = time.perf_counter()
    lines = ocr.read(card)
    ocr_ms = (time.perf_counter() - start) * 1000
    return PhotoResult(
        file=path.name,
        card_found=True,
        detected_ratio=round(_quad_ratio(corners), 3),
        name_guess=guess_name(lines),
        number_guess=guess_number(lines),
        ocr_lines=len(lines),
        detect_ms=detect_ms,
        ocr_ms=ocr_ms,
    )


def _rate(values: list[bool | None]) -> str:
    known = [value for value in values if value is not None]
    if not known:
        return "– (keine Soll-Werte)"
    return f"{sum(known)}/{len(known)} ({100 * sum(known) / len(known):.0f} %)"


def render_report(results: list[PhotoResult]) -> str:
    found = sum(result.card_found for result in results)
    total = len(results)
    avg_ms = sum(r.detect_ms + r.ocr_ms for r in results) / total if total else 0.0
    lines = [
        "# Spike: Scanner\n",
        "## Zusammenfassung\n",
        f"- Fotos: {total}",
        f"- Karte gefunden: {found}/{total}",
        f"- Name korrekt: {_rate([r.name_ok for r in results])}",
        f"- Nummer korrekt: {_rate([r.number_ok for r in results])}",
        f"- Ø Zeit pro Foto (Erkennung + OCR): {avg_ms:.0f} ms",
        "",
        "## Einzelergebnisse\n",
        "| Datei | Karte | Verhältnis | Name (erkannt) | Nummer (erkannt) | Soll "
        "| OCR-Zeilen | ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        expected = f"{r.expected_name} · {r.expected_number}" if r.expected_name else "–"
        lines.append(
            f"| {r.file} | {'✅' if r.card_found else '❌'} | {r.detected_ratio or '–'} "
            f"| {r.name_guess or '–'} | {r.number_guess or '–'} | {expected} "
            f"| {r.ocr_lines} | {r.detect_ms + r.ocr_ms:.0f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--photos", type=Path, required=True, help="Ordner mit Testfotos")
    parser.add_argument("--out", type=Path, default=Path("../docs/spikes/scanner.md"))
    parser.add_argument("--expected", type=Path, help="CSV mit Soll-Werten (datei;name;nummer)")
    args = parser.parse_args()
    photos_dir: Path = args.photos
    out_path: Path = args.out

    photos = sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not photos:
        parser.error(f"Keine Fotos in {photos_dir} gefunden.")
    debug_dir = out_path.parent / "scanner_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    expected = load_expected(args.expected)

    ocr = Ocr()
    results: list[PhotoResult] = []
    for index, photo in enumerate(photos, start=1):
        result = process_photo(photo, ocr, debug_dir)
        if photo.name in expected:
            result.expected_name, result.expected_number = expected[photo.name]
        results.append(result)
        print(f"[{index}/{len(photos)}] {photo.name}: {result.name_guess} · {result.number_guess}")

    out_path.write_text(render_report(results), encoding="utf-8")
    print(f"Bericht geschrieben: {out_path} (Debug-Bilder: {debug_dir})")


if __name__ == "__main__":
    main()
