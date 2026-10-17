"""Texterkennung: dünne, typisierte Hülle um RapidOCR 3.

* Standard: das mitgelieferte PP-OCRv6-Modell (Chinesisch, Englisch, Japanisch, Latein).
* Koreanisch: eigenes Modell ``korean_PP-OCRv5`` (mobile). Es wird beim ersten Gebrauch
  heruntergeladen (im Docker-Image schon beim Bauen) und nur bei Bedarf genutzt.

Die Erkennung ist CPU-lastig und blockierend – Aufrufer führen sie in einem Thread aus
(siehe :mod:`app.services.scan`).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from app.scanner.imaging import UInt8Image


@dataclass(frozen=True)
class OcrLine:
    """Eine erkannte Textzeile. Positionen relativ zur Bildgröße (0 = oben/links)."""

    text: str
    score: float = 1.0
    top: float = 0.0
    left: float = 0.0
    height: float = 0.0
    width: float = 0.0


class TextReader(Protocol):
    """Schnittstelle der Texterkennung (in Tests durch eine Attrappe ersetzt)."""

    def read(self, image: UInt8Image, *, korean: bool = False) -> list[OcrLine]:
        """Erkennt alle Textzeilen; ``korean=True`` nutzt das koreanische Modell."""
        ...


class RapidOcrReader:
    """RapidOCR mit lazily geladenen Modellen; Aufrufe sind gegeneinander gesperrt."""

    def __init__(self) -> None:
        self._engines: dict[bool, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _create(*, korean: bool) -> Any:
        from rapidocr import (  # noqa: PLC0415 – schwerer Import, erst bei Bedarf
            LangRec,
            ModelType,
            OCRVersion,
            RapidOCR,
        )

        params: dict[str, Any] = {"Global.log_level": "warning"}
        if korean:
            # Sprachspezifische Modelle gibt es nur als PP-OCRv5 „mobile“. Achtung: RapidOCR
            # lädt das Modell erst beim ersten erkannten Text – Fehler zeigen sich erst dann.
            params |= {
                "Rec.lang_type": LangRec.KOREAN,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            }
        return RapidOCR(params=params)

    def read(self, image: UInt8Image, *, korean: bool = False) -> list[OcrLine]:
        with self._lock:
            if korean not in self._engines:
                self._engines[korean] = self._create(korean=korean)
            result = self._engines[korean](image)
        if result.boxes is None or result.txts is None:
            return []
        image_height, image_width = (float(side) for side in image.shape[:2])
        lines: list[OcrLine] = []
        for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            lines.append(
                OcrLine(
                    text=str(text).strip(),
                    score=float(score),
                    top=min(ys) / image_height,
                    left=min(xs) / image_width,
                    height=(max(ys) - min(ys)) / image_height,
                    width=(max(xs) - min(xs)) / image_width,
                )
            )
        return lines

    def warm_up(self, *, korean: bool = False) -> int:
        """Lädt die Modelle (inkl. Download) mit einem Probebild; gibt die Zeilenzahl zurück."""
        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

        canvas = Image.new("RGB", (640, 160), (255, 255, 255))
        ImageDraw.Draw(canvas).text(
            (20, 40), "PSA 110/098", fill=(0, 0, 0), font=ImageFont.load_default(size=56)
        )
        image = np.asarray(canvas, dtype=np.uint8)[:, :, ::-1].copy()
        return len(self.read(image, korean=korean))
