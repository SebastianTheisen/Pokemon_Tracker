"""Ablage des Scanners auf dem Daten-Volume (``PT_SCANNER_DATA_DIR``).

Aufbau::

    <data_dir>/catalog/<hash>.npz          Merkmale eines Katalogbilds (kein Bild)
    <data_dir>/catalog/<hash>.missing      Bild fehlt bei der Quelle (später erneut versuchen)
    <data_dir>/references/<user>/<id>.jpg  eigenes Referenzbild (nur Kartenausschnitt)
    <data_dir>/references/<user>/<id>.npz  dessen Merkmale

Fotos selbst werden **nicht** gespeichert. Bis ein Nutzer einen Treffer bestätigt, liegt
der Kartenausschnitt nur im Arbeitsspeicher (:class:`PendingScans`, begrenzt und mit Ablauf).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from app.scanner.matching import ImageFeatures


def _atomic_write(path: Path, data: bytes) -> None:
    """Schreibt erst in eine Temp-Datei und benennt dann um – nie halbe Dateien."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as temp_file:
            temp_file.write(data)
        Path(temp_name).replace(path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


class FeatureCache:
    """Merkmale von Katalogbildern, Schlüssel = Hash der Bild-URL."""

    def __init__(self, root: Path) -> None:
        self.root = root / "catalog"

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:40]

    def _path(self, url: str, suffix: str) -> Path:
        return self.root / f"{self.key(url)}{suffix}"

    def get(self, url: str) -> ImageFeatures | None:
        path = self._path(url, ".npz")
        try:
            return ImageFeatures.from_bytes(path.read_bytes())
        except FileNotFoundError:
            return None
        except (ValueError, OSError, KeyError):
            path.unlink(missing_ok=True)  # defekt → beim nächsten Mal neu laden
            return None

    def put(self, url: str, features: ImageFeatures) -> None:
        _atomic_write(self._path(url, ".npz"), features.to_bytes())
        self._path(url, ".missing").unlink(missing_ok=True)

    def mark_missing(self, url: str) -> None:
        _atomic_write(self._path(url, ".missing"), b"")

    def missing_since(self, url: str) -> float | None:
        """Zeitpunkt (Unix-Sekunden), seit dem das Bild als fehlend gilt."""
        try:
            return self._path(url, ".missing").stat().st_mtime
        except FileNotFoundError:
            return None


class ReferenceStore:
    """Eigene Referenzbilder je Nutzer (Kartenausschnitt als JPEG + Merkmale)."""

    def __init__(self, root: Path) -> None:
        self.root = root / "references"

    def _base(self, user_id: uuid.UUID, reference_id: uuid.UUID) -> Path:
        return self.root / str(user_id) / str(reference_id)

    def save(
        self,
        user_id: uuid.UUID,
        reference_id: uuid.UUID,
        image_jpeg: bytes,
        features: ImageFeatures,
    ) -> None:
        base = self._base(user_id, reference_id)
        _atomic_write(base.with_suffix(".npz"), features.to_bytes())
        _atomic_write(base.with_suffix(".jpg"), image_jpeg)

    def features(self, user_id: uuid.UUID, reference_id: uuid.UUID) -> ImageFeatures | None:
        try:
            data = self._base(user_id, reference_id).with_suffix(".npz").read_bytes()
            return ImageFeatures.from_bytes(data)
        except (OSError, ValueError, KeyError):
            return None

    def image(self, user_id: uuid.UUID, reference_id: uuid.UUID) -> bytes | None:
        try:
            return self._base(user_id, reference_id).with_suffix(".jpg").read_bytes()
        except OSError:
            return None

    def delete(self, user_id: uuid.UUID, reference_id: uuid.UUID) -> None:
        base = self._base(user_id, reference_id)
        for suffix in (".jpg", ".npz"):
            base.with_suffix(suffix).unlink(missing_ok=True)

    def prune(self, keep: set[tuple[uuid.UUID, uuid.UUID]]) -> int:
        """Löscht Dateien ohne Datenbankeintrag (z. B. nach Löschen einer Karte)."""
        removed = 0
        if not self.root.exists():
            return 0
        for path in self.root.glob("*/*"):
            try:
                identity = (uuid.UUID(path.parent.name), uuid.UUID(path.stem))
            except ValueError:
                continue
            if identity not in keep:
                path.unlink(missing_ok=True)
                removed += 1
        return removed


@dataclass(frozen=True)
class PendingScan:
    """Kartenausschnitt eines Scans, bis der Nutzer bestätigt (nur im Arbeitsspeicher)."""

    user_id: uuid.UUID
    image_jpeg: bytes
    expires_at: float


class PendingScans:
    """Begrenzter Zwischenspeicher mit Ablaufzeit (älteste Einträge fliegen zuerst raus)."""

    def __init__(self, *, ttl_seconds: float, max_entries: int = 300) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._items: OrderedDict[uuid.UUID, PendingScan] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._items)

    def _purge(self, now: float) -> None:
        for scan_id in [key for key, item in self._items.items() if item.expires_at <= now]:
            del self._items[scan_id]
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def put(self, scan_id: uuid.UUID, user_id: uuid.UUID, image_jpeg: bytes) -> None:
        now = time.monotonic()
        with self._lock:
            self._items[scan_id] = PendingScan(user_id, image_jpeg, now + self._ttl)
            self._purge(now)

    def pop(self, scan_id: uuid.UUID, user_id: uuid.UUID) -> PendingScan | None:
        """Entnimmt den Eintrag – nur für den Nutzer, der gescannt hat."""
        with self._lock:
            self._purge(time.monotonic())
            item = self._items.get(scan_id)
            if item is None or item.user_id != user_id:
                return None
            del self._items[scan_id]
            return item

    def contains(self, scan_id: uuid.UUID) -> bool:
        with self._lock:
            self._purge(time.monotonic())
            return scan_id in self._items
