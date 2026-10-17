"""Rauchtest für den Scanner-Spike mit einem synthetischen Kartenfoto.

Ersetzt keine echten Fotos – prüft nur, dass Erkennung, Entzerrung und OCR-Auswertung
zusammenspielen. Wird übersprungen, wenn die Spike-Abhängigkeiten fehlen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("rapidocr")

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from scripts import spike_scanner as scanner  # noqa: E402


def _synthetic_card() -> Image.Image:
    """Eine schlichte „Karte“ mit Name oben und Nummer unten."""
    card = Image.new("RGB", (scanner.NORM_WIDTH, scanner.NORM_HEIGHT), (250, 220, 90))
    draw = ImageDraw.Draw(card)
    draw.rectangle((30, 30, 600, 850), fill=(245, 245, 235))
    draw.text((50, 50), "Nachtara VMAX", fill=(10, 10, 10), font=ImageFont.load_default(size=48))
    draw.text((50, 800), "215/203", fill=(10, 10, 10), font=ImageFont.load_default(size=30))
    return card


def _photo_of(card: Image.Image) -> np.ndarray:
    """Legt die Karte schräg auf einen dunklen Tisch (Perspektive wie ein Handyfoto)."""
    background = np.full((1200, 1000, 3), 40, dtype=np.uint8)
    src = np.array(
        [[0, 0], [card.width, 0], [card.width, card.height], [0, card.height]], dtype=np.float32
    )
    dst = np.array([[220, 150], [760, 190], [800, 1000], [180, 960]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    card_bgr = cv2.cvtColor(np.asarray(card), cv2.COLOR_RGB2BGR)
    warped = cv2.warpPerspective(card_bgr, matrix, (1000, 1200))
    mask = cv2.warpPerspective(np.full(card_bgr.shape[:2], 255, np.uint8), matrix, (1000, 1200))
    background[mask > 0] = warped[mask > 0]
    return background


def test_pipeline_finds_card_name_and_number(tmp_path: Path) -> None:
    photo_path = tmp_path / "synthetisch.png"
    cv2.imwrite(str(photo_path), _photo_of(_synthetic_card()))

    result = scanner.process_photo(photo_path, scanner.Ocr(), tmp_path)

    assert result.card_found
    assert result.name_guess is not None
    assert "nachtara" in result.name_guess.casefold()
    assert result.number_guess == "215/203"
    result.expected_name, result.expected_number = "Nachtara VMAX", "215/203"
    assert result.name_in_text
    assert result.number_in_text


def test_number_normalization() -> None:
    assert scanner._normalize_number("015/203") == "15"
    assert scanner._normalize_number("SWSH 050") == "SWSH050"
    assert scanner._normalize_number(None) == ""


@pytest.mark.parametrize(
    ("expected", "texts", "found"),
    [
        ("110/098", ["512 F 110/098 SR"], True),
        ("110/098", ["11O/O98"], True),  # O statt 0
        ("165/103", ["G504C 165/103"], True),
        ("165/103", ["1165/1030"], False),  # keine Teiltreffer in längeren Zahlen
        ("007", ["No. 007"], True),
        ("007", ["1007"], False),
    ],
)
def test_number_occurs(expected: str, texts: list[str], found: bool) -> None:
    assert scanner._number_occurs(expected, texts) is found
