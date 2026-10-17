"""Client für die TCGdex-REST-API (https://tcgdex.dev).

Nur die Felder, die der Katalog braucht, werden validiert; alles andere wird ignoriert.
Feldnamen laut Phase-0-Spike (``docs/spikes/datenquellen.md``).
"""

from __future__ import annotations

from datetime import date
from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _TcgdexModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CardCount(_TcgdexModel):
    total: int | None = None
    official: int | None = None


class SetBrief(_TcgdexModel):
    """Eintrag aus ``GET /{lang}/sets``."""

    id: str
    name: str
    logo: str | None = None
    symbol: str | None = None
    card_count: CardCount = Field(default_factory=CardCount, alias="cardCount")


class CardBrief(_TcgdexModel):
    """Karte, wie sie in ``GET /{lang}/sets/{id}`` aufgelistet wird."""

    id: str
    local_id: str = Field(alias="localId")
    name: str
    image: str | None = None


class Serie(_TcgdexModel):
    id: str | None = None
    name: str | None = None


class SetDetail(SetBrief):
    """Antwort von ``GET /{lang}/sets/{id}``."""

    serie: Serie | None = None
    release_date: date | None = Field(default=None, alias="releaseDate")
    cards: list[CardBrief] = Field(default_factory=list)


class TcgdexError(Exception):
    """TCGdex nicht erreichbar oder Antwort unbrauchbar. ``status_code`` bei HTTP-Fehlern."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TcgdexClient:
    """Asynchroner TCGdex-Client. Als Kontextmanager verwenden (schließt die Verbindung)."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str) -> object:
        try:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise TcgdexError(f"GET {path}: HTTP {status}", status_code=status) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise TcgdexError(f"GET {path}: {type(exc).__name__}: {exc}") from exc

    async def list_sets(self, language: str) -> list[SetBrief]:
        data = await self._get_json(f"/{language}/sets")
        if not isinstance(data, list):
            raise TcgdexError(f"/{language}/sets: Liste erwartet")
        sets: list[SetBrief] = []
        for item in data:
            try:
                sets.append(SetBrief.model_validate(item))
            except ValidationError:
                continue  # einzelne kaputte Einträge überspringen statt alles abzubrechen
        return sets

    async def get_card(self, language: str, card_id: str) -> dict[str, object]:
        """Kartendetails inkl. ``pricing`` (Rohdaten; die Preislogik wertet sie aus)."""
        data = await self._get_json(f"/{language}/cards/{quote(card_id, safe='')}")
        if not isinstance(data, dict):
            raise TcgdexError(f"/{language}/cards/{card_id}: Objekt erwartet")
        return data

    async def get_set(self, language: str, set_id: str) -> SetDetail:
        # Set-IDs können Sonderzeichen enthalten (z. B. „SM1+“) → als Pfadsegment kodieren.
        data = await self._get_json(f"/{language}/sets/{quote(set_id, safe='')}")
        try:
            return SetDetail.model_validate(data)
        except ValidationError as exc:
            raise TcgdexError(f"/{language}/sets/{set_id}: {exc}") from exc
