"""Höflicher HTTP-Client für fremde Server: höchstens eine Anfrage je Intervall und Host.

Die offiziellen Kartendatenbanken sind keine APIs für Dritte. Wir fragen deshalb sanft an
(Standard: eine Anfrage pro Sekunde und Server, einstellbar), mit erkennbarem User-Agent, und
laden nie Bilder herunter – geprüft wird nur, ob es sie gibt. Meldet ein Server „zu viel“
(429, 403, 503), verdoppelt sich der Abstand für diesen Server automatisch (höchstens 30 s);
nach 200 Erfolgen in Folge wird er schrittweise wieder kleiner.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx
import structlog

log = structlog.get_logger(__name__)

_IMAGE_PROBE_TIMEOUT = 20.0
# Antworten, mit denen ein Server „zu schnell“ signalisiert → automatisch bremsen.
_SLOW_DOWN_STATUS = frozenset({403, 429, 503})
MAX_INTERVAL = 30.0
# Nach so vielen erfolgreichen Anfragen in Folge wieder etwas schneller werden.
_RECOVER_AFTER = 200


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
        # Aktueller Abstand je Host: startet beim eingestellten Wert, wächst bei 429/403/503.
        self._interval: dict[str, float] = {}
        self._successes: defaultdict[str, int] = defaultdict(int)

    def interval(self, host: str) -> float:
        return self._interval.get(host, self._min_interval)

    def _slow_down(self, url: str, response: httpx.Response) -> None:
        """Server meldet Überlastung/Sperre: Abstand verdoppeln (bzw. ``Retry-After``)."""
        host = urlsplit(url).hostname or ""
        retry_after = response.headers.get("retry-after", "")
        wanted = float(retry_after) if retry_after.isdigit() else self.interval(host) * 2
        self._interval[host] = min(max(wanted, 1.0), MAX_INTERVAL)
        self._successes[host] = 0
        log.warning(
            "polite_client.slow_down",
            host=host,
            status=response.status_code,
            interval=self._interval[host],
        )

    def _succeeded(self, url: str) -> None:
        """Nach vielen Erfolgen in Folge den Abstand schrittweise wieder verkleinern."""
        host = urlsplit(url).hostname or ""
        if host not in self._interval:
            return
        self._successes[host] += 1
        if self._successes[host] >= _RECOVER_AFTER:
            self._successes[host] = 0
            relaxed = self._interval[host] * 0.75
            if relaxed <= self._min_interval:
                del self._interval[host]
            else:
                self._interval[host] = relaxed

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
            delay = self.interval(host) - (time.monotonic() - last)
            if delay > 0:
                await asyncio.sleep(delay)
        self._last_request[host] = time.monotonic()

    def _lock(self, url: str) -> asyncio.Lock:
        return self._locks[urlsplit(url).hostname or ""]

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET mit Wartezeit. Wirft :class:`SourceError` bei Netz- oder HTTP-Fehlern.

        Das Host-Lock gilt nur für den Start: höchstens eine *neue* Anfrage je Intervall;
        langsame Antworten dürfen sich überlappen (sonst bremst die Antwortzeit den Lauf).
        """
        async with self._lock(url):
            await self._wait_turn(url)
        try:
            response = await self._client.get(url, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _SLOW_DOWN_STATUS:
                self._slow_down(url, exc.response)
            raise SourceError(f"GET {url}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"GET {url}: {type(exc).__name__}: {exc}") from exc
        self._succeeded(url)
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
            async with self._client.stream("GET", url, timeout=_IMAGE_PROBE_TIMEOUT) as response:
                if response.status_code in (httpx.codes.NOT_FOUND, httpx.codes.GONE):
                    self._succeeded(url)
                    return False
                if response.status_code in _SLOW_DOWN_STATUS:
                    # Gesperrt/überlastet ist nicht „kein Bild“ – nichts speichern, bremsen.
                    self._slow_down(url, response)
                    raise SourceError(f"GET {url}: HTTP {response.status_code}")
                if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                    raise SourceError(f"GET {url}: HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "")
                self._succeeded(url)
                return response.is_success and content_type.startswith("image/")
        except httpx.HTTPError as exc:
            raise SourceError(f"GET {url}: {type(exc).__name__}: {exc}") from exc
