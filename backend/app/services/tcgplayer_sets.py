"""Setnamen von TCGplayer (über tcgcsv.com) → Setkürzel.

Collectr übernimmt die Setnamen von TCGplayer. Die weichen bei japanischen Sets oft von den
Namen in Kartenkiste ab („Hot Air Arena“ statt „Heat Wave Arena“, „Sky Legend“ statt „Sky
Legends“). TCGplayer führt zu jeder Gruppe ein Kürzel („SV9a“) – damit wird aus dem Namen
ohne Raten das Set. Die Liste (≈ 2 kleine Abrufe) bleibt einen Tag im Speicher; ist tcgcsv
nicht erreichbar, bleibt es beim Namensvergleich.
"""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import httpx
import structlog

from app.core.config import Settings

log = structlog.get_logger(__name__)

CATEGORIES = (3, 85)  # Pokémon (Englisch), Pokémon Japan
CACHE_SECONDS = 24 * 3600
RETRY_SECONDS = 10 * 60

_PREFIX = re.compile(r"^[A-Za-z0-9.-]{1,12}:\s+")  # „SV9a: Hot Air Arena“
_JP = re.compile(r"\s*(?:\(JP\)|\bJP)\s*$", re.IGNORECASE)
_KEY = re.compile(r"[^a-z0-9]+")
_LEADING_ZEROS = re.compile(r"(?<![0-9])0+(?=[0-9])")

SetAliases = Mapping[str, frozenset[str]]


def name_key(name: str) -> str:
    """Vergleichsschlüssel eines Setnamens (ohne Kürzel-Präfix und „(JP)“)."""
    text = unicodedata.normalize("NFKD", name.strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _JP.sub("", _PREFIX.sub("", text)).casefold().replace("&", "and")
    return _KEY.sub("", text)


def code_key(code: str) -> str:
    """Vergleichsschlüssel eines Setkürzels: „SV09“ = „sv9“, „SM10b“ = „sm10b“."""
    return _LEADING_ZEROS.sub("", _KEY.sub("", code.casefold()))


def build_aliases(groups: Iterable[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """Gruppen von tcgcsv → {Namensschlüssel: Kürzel-Schlüssel}."""
    found: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        name, code = group.get("name"), group.get("abbreviation")
        key = name_key(name) if isinstance(name, str) else ""
        if key and isinstance(code, str) and code.strip():
            found[key].add(code_key(code))
    return {key: frozenset(codes) for key, codes in found.items()}


_cache: tuple[float, dict[str, frozenset[str]]] | None = None
_lock = asyncio.Lock()


async def set_aliases(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> SetAliases:
    """Namensschlüssel → Setkürzel (zwischengespeichert; leer, wenn tcgcsv nicht antwortet)."""
    global _cache  # noqa: PLW0603 – einfacher Prozess-Cache
    async with _lock:
        now = time.monotonic()
        if _cache is not None and now < _cache[0]:
            return _cache[1]
        base = settings.sealed_images_url.rstrip("/")
        groups: list[Mapping[str, Any]] = []
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": settings.http_user_agent},
                timeout=20,
                follow_redirects=True,
                transport=transport,
            ) as client:
                for category in CATEGORIES:
                    response = await client.get(f"{base}/{category}/groups")
                    response.raise_for_status()
                    data = response.json()
                    items = data.get("results", []) if isinstance(data, dict) else data
                    groups += [item for item in items if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError):
            log.warning("tcgplayer_sets.unavailable", exc_info=True)
            _cache = (now + RETRY_SECONDS, {})
            return {}
        aliases = build_aliases(groups)
        _cache = (now + CACHE_SECONDS, aliases)
        log.info("tcgplayer_sets.loaded", groups=len(groups), names=len(aliases))
        return aliases


def reset_cache() -> None:
    """Für Tests."""
    global _cache  # noqa: PLW0603
    _cache = None
