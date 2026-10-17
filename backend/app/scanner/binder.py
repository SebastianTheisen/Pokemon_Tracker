"""Binderseite in einzelne Karten zerlegen (Beta, Plan 5.6 Schritt 9).

Zwei Wege:

1. **Konturen:** Werden genügend gleich große Kartenvierecke gefunden, wird jedes einzeln
   entzerrt und nach Reihe/Spalte sortiert.
2. **Raster:** Sonst wird ein festes Raster angenommen (3×3 = 9er-Seite, 4×3 = 12er-Seite
   quer) und das Bild gleichmäßig geteilt – mit etwas Rand, damit Nachbarkarten nicht
   hineinragen.

Jede Zelle läuft danach einzeln durch die normale Erkennung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.scanner.imaging import Quad, UInt8Image, card_quads, rectify

BinderLayout = Literal["auto", "3x3", "4x3", "2x2"]
GRIDS: dict[str, tuple[int, int]] = {"3x3": (3, 3), "4x3": (4, 3), "2x2": (2, 2)}  # Spalten, Reihen
CELL_MARGIN = 0.04
MIN_DETECTED_CARDS = 4
MAX_CARDS = 12
_SIZE_TOLERANCE = 0.5  # Fläche höchstens ±50 % vom Median
_OVERLAP_LIMIT = 0.3
_REFERENCE_CANDIDATES = 4


@dataclass(frozen=True)
class BinderCell:
    """Eine Zelle der Seite (0-basiert, oben links beginnend)."""

    row: int
    column: int
    image: UInt8Image


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
            cells.append(BinderCell(row, column, image[y0:y1, x0:x1].copy()))
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


def detect_cards(image: UInt8Image) -> list[BinderCell]:
    """Sucht Karten über Konturen. Leere Liste, wenn das nicht verlässlich gelingt.

    Neben den Karten findet die Konturensuche oft auch die ganze Seite oder Teile des
    Artworks. Deshalb wird für einige der größten Vierecke geprüft, wie viele ähnlich große
    Vierecke es gibt – die größte Gruppe sind die Karten.
    """
    quads = card_quads(image, min_area_fraction=0.02, limit=MAX_CARDS * 3, nested=True)
    best: list[Quad] = []
    for area, _ in quads[:_REFERENCE_CANDIDATES]:
        selected = _select_similar(quads, area)
        if len(selected) > len(best):
            best = selected
    if len(best) < MIN_DETECTED_CARDS:
        return []

    # Reihen bilden: Karten, deren Mittelpunkte weniger als eine halbe Kartenhöhe
    # auseinanderliegen, gehören zur selben Reihe.
    boxes = [_box(corners) for corners in best]
    centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, b[3] - b[1]) for b in boxes]
    order = sorted(range(len(best)), key=lambda i: centers[i][1])
    rows: list[list[int]] = []
    for index in order:
        if rows and abs(centers[index][1] - centers[rows[-1][0]][1]) < centers[index][2] / 2:
            rows[-1].append(index)
        else:
            rows.append([index])
    cells: list[BinderCell] = []
    for row_number, members in enumerate(rows):
        for column, index in enumerate(sorted(members, key=lambda i: centers[i][0])):
            cells.append(BinderCell(row_number, column, rectify(image, best[index])))
    return cells


def binder_cells(image: UInt8Image, layout: BinderLayout = "auto") -> tuple[list[BinderCell], str]:
    """Zerlegt die Seite. Gibt die Zellen und das tatsächlich genutzte Verfahren zurück."""
    if layout == "auto":
        detected = detect_cards(image)
        if detected:
            return detected, "konturen"
        layout = "3x3"
    columns, rows = GRIDS[layout]
    return split_grid(image, columns, rows), layout
