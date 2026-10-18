"""Offizielle asiatische Kartendatenbanken: gemeinsame Typen und HTML-Hilfen.

Beide Datenbanken (Japan: ``www.pokemon-card.com``, Taiwan: ``asia.pokemon-card.com/tw``)
liefern eine Liste aller Karten (seitenweise) und je Karte eine Detailseite. Die Liste
enthält ID, Name und Bild; Nummer und Setcode stehen nur auf der Detailseite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Protocol

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
# „001/103“, „132/M-P“, „SV001/SV-P“; Leerzeichen um den Schrägstrich sind erlaubt.
_NUMBER = re.compile(r"([A-Za-z]{0,4}\d{1,4}[A-Za-z]?)\s*/\s*([A-Za-z0-9][A-Za-z0-9-]{0,11})")


@dataclass(frozen=True)
class OfficialEntry:
    """Eintrag der Kartenliste."""

    official_id: str
    name: str
    image_url: str
    set_code: str | None = None


@dataclass(frozen=True)
class OfficialDetail:
    """Angaben der Detailseite (``None`` = nicht gefunden)."""

    name: str | None
    number: str | None
    set_code: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class ListPage:
    entries: list[OfficialEntry]
    max_page: int | None  # ``None``: unbekannt, weiterblättern bis eine Seite leer ist


class OfficialDatabase(Protocol):
    """Schnittstelle einer offiziellen Kartendatenbank."""

    source: str
    language: str

    async def list_page(self, page: int) -> ListPage: ...

    async def detail(self, official_id: str) -> tuple[OfficialDetail, str]:
        """Angaben der Detailseite und das HTML (für Diagnose)."""
        ...


def plain_text(html: str) -> str:
    """HTML-Ausschnitt → Text mit einfachen Leerzeichen."""
    return _SPACE.sub(" ", unescape(_TAG.sub(" ", html))).strip()


def find_number(text: str) -> str | None:
    """Gedruckte Kartennummer im Text, normiert ohne Leerzeichen (``"001/103"``)."""
    match = _NUMBER.search(text)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def absolute(base: str, url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url if url.startswith("http") else f"{base}{url if url.startswith('/') else '/' + url}"
