"""Katalogbilder für den Bildabgleich – lazy geladen, nur Merkmale werden gespeichert.

Über 100.000 Kartenbilder vorab zu laden wäre teuer (Plan 5.6). Stattdessen wird das Bild
einer Karte erst geholt, wenn sie zum ersten Mal Kandidat eines Scans ist. Gespeichert
werden nur die SIFT-Merkmale (:class:`~app.scanner.storage.FeatureCache`).

Sicherheit: Nutzer können eigene Karten mit Bild-URL anlegen. Damit der Server keine
beliebigen Adressen abruft (SSRF), werden nur HTTPS-URLs der erlaubten Hosts geladen
(Standard: ``assets.tcgdex.net``).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog

from app.scanner.imaging import InvalidImageError, decode_image
from app.scanner.matching import REFERENCE_FEATURES, ImageFeatures, extract_features
from app.scanner.storage import FeatureCache

log = structlog.get_logger(__name__)

CpuRunner = Callable[..., Awaitable[Any]]

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
_IMAGE_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg")


def download_url(image_url: str) -> str:
    """TCGdex liefert Bild-URLs ohne Endung – die hohe Auflösung heißt ``/high.webp``."""
    path = urlsplit(image_url).path.lower()
    return image_url if path.endswith(_IMAGE_SUFFIXES) else f"{image_url.rstrip('/')}/high.webp"


def _features_from_bytes(data: bytes) -> ImageFeatures:
    return extract_features(decode_image(data), max_features=REFERENCE_FEATURES)


class CatalogImageIndex:
    """Liefert Merkmale zu Katalogbild-URLs (Speicher → Datei-Cache → Download)."""

    def __init__(
        self,
        cache: FeatureCache,
        client: httpx.AsyncClient,
        run_cpu: CpuRunner,
        *,
        allowed_hosts: Iterable[str],
        retry_missing_after_seconds: float = 7 * 24 * 3600,
        memory_entries: int = 128,
        download_concurrency: int = 6,
    ) -> None:
        self._cache = cache
        self._client = client
        self._run_cpu = run_cpu
        self._allowed_hosts = {host.lower() for host in allowed_hosts}
        self._retry_missing_after = retry_missing_after_seconds
        self._memory: OrderedDict[str, ImageFeatures] = OrderedDict()
        self._memory_entries = memory_entries
        self._downloads = asyncio.Semaphore(download_concurrency)

    def is_allowed(self, image_url: str) -> bool:
        parts = urlsplit(image_url)
        return parts.scheme == "https" and (parts.hostname or "").lower() in self._allowed_hosts

    def _remember(self, url: str, features: ImageFeatures) -> None:
        self._memory[url] = features
        self._memory.move_to_end(url)
        while len(self._memory) > self._memory_entries:
            self._memory.popitem(last=False)

    async def features_for(self, image_url: str | None) -> ImageFeatures | None:
        """Merkmale des Katalogbilds oder ``None`` (kein/unerlaubtes/fehlendes Bild)."""
        if not image_url or not self.is_allowed(image_url):
            return None
        if (features := self._memory.get(image_url)) is not None:
            self._memory.move_to_end(image_url)
            return features
        features = await self._run_cpu(self._cache.get, image_url)
        if features is None:
            missing_since = self._cache.missing_since(image_url)
            if missing_since is not None and (
                time.time() - missing_since < self._retry_missing_after
            ):
                return None
            features = await self._download(image_url)
        if features is not None:
            self._remember(image_url, features)
        return features

    async def _download(self, image_url: str) -> ImageFeatures | None:
        url = download_url(image_url)
        async with self._downloads:
            try:
                async with self._client.stream("GET", url) as response:
                    if response.status_code == httpx.codes.NOT_FOUND:
                        self._cache.mark_missing(image_url)
                        return None
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data += chunk
                        if len(data) > MAX_DOWNLOAD_BYTES:
                            raise InvalidImageError("Katalogbild ist zu groß.")
            except (httpx.HTTPError, InvalidImageError) as exc:
                # Netzfehler: nichts merken, beim nächsten Scan erneut versuchen.
                log.warning("catalog_image_failed", url=url, error=str(exc))
                return None
        try:
            features: ImageFeatures = await self._run_cpu(_features_from_bytes, bytes(data))
        except InvalidImageError:
            self._cache.mark_missing(image_url)
            return None
        await self._run_cpu(self._cache.put, image_url, features)
        return features

    async def features_many(self, urls: Iterable[str | None]) -> list[ImageFeatures | None]:
        """Mehrere Bilder parallel (Downloads begrenzt)."""
        return list(await asyncio.gather(*(self.features_for(url) for url in urls)))
