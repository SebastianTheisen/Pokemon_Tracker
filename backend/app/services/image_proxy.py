"""Kartenbilder über den eigenen Server: geladen, verkleinert (WebP) und auf der Platte gemerkt.

Warum: Viele Bildserver (z. B. pokemon-card.com) erlauben keinen Zugriff aus fremden Webseiten
(CORS). Die Web-App muss solche Bilder dann als einzelne HTML-Elemente einbetten – bei einem
Set mit 200 Karten frisst das Hunderte MB, iPhones beenden die App. Über den eigenen Server
kommt jedes Bild in der passenden Größe und ohne diese Sonderbehandlung.

Nur Hosts aus der Freigabeliste werden angefragt (Schutz vor SSRF); andere Adressen leitet die
API einfach an das Original weiter.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import structlog
from PIL import Image, UnidentifiedImageError

log = structlog.get_logger(__name__)

WIDTHS = (160, 240, 320, 480, 800)
"""Feste Stufen, damit der Cache nicht je Pixelbreite neue Dateien anlegt."""

MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_REDIRECTS = 3
WEBP_QUALITY = 80


class ImageProxyError(Exception):
    """Bild nicht ladbar (nicht erlaubt, Netzfehler, kein Bild) – Aufrufer leitet weiter."""


def width_bucket(width: int) -> int:
    """Kleinste Stufe, die mindestens so breit ist (sonst die größte)."""
    return next((w for w in WIDTHS if w >= width), WIDTHS[-1])


def is_allowed(url: str, hosts: Iterable[str]) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() in {h.lower() for h in hosts}


def cache_path(root: Path, url: str, width: int) -> Path:
    digest = hashlib.sha256(f"{width}:{url}".encode()).hexdigest()
    return root / digest[:2] / f"{digest}.webp"


def _resize(data: bytes, width: int) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ImageProxyError("Bild ist zu groß.")
            image.draft("RGB", (width, width * 2))  # JPEG: gleich verkleinert dekodieren
            image.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
            converted = image.convert("RGBA" if image.mode in {"RGBA", "LA", "P"} else "RGB")
            out = io.BytesIO()
            converted.save(out, "WEBP", quality=WEBP_QUALITY, method=4)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageProxyError("Kein lesbares Bild.") from exc


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "wb") as file:
        file.write(data)
    Path(temp).replace(path)


class ImageProxy:
    """Lädt erlaubte Bilder, verkleinert sie und merkt sie sich (Dateien unter ``root``)."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        root: Path,
        *,
        allowed_hosts: Iterable[str],
        concurrency: int = 6,
    ) -> None:
        self._client = client
        self._root = root
        self._hosts = frozenset(host.lower() for host in allowed_hosts)
        self._downloads = asyncio.Semaphore(concurrency)

    def allowed(self, url: str) -> bool:
        return is_allowed(url, self._hosts)

    async def thumbnail(self, url: str, width: int) -> bytes:
        """WebP in der Stufe zu ``width``; wirft :class:`ImageProxyError`, wenn es nicht geht."""
        if not self.allowed(url):
            raise ImageProxyError("Host nicht freigegeben.")
        width = width_bucket(width)
        path = cache_path(self._root, url, width)
        if path.exists():
            return await asyncio.to_thread(path.read_bytes)
        data = await self._fetch(url)
        result = await asyncio.to_thread(_resize, data, width)
        await asyncio.to_thread(_write_atomic, path, result)
        return result

    async def _fetch(self, url: str) -> bytes:
        """Laden; Weiterleitungen nur innerhalb der Freigabeliste – jede Station wird geprüft,
        bevor sie angefragt wird."""
        async with self._downloads:
            try:
                for _ in range(MAX_REDIRECTS + 1):
                    async with self._client.stream("GET", url, follow_redirects=False) as response:
                        if response.is_redirect:
                            url = str(response.url.join(response.headers.get("location", "")))
                            if not self.allowed(url):
                                raise ImageProxyError("Weiterleitung auf fremden Host.")
                            continue
                        response.raise_for_status()
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data += chunk
                            if len(data) > MAX_DOWNLOAD_BYTES:
                                raise ImageProxyError("Bild ist zu groß.")
                        return bytes(data)
            except httpx.HTTPError as exc:
                log.warning("image_proxy.fetch_failed", url=url, error=str(exc))
                raise ImageProxyError("Bild nicht erreichbar.") from exc
        raise ImageProxyError("Zu viele Weiterleitungen.")
