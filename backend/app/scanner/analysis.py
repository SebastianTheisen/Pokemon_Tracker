"""Ein Foto auswerten: OCR, Textmerkmale, Kartenausschnitt, Bildmerkmale (ohne Datenbank).

Reihenfolge (Plan 5.6, Schritte 2–4):

1. OCR auf dem **ganzen** Bild (robust gegen Hände, Slabs, Hüllen, Screenshots).
2. Kartenausschnitt suchen. Er dient als Referenzbild und – wenn auf dem ganzen Bild keine
   Nummer lesbar war – für eine zweite OCR (kleine Karten im Bild werden so größer).
   Ist die Karte klein (Binder-Zellen) und das Ergebnis unsicher, liest der Service sie
   einmal vergrößert nach (:func:`add_enlarged_pass`): Die Nummer ist dort nur 10–15 Pixel
   hoch. Erst bei Bedarf – meist entscheidet schon der Bildabgleich, und die zweite OCR
   kostet je Karte gut eine Sekunde.
3. Optional ein Durchlauf mit dem koreanischen Modell.
4. SIFT-Merkmale des ganzen Bildes für den Bildabgleich.

Alles hier ist CPU-lastig und blockierend; der Service ruft es in einem Thread auf.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np
import structlog

from app.scanner.imaging import UInt8Image, card_crop
from app.scanner.matching import ImageFeatures, extract_features
from app.scanner.ocr import OcrLine, TextReader
from app.scanner.text import TextFeatures, extract_text_features

log = structlog.get_logger(__name__)

# Unterhalb dieser Kantenlänge (Pixel) ist die Kartennummer für die OCR meist zu klein.
SMALL_CARD_SIDE = 900
UPSCALE_FACTOR = 2.0


@dataclass(frozen=True)
class PhotoAnalysis:
    """Ergebnis der Auswertung eines Bildes."""

    lines: tuple[OcrLine, ...]
    text: TextFeatures
    features: ImageFeatures
    crop: UInt8Image | None
    korean_done: bool = False

    def reference_image(self, image: UInt8Image) -> UInt8Image:
        """Bild für ein eigenes Referenzbild: Kartenausschnitt, sonst das ganze Bild."""
        return self.crop if self.crop is not None else image


def analyze_photo(
    image: UInt8Image,
    reader: TextReader,
    *,
    korean: bool = False,
    find_crop: bool = True,
) -> PhotoAnalysis:
    """Wertet ein Bild aus. ``find_crop=False`` für Bilder, die schon eine Karte sind
    (Binder-Zellen)."""
    lines = list(reader.read(image))
    crop = card_crop(image) if find_crop else None
    text = extract_text_features(lines)
    if crop is not None and not text.numbers:
        lines += reader.read(crop)
        text = extract_text_features(lines)
    analysis = PhotoAnalysis(
        lines=tuple(lines),
        text=text,
        features=extract_features(image),
        crop=crop,
    )
    return add_korean_pass(analysis, image, reader) if korean else analysis


def add_enlarged_pass(
    analysis: PhotoAnalysis, image: UInt8Image, reader: TextReader
) -> PhotoAnalysis | None:
    """Kleine Karte ohne gelesene Nummer vergrößert nachlesen; ``None``, wenn das nichts
    bringen kann (Nummer schon gelesen oder Karte groß genug)."""
    card = analysis.crop if analysis.crop is not None else image
    if analysis.text.numbers or max(card.shape[:2]) >= SMALL_CARD_SIDE:
        return None
    lines = (*analysis.lines, *reader.read(upscale(card)))
    return replace(analysis, lines=lines, text=extract_text_features(lines))


def upscale(image: UInt8Image, factor: float = UPSCALE_FACTOR) -> UInt8Image:
    """Bild für die OCR vergrößern (bikubisch – schärfere Ziffern als linear)."""
    enlarged = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    return enlarged.astype(np.uint8)


def add_korean_pass(
    analysis: PhotoAnalysis, image: UInt8Image, reader: TextReader
) -> PhotoAnalysis:
    """Zweiter Durchlauf mit dem koreanischen Modell. Fehler (z. B. Modell-Download)
    brechen den Scan nicht ab – dann bleibt es beim ersten Durchlauf."""
    if analysis.korean_done:
        return analysis
    try:
        korean_lines = reader.read(image, korean=True)
    except Exception:  # Fremdbibliothek: jeder Fehler wird nur protokolliert
        log.warning("scanner.korean_ocr_failed", exc_info=True)
        return replace(analysis, korean_done=True)
    lines = (*analysis.lines, *korean_lines)
    return replace(analysis, lines=lines, text=extract_text_features(lines), korean_done=True)
