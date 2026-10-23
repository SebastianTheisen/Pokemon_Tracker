"""Nachdrucke unterscheiden: gleiche Karte, gleiche Nummer, kleiner Unterschied im Bild.

Beispiel: „30th Celebration: Classic Collection“ druckt Glurak 4/102 oder Selfe 43/146 mit
derselben Nummer und demselben Bild nach – dazu kommt nur ein Jubiläums-Stempel
(Celebrations 2021 ebenso). Name, Nummer und Setgröße passen dann auf beide Karten, und der
gewöhnliche Bildabgleich zählt vor allem das Gemeinsame.

Vorgehen (Katalogbilder aller Zwillinge in *einer* Sprache, damit Text kein Unterschied ist):

1. Alle Katalogbilder auf das erste ausrichten (SIFT + Homographie).
2. Bilder, die großflächig abweichen, sind andere Karten (nur die übrigen sind Zwillinge).
3. **Unterschiedsmaske**: Stellen, an denen sich die Katalogbilder deutlich unterscheiden
   (Stempel, Set-Symbol). Feines Rauschen verschiedener Bildquellen fällt durch Weichzeichnen,
   Schwelle und Öffnen heraus.
4. Das Foto ebenfalls ausrichten und *nur in der Maske* mit jedem Katalogbild vergleichen
   (normierte Helligkeit, mittlere Abweichung).
5. Liegt ein Bild um mindestens :data:`TWIN_MIN_MARGIN` (relativ) vorn, ist es die Karte –
   sonst bleibt es offen und die App fragt nach.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from app.scanner.imaging import UInt8Image
from app.scanner.matching import extract_features, match_inliers

WIDTH, HEIGHT = 600, 836  # Kartenformat 63 × 88 mm
TWIN_MIN_MARGIN = 0.15
MIN_ALIGN_INLIERS = 25
DIFF_THRESHOLD = 45.0  # Grauwert-Abweichung nach Normierung (0..255)
MIN_MASK_SHARE = 0.002  # kleiner = kein sichtbarer Unterschied
MAX_MASK_SHARE = 0.25  # größer = Bilder passen nicht zueinander (andere Sprache, Fehlausrichtung)
_BLUR = (7, 7)
_KERNEL = np.ones((5, 5), np.uint8)

FloatImage = npt.NDArray[np.float32]


@dataclass(frozen=True)
class TwinDecision:
    """Ergebnis des Vergleichs.

    ``members``: Indizes der Katalogbilder, die wirklich dieselbe Grafik zeigen (immer mit 0,
    sonst leer). ``index``: das passende davon oder ``None`` (zu knapp).
    """

    members: tuple[int, ...] = ()
    index: int | None = None
    distances: tuple[float, ...] = ()


def _card(image: UInt8Image) -> UInt8Image:
    """BGR im Einheitsformat (Katalogbilder zeigen die ganze Karte bis zum Rand)."""
    color = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image  # noqa: PLR2004
    return np.asarray(cv2.resize(color, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA), np.uint8)


def _normalized(image: UInt8Image) -> FloatImage:
    """Grau, weichgezeichnet und auf Mittelwert/Streuung normiert (Belichtung egal)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray.astype(np.float32), _BLUR, 0)
    std = float(blurred.std()) or 1.0
    return np.asarray((blurred - blurred.mean()) / std * 48.0 + 128.0, np.float32)


def _align(image: UInt8Image, target: UInt8Image) -> UInt8Image | None:
    """``image`` per Homographie auf ``target`` legen (``None``: kein sicherer Zusammenhang)."""
    source, destination = extract_features(image), extract_features(target)
    source_idx, target_idx = match_inliers(source, destination)
    if source_idx.size < MIN_ALIGN_INLIERS:
        return None
    homography, _ = cv2.findHomography(
        source.points[source_idx], destination.points[target_idx], cv2.RANSAC, 3.0
    )
    if homography is None:
        return None
    warped = cv2.warpPerspective(image, homography, (WIDTH, HEIGHT), borderValue=0)
    return np.asarray(warped, np.uint8)


def difference_mask(images: Sequence[FloatImage]) -> npt.NDArray[np.bool_]:
    """Wo unterscheiden sich die (ausgerichteten, normierten) Katalogbilder deutlich?"""
    mask = np.zeros((HEIGHT, WIDTH), np.uint8)
    for first in range(len(images)):
        for second in range(first + 1, len(images)):
            diff = np.abs(images[first] - images[second]) > DIFF_THRESHOLD
            mask |= diff.astype(np.uint8)
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _KERNEL)
    return np.asarray(cv2.dilate(opened, _KERNEL, iterations=2), bool)


def _mask_share(first: FloatImage, second: FloatImage, valid: npt.NDArray[np.bool_]) -> float:
    return float((difference_mask([first, second]) & valid).mean())


def pick_twin(photo: UInt8Image, catalog: Sequence[UInt8Image]) -> TwinDecision:
    """Welchem Katalogbild gleicht der Kartenausschnitt ``photo`` an den Unterschieden?

    Bilder, die sich nicht auf das erste legen lassen oder großflächig abweichen (andere
    Grafik), zählen nicht als Zwilling.
    """
    base = _card(catalog[0])
    aligned: dict[int, UInt8Image] = {0: base}
    for index, image in enumerate(catalog[1:], start=1):
        warped = _align(_card(image), base)
        if warped is not None:
            aligned[index] = warped
    photo_aligned = _align(_card(photo), base)
    if len(aligned) < 2 or photo_aligned is None:  # noqa: PLR2004
        return TwinDecision()
    # Ränder ohne Bildinhalt (nach dem Ausrichten schwarz) nicht werten.
    valid = np.logical_and.reduce(
        [image.any(axis=2) for image in [*aligned.values(), photo_aligned]]
    )
    normalized = {index: _normalized(image) for index, image in aligned.items()}
    members = [0] + [
        index
        for index in sorted(normalized)
        if index and _mask_share(normalized[0], normalized[index], valid) <= MAX_MASK_SHARE
    ]
    if len(members) < 2:  # noqa: PLR2004
        return TwinDecision()
    mask = difference_mask([normalized[index] for index in members]) & valid
    if mask.mean() < MIN_MASK_SHARE:  # kein sichtbarer Unterschied
        return TwinDecision(tuple(members))
    query = _normalized(photo_aligned)
    distances = tuple(
        float(np.abs(query[mask] - normalized[index][mask]).mean()) for index in members
    )
    order = sorted(range(len(members)), key=lambda position: distances[position])
    best, runner_up = distances[order[0]], distances[order[1]]
    winner = members[order[0]] if (runner_up - best) / runner_up >= TWIN_MIN_MARGIN else None
    return TwinDecision(tuple(members), winner, distances)
