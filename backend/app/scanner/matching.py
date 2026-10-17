"""Bildabgleich: SIFT-Merkmale + RANSAC (im Phase-0-Spike erprobt).

Score = Anzahl geometrisch konsistenter Übereinstimmungen (RANSAC-Inlier). Im Spike lag
die richtige Karte bei 184–370, andere Karten bei ≤ 20 (vereinzelt bis 219 bei gleicher
Figur) – ab :data:`CONFIDENT_INLIERS` gilt ein Treffer als sicher.

Merkmale werden gespeichert (Katalogbilder, Referenzbilder). Dafür werden die Deskriptoren
als ``uint8`` abgelegt (SIFT-Werte liegen ohnehin in 0..255) – ein Viertel des Platzes.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from app.scanner.imaging import UInt8Image, downscale

CONFIDENT_INLIERS = 50
RATIO_TEST = 0.75
MIN_GOOD_MATCHES = 8
RANSAC_THRESHOLD = 5.0
QUERY_FEATURES = 3000
REFERENCE_FEATURES = 2000
FEATURE_MAX_SIDE = 1024


@dataclass(frozen=True)
class ImageFeatures:
    """SIFT-Schlüsselpunkte (nur Koordinaten) und Deskriptoren eines Bildes."""

    points: npt.NDArray[np.float32]  # (n, 2)
    descriptors: npt.NDArray[np.uint8]  # (n, 128)

    def __len__(self) -> int:
        return int(self.points.shape[0])

    def to_bytes(self) -> bytes:
        buffer = io.BytesIO()
        np.savez_compressed(buffer, points=self.points, descriptors=self.descriptors)
        return buffer.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> ImageFeatures:
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            points = archive["points"].astype(np.float32)
            descriptors = archive["descriptors"].astype(np.uint8)
        if points.ndim != 2 or descriptors.ndim != 2 or len(points) != len(descriptors):  # noqa: PLR2004
            raise ValueError("Ungültige Merkmal-Datei.")
        return cls(points=points, descriptors=descriptors)

    @classmethod
    def empty(cls) -> ImageFeatures:
        return cls(
            points=np.zeros((0, 2), dtype=np.float32),
            descriptors=np.zeros((0, 128), dtype=np.uint8),
        )


def extract_features(image: UInt8Image, *, max_features: int = QUERY_FEATURES) -> ImageFeatures:
    """SIFT-Merkmale (Graustufen, längere Seite höchstens 1024 px)."""
    gray = cv2.cvtColor(downscale(image, FEATURE_MAX_SIDE), cv2.COLOR_BGR2GRAY)
    keypoints, descriptors = cv2.SIFT.create(nfeatures=max_features).detectAndCompute(gray, None)
    if descriptors is None or not keypoints:
        return ImageFeatures.empty()
    points = np.array([keypoint.pt for keypoint in keypoints], dtype=np.float32)
    return ImageFeatures(
        points=points,
        descriptors=np.clip(np.rint(descriptors), 0, 255).astype(np.uint8),
    )


def match_score(query: ImageFeatures, reference: ImageFeatures) -> int:
    """Anzahl RANSAC-Inlier zwischen zwei Bildern (0 = kein Zusammenhang)."""
    if len(query) < MIN_GOOD_MATCHES or len(reference) < MIN_GOOD_MATCHES:
        return 0
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(
        query.descriptors.astype(np.float32), reference.descriptors.astype(np.float32), k=2
    )
    good = [
        pair[0]
        for pair in pairs
        if len(pair) == 2 and pair[0].distance < RATIO_TEST * pair[1].distance  # noqa: PLR2004
    ]
    if len(good) < MIN_GOOD_MATCHES:
        return 0
    src = query.points[[match.queryIdx for match in good]]
    dst = reference.points[[match.trainIdx for match in good]]
    _, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_THRESHOLD)
    return int(mask.sum()) if mask is not None else 0
