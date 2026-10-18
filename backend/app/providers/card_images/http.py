"""Höflicher HTTP-Client für fremde Server: höchstens eine Anfrage je Intervall und Host.

Die offiziellen Kartendatenbanken sind keine APIs für Dritte. Wir fragen deshalb sanft an
(Standard: eine Anfrage pro Sekunde und Server), mit erkennbarem User-Agent, und laden nie
Bilder herunter – geprüft wird nur, ob es sie gibt.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

_IMAGE_PROBE_TIMEOUT = 20.0


class SourceError(Exception):
    """Quelle nicht erreichbar oder Antwort unbrauchbar."""


class PoliteClient:
    """``httpx.AsyncClient`` mit Mindestabstand zwischen Anfragen an denselben Host."""

    def __init__(
        self,
        *,
        user_agent: str,
        min_interval: float = 1.0,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._min_interval = min_interval
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request: dict[str, float] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _wait_turn(self, url: str) -> None:
        """Wartet, bis der Host wieder angefragt werden darf (Aufrufer hält das Host-Lock)."""
        host = urlsplit(url).hostname or ""
        last = self._last_request.get(host)
        if last is not None:
            delay = self._min_interval - (time.monotonic() - last)
            if delay > 0:
                await asyncio.sleep(delay)
        self._last_request[host] = time.monotonic()

    def _lock(self, url: str) -> asyncio.Lock:
        return self._locks[urlsplit(url).hostname or ""]

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET mit Wartezeit. Wirft :class:`SourceError` bei Netz- oder HTTP-Fehlern."""
        async with self._lock(url):
            await self._wait_turn(url)
            try:
                response = await self._client.get(url, **kwargs)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise SourceError(f"GET {url}: HTTP {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise SourceError(f"GET {url}: {type(exc).__name__}: {exc}") from exc
            return response

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"GET {url}: kein JSON") from exc

    async def image_exists(self, url: str) -> bool:
        """Gibt es unter der Adresse ein Bild? Lädt nur den Kopf der Antwort.

        ``False`` bei 404/410 oder wenn statt eines Bildes eine Seite kommt (pokemon.com
        liefert für fehlende Bilder HTML). Netzfehler und Serverfehler → :class:`SourceError`,
        damit ein Ausfall nicht als „kein Bild“ gespeichert wird.
        """
        async with self._lock(url):
            await self._wait_turn(url)
            try:
                async with self._client.stream(
                    "GET", url, timeout=_IMAGE_PROBE_TIMEOUT
                ) as response:
                    if response.status_code in (httpx.codes.NOT_FOUND, httpx.codes.GONE):
                        return False
                    if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                        raise SourceError(f"GET {url}: HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "")
                    return response.is_success and content_type.startswith("image/")
            except httpx.HTTPError as exc:
                raise SourceError(f"GET {url}: {type(exc).__name__}: {exc}") from exc
