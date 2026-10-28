"""Binderseite in einzelne Karten zerlegen (Beta, Plan 5.6 Schritt 9).

Zwei Wege:

1. **Konturen:** Werden genügend gleich große Kartenvierecke gefunden, wird jedes einzeln
   entzerrt. Aus ihnen ergeben sich Kartengröße und Abstand – damit wird das **Raster
   vervollständigt**: Karten, deren Umriss ein Glanzstreifen der Hülle verdeckt, werden an
   ihrer berechneten Stelle ausgeschnitten statt wegzufallen, und Reihe/Spalte stimmen.
2. **Raster:** Sonst wird zuerst die Binderseite im Foto gesucht (Tisch und Ringe weg) und
   *sie* gleichmäßig geteilt (3×3 = 9er-Seite, 4×3 = 12er-Seite quer).

Geschätzte Zellen (``estimated``) sind etwas größer als eine Karte; die normale Erkennung
sucht darin die Karte selbst. Messung (``docs/phase8/binder.md``): synthetische Seiten mit
Hüllen, Tisch, Schräglage und Glanz.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.scanner.imaging import Quad, UInt8Image, card_quads, edge_maps, order_corners, rectify

BinderLayout = Literal["auto", "3x3", "4x3", "2x2"]
GRIDS: dict[str, tuple[int, int]] = {"3x3": (3, 3), "4x3": (4, 3), "2x2": (2, 2)}  # Spalten, Reihen
CELL_MARGIN = 0.04
MIN_DETECTED_CARDS = 3
_SAME_LINE = 0.45  # Mittelpunkte näher als dieser Anteil des Abstands: dieselbe Reihe/Spalte
_GAP_GUESS = 1.06  # Abstand ≈ Kartenmaß + Steg, solange nur eine Reihe/Spalte bekannt ist
_ESTIMATE_PADDING = 0.12  # geschätzte Zellen: so viel größer als eine Karte (je Seite)
_MIN_VISIBLE = 0.6  # ergänzte Position: so viel der Karte muss im Bild liegen
_PAGE_MIN_AREA = 0.3
MAX_CARDS = 12
_SIZE_TOLERANCE = 0.5  # Fläche höchstens ±50 % vom Median
_OVERLAP_LIMIT = 0.3
_REFERENCE_CANDIDATES = 4


@dataclass(frozen=True)
class BinderCell:
    """Eine Zelle der Seite (0-basiert, oben links beginnend).

    ``estimated``: Position berechnet statt als Umriss gefunden – die Erkennung soll die
    Karte in der Zelle selbst suchen.
    """

    row: int
    column: int
    image: UInt8Image
    estimated: bool = False


def split_grid(image: UInt8Image, columns: int, rows: int) -> list[BinderCell]:
    """Teilt das Bild gleichmäßig; jede Zelle verliert einen kleinen Rand."""
    height, width = image.shape[:2]
    cell_w, cell_h = width / columns, height / rows
    cells: list[BinderCell] = []
    for row in range(rows):
        for column in range(columns):
            x0 = int(column * cell_w + CELL_MARGIN * cell_w)
            x1 = int((column + 1) * cell_w - CELL_MARGIN * cell_w)
            y0 = int(row * cell_h + CELL_MARGIN * cell_h)
            y1 = int((row + 1) * cell_h - CELL_MARGIN * cell_h)
            cells.append(BinderCell(row, column, image[y0:y1, x0:x1].copy(), estimated=True))
    return cells


def _overlaps(box: tuple[float, float, float, float], others: list[tuple[float, ...]]) -> bool:
    x0, y0, x1, y1 = box
    area = (x1 - x0) * (y1 - y0)
    for ox0, oy0, ox1, oy1 in others:
        inter_w = max(0.0, min(x1, ox1) - max(x0, ox0))
        inter_h = max(0.0, min(y1, oy1) - max(y0, oy0))
        if area and inter_w * inter_h / area > _OVERLAP_LIMIT:
            return True
    return False


def _box(corners: Quad) -> tuple[float, float, float, float]:
    return (
        float(corners[:, 0].min()),
        float(corners[:, 1].min()),
        float(corners[:, 0].max()),
        float(corners[:, 1].max()),
    )


def _select_similar(quads: list[tuple[float, Quad]], reference_area: float) -> list[Quad]:
    """Nicht überlappende Vierecke mit ähnlicher Fläche wie ``reference_area``."""
    chosen: list[tuple[float, ...]] = []
    selected: list[Quad] = []
    for area, corners in quads:
        if abs(area - reference_area) > _SIZE_TOLERANCE * reference_area:
            continue
        box = _box(corners)
        if _overlaps(box, chosen):
            continue
        chosen.append(box)
        selected.append(corners)
        if len(selected) == MAX_CARDS:
            break
    return selected


def _lines(values: list[float], pitch: float) -> list[float]:
    """Mittelpunkte zu Reihen bzw. Spalten zusammenfassen (Mittelwert je Gruppe)."""
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] < _SAME_LINE * pitch:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _pitch(lines: list[float], size: float) -> float:
    """Abstand zweier Nachbarn; Lücken (fehlende Karte dazwischen) werden herausgerechnet."""
    guess = size * _GAP_GUESS
    estimates = []
    for first, second in itertools.pairwise(lines):
        steps = max(1, round((second - first) / guess))
        estimates.append((second - first) / steps)
    return float(np.median(estimates)) if estimates else guess


def _complete(
    lines: list[float], pitch: float, wanted: int, size: float, limit: float
) -> list[float]:
    """Alle Positionen einer Achse: Lücken füllen, dann bis ``wanted`` nach außen ergänzen –
    nur solange die Karte noch zum größten Teil im Bild liegt."""
    first = lines[0]
    known = {round((line - first) / pitch): line for line in lines}
    low, high = min(known), max(known)
    positions = {index: known.get(index, first + index * pitch) for index in range(low, high + 1)}

    def fits(center: float) -> bool:
        visible = min(center + size / 2, limit) - max(center - size / 2, 0.0)
        return visible >= _MIN_VISIBLE * size

    while len(positions) < wanted:
        before, after = first + (low - 1) * pitch, first + (high + 1) * pitch
        room_before, room_after = fits(before), fits(after)
        if not room_before and not room_after:
            break
        # Zur Seite mit mehr Platz zuerst (die Karten liegen meist mittig im Foto).
        if room_after and (not room_before or limit - after > before):
            high += 1
            positions[high] = after
        else:
            low -= 1
            positions[low] = before
    return [positions[index] for index in sorted(positions)]


def _estimated_cell(
    image: UInt8Image, center: tuple[float, float], size: tuple[float, float]
) -> UInt8Image:
    height, width = image.shape[:2]
    half_w = size[0] * (0.5 + _ESTIMATE_PADDING)
    half_h = size[1] * (0.5 + _ESTIMATE_PADDING)
    x0, x1 = max(0, int(center[0] - half_w)), min(width, int(center[0] + half_w))
    y0, y1 = max(0, int(center[1] - half_h)), min(height, int(center[1] + half_h))
    return image[y0:y1, x0:x1].copy()


def detect_cards(image: UInt8Image, grid: tuple[int, int] | None = None) -> list[BinderCell]:
    """Sucht Karten über Konturen und vervollständigt das Raster. Leere Liste, wenn das nicht
    verlässlich gelingt.

    Neben den Karten findet die Konturensuche oft auch die ganze Seite oder Teile des
    Artworks. Deshalb wird für einige der größten Vierecke geprüft, wie viele ähnlich große
    Vierecke es gibt – die größte Gruppe sind die Karten. ``grid`` (Spalten, Reihen) ist das
    erwartete Raster; ohne Angabe 3×3 hochkant bzw. 4×3 quer.
    """
    quads = card_quads(image, min_area_fraction=0.02, limit=MAX_CARDS * 3, nested=True)
    best: list[Quad] = []
    for area, _ in quads[:_REFERENCE_CANDIDATES]:
        selected = _select_similar(quads, area)
        if len(selected) > len(best):
            best = selected
    if len(best) < MIN_DETECTED_CARDS:
        return []

    boxes = [_box(corners) for corners in best]
    card_w = float(np.median([b[2] - b[0] for b in boxes]))
    card_h = float(np.median([b[3] - b[1] for b in boxes]))
    centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes]
    height, width = image.shape[:2]
    columns_wanted, rows_wanted = grid or ((4, 3) if width > height else (3, 3))

    column_lines = _lines([c[0] for c in centers], card_w * _GAP_GUESS)
    row_lines = _lines([c[1] for c in centers], card_h * _GAP_GUESS)
    pitch_x, pitch_y = _pitch(column_lines, card_w), _pitch(row_lines, card_h)
    xs = _complete(column_lines, pitch_x, columns_wanted, card_w, float(width))
    ys = _complete(row_lines, pitch_y, rows_wanted, card_h, float(height))

    cells: list[BinderCell] = []
    for row, y in enumerate(ys):
        for column, x in enumerate(xs):
            nearest = min(
                range(len(best)),
                key=lambda i: (centers[i][0] - x) ** 2 + (centers[i][1] - y) ** 2,
            )
            near_x = abs(centers[nearest][0] - x) < _SAME_LINE * pitch_x
            near_y = abs(centers[nearest][1] - y) < _SAME_LINE * pitch_y
            if near_x and near_y:
                cells.append(BinderCell(row, column, rectify(image, best[nearest])))
            else:
                cell = _estimated_cell(image, (x, y), (card_w, card_h))
                cells.append(BinderCell(row, column, cell, estimated=True))
    return cells


def find_page(image: UInt8Image) -> UInt8Image:
    """Die Binderseite im Foto (größtes Viereck ab 30 % der Fläche, entzerrt) – sonst das
    ganze Foto. So teilt das Raster die Seite und nicht Tisch und Ringe mit."""
    height, width = image.shape[:2]
    min_area = _PAGE_MIN_AREA * height * width
    best: tuple[float, Quad] | None = None
    for edges in edge_maps(image):
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < min_area or area > 0.98 * height * width:
                continue
            perimeter = cv2.arcLength(contour, closed=True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, closed=True)
            if len(approx) == 4 and (best is None or area > best[0]):  # noqa: PLR2004
                best = (area, order_corners(approx.reshape(4, 2).astype(np.float32)))
    if best is None:
        return image
    corners = best[1]
    top_left, top_right, bottom_right, bottom_left = corners
    out_w = int(
        max(np.linalg.norm(top_right - top_left), np.linalg.norm(bottom_right - bottom_left))
    )
    out_h = int(
        max(np.linalg.norm(bottom_left - top_left), np.linalg.norm(bottom_right - top_right))
    )
    target = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32
    )
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (out_w, out_h)).astype(np.uint8)


def binder_cells(image: UInt8Image, layout: BinderLayout = "auto") -> tuple[list[BinderCell], str]:
    """Zerlegt die Seite. Gibt die Zellen und das tatsächlich genutzte Verfahren zurück."""
    grid = GRIDS.get(layout)
    detected = detect_cards(image, grid)
    if detected:
        return detected, "konturen"
    page = find_page(image)
    if grid is None:
        layout = "4x3" if page.shape[1] > page.shape[0] else "3x3"
    columns, rows = GRIDS[layout]
    return split_grid(page, columns, rows), layout
