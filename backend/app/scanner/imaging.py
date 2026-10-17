"""Fotos sicher laden und die Karte im Bild finden.

Hochgeladene Dateien sind nicht vertrauenswürdig: Format und Pixelzahl werden geprüft,
*bevor* das Bild dekodiert wird (Schutz vor „Dekompressionsbomben“). Erlaubt sind JPEG,
PNG, WebP und HEIC/HEIF (iPhone).
"""

from __future__ import annotations

import io
import warnings
from functools import cache

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image, ImageOps, UnidentifiedImageError

UInt8Image = npt.NDArray[np.uint8]
Quad = npt.NDArray[np.float32]

MAX_SIDE = 1280
BINDER_MAX_SIDE = 2400
DEFAULT_MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP", "HEIF"})

CARD_RATIO = 63 / 88  # Breite / Höhe einer Standard-Pokémon-Karte
RATIO_TOLERANCE = 0.18
MIN_AREA_FRACTION = 0.08
NORM_WIDTH, NORM_HEIGHT = 630, 880
_QUAD_CORNERS = 4


class InvalidImageError(ValueError):
    """Datei ist kein (unterstütztes) Bild oder zu groß."""


@cache
def _register_heif() -> None:
    from pillow_heif import register_heif_opener  # noqa: PLC0415 – nur bei Bedarf laden

    register_heif_opener()


def decode_image(
    data: bytes, *, max_side: int = MAX_SIDE, max_pixels: int = DEFAULT_MAX_PIXELS
) -> UInt8Image:
    """Lädt ein Foto, korrigiert die EXIF-Drehung und verkleinert es auf ``max_side`` (BGR).

    Raises:
        InvalidImageError: leer, unbekanntes Format, zu viele Pixel oder defekt.
    """
    if not data:
        raise InvalidImageError("Die Datei ist leer.")
    _register_heif()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as raw:
                if raw.format not in ALLOWED_FORMATS:
                    raise InvalidImageError(
                        f"Bildformat {raw.format or 'unbekannt'} wird nicht unterstützt "
                        "(erlaubt: JPEG, PNG, WebP, HEIC)."
                    )
                if raw.width * raw.height > max_pixels:
                    raise InvalidImageError("Das Bild hat zu viele Pixel.")
                image = ImageOps.exif_transpose(raw).convert("RGB")
    except InvalidImageError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
        SyntaxError,  # defekte PNG-Blöcke
    ) as exc:
        raise InvalidImageError("Die Datei ist kein lesbares Bild.") from exc
    image.thumbnail((max_side, max_side))
    rgb = np.asarray(image, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).astype(np.uint8)


def encode_jpeg(image: UInt8Image, *, quality: int = 85, max_side: int | None = None) -> bytes:
    """Kodiert ein BGR-Bild als JPEG (optional vorher verkleinert)."""
    if max_side is not None:
        image = downscale(image, max_side)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:  # pragma: no cover – passiert nur bei leeren Bildern
        raise InvalidImageError("Bild konnte nicht gespeichert werden.")
    return bytes(buffer.tobytes())


def downscale(image: UInt8Image, max_side: int) -> UInt8Image:
    """Verkleinert proportional, sodass die längere Seite höchstens ``max_side`` ist."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image
    factor = max_side / longest
    size = (max(1, round(width * factor)), max(1, round(height * factor)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA).astype(np.uint8)


# --------------------------------------------------------------- Karte finden


def order_corners(points: npt.NDArray[np.float32]) -> Quad:
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


def quad_ratio(corners: Quad) -> float:
    """Verhältnis kurze/lange Seite eines geordneten Vierecks (≤ 1)."""
    top_left, top_right, bottom_right, bottom_left = corners
    width = (np.linalg.norm(top_right - top_left) + np.linalg.norm(bottom_right - bottom_left)) / 2
    height = (np.linalg.norm(bottom_left - top_left) + np.linalg.norm(bottom_right - top_right)) / 2
    short, long_ = sorted((float(width), float(height)))
    return short / long_ if long_ else 0.0


def _edge_maps(image: UInt8Image) -> list[UInt8Image]:
    """Zwei Kantenstrategien: Canny (kontrastreich) und adaptive Schwelle (schwaches Licht)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    canny = cv2.dilate(cv2.Canny(blurred, 40, 140), np.ones((5, 5), np.uint8), iterations=2)
    threshold = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 7
    )
    return [canny.astype(np.uint8), threshold.astype(np.uint8)]


def card_quads(
    image: UInt8Image,
    *,
    min_area_fraction: float = MIN_AREA_FRACTION,
    limit: int = 10,
    nested: bool = False,
) -> list[tuple[float, Quad]]:
    """Alle Vierecke mit Kartenformat als ``(Fläche, Ecken)``, größte zuerst.

    ``nested=True`` sucht auch Konturen innerhalb anderer (Karten in einer Binderseite).
    """
    min_area = min_area_fraction * image.shape[0] * image.shape[1]
    retrieval = cv2.RETR_LIST if nested else cv2.RETR_EXTERNAL
    found: list[tuple[float, Quad]] = []
    for edges in _edge_maps(image):
        contours, _ = cv2.findContours(edges, retrieval, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[: limit * 4]:
            area = float(cv2.contourArea(contour))
            if area < min_area:
                break
            perimeter = cv2.arcLength(contour, closed=True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, closed=True)
            if len(approx) == _QUAD_CORNERS:
                corners = order_corners(approx.reshape(4, 2).astype(np.float32))
            else:  # Fallback: kleinstes umschließendes Rechteck
                corners = order_corners(cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32))
            if abs(quad_ratio(corners) - CARD_RATIO) <= RATIO_TOLERANCE:
                found.append((area, corners))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def find_card_quad(image: UInt8Image) -> Quad | None:
    """Größtes Viereck mit Kartenformat oder ``None``."""
    quads = card_quads(image, limit=10)
    return quads[0][1] if quads else None


def rectify(image: UInt8Image, corners: Quad) -> UInt8Image:
    """Entzerrt die Karte auf das Normformat (hochkant, 630×880 px)."""
    top_left, top_right, _, bottom_left = corners
    if np.linalg.norm(top_right - top_left) > np.linalg.norm(bottom_left - top_left):
        corners = np.roll(corners, -1, axis=0)  # Karte liegt quer → um 90° drehen
    target = np.array(
        [[0, 0], [NORM_WIDTH - 1, 0], [NORM_WIDTH - 1, NORM_HEIGHT - 1], [0, NORM_HEIGHT - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), target)
    return cv2.warpPerspective(image, matrix, (NORM_WIDTH, NORM_HEIGHT)).astype(np.uint8)


def card_crop(image: UInt8Image, *, min_area_fraction: float = 0.15) -> UInt8Image | None:
    """Entzerrter Kartenausschnitt, wenn eine ausreichend große Karte erkannt wird.

    Dient als Zusatz: für eine zweite OCR bei kleinen Karten im Bild und als Referenzbild
    (ohne Hintergrund, damit eigene Referenzen nicht über den Tisch „matchen“).
    """
    quads = card_quads(image, min_area_fraction=min_area_fraction, limit=10)
    return rectify(image, quads[0][1]) if quads else None
