"""Englische Kartenbilder aus dem offenen Datensatz von pokemontcg.io.

Der Datensatz liegt als JSON auf GitHub (``PokemonTCG/pokemon-tcg-data``) – kein API-Schlüssel,
keine Ratenbegrenzung der API. Je Set eine Datei mit allen Karten samt Bildadressen
(``images.pokemontcg.io`` bzw. für neue Sets ``images.scrydex.com``).

Die Set-IDs weichen von TCGdex ab (``swsh4.5`` ↔ ``swsh45``, ``sv03.5`` ↔ ``sv3pt5``,
``swsh10.5`` ↔ ``pgo``). :func:`match_sets` ordnet über die ID, den Namen und eine kleine
Ausnahmeliste zu.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.providers.card_images.http import PoliteClient, SourceError

DEFAULT_DATA_URL = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"

# TCGdex-ID → pokemontcg.io-ID, wo weder ID noch Name passen.
SET_ALIASES: Mapping[str, str] = {
    "2011bw": "mcd11",
    "2012bw": "mcd12",
    "2014xy": "mcd14",
    "2015xy": "mcd15",
    "2016xy": "mcd16",
    "2017sm": "mcd17",
    "2018sm": "mcd18",
    "2019sm": "mcd19",
    "2021swsh": "mcd21",
    "2022swsh": "mcd22",
    "swsh3.5": "swsh35",
    "fut2020": "fut20",
    "30th-c": "me55c",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class PtcgSet(_Model):
    id: str
    name: str
    release_date: str | None = Field(default=None, alias="releaseDate")


class PtcgImages(_Model):
    small: str | None = None
    large: str | None = None


class PtcgCard(_Model):
    id: str
    name: str
    number: str
    images: PtcgImages = Field(default_factory=PtcgImages)

    @property
    def image_url(self) -> str | None:
        """Große Fassung (die App leitet daraus die kleine ab)."""
        return self.images.large or self.images.small


@dataclass(frozen=True)
class SetRef:
    """Ein Set unseres Katalogs (TCGdex-ID, englischer Name, falls bekannt)."""

    external_id: str
    name: str | None


def normalize_set_id(set_id: str) -> list[str]:
    """Mögliche pokemontcg.io-IDs zu einer TCGdex-ID.

    ``sv03.5`` → ``["sv3pt5", "sv35"]``, ``swsh4.5sv`` → ``["swsh4pt5sv", "swsh45sv"]``,
    ``me01`` → ``["me1"]``.
    """
    base = re.sub(r"(?<=[a-z])0+(?=\d)", "", set_id.lower())
    variants = [base.replace(".", "pt"), base.replace(".", "")]
    return list(dict.fromkeys(variants))


def normalize_set_name(name: str) -> str:
    """Vergleichbarer Setname: ohne Akzente, Satzzeichen und Leerzeichen, „&“ = „and“."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower().replace("&", "and"))


def match_sets(ours: Iterable[SetRef], theirs: Iterable[PtcgSet]) -> dict[str, str]:
    """Ordnet unsere Sets den pokemontcg.io-Sets zu (TCGdex-ID → pokemontcg.io-ID).

    Reihenfolge: Ausnahmeliste, ID, Name. Jedes pokemontcg.io-Set wird höchstens einmal
    vergeben; ein ID-Treffer hat Vorrang vor einem Namenstreffer.
    """
    their_list = list(theirs)
    by_id = {item.id: item for item in their_list}
    by_name: dict[str, str] = {}
    for item in their_list:
        by_name.setdefault(normalize_set_name(item.name), item.id)

    our_list = list(ours)
    result: dict[str, str] = {}
    used: set[str] = set()
    for ref in our_list:  # 1. Ausnahmen und IDs
        alias = SET_ALIASES.get(ref.external_id)
        candidates = [alias] if alias else normalize_set_id(ref.external_id)
        for candidate in candidates:
            if candidate in by_id and candidate not in used:
                result[ref.external_id] = candidate
                used.add(candidate)
                break
    for ref in our_list:  # 2. Namen
        if ref.external_id in result or not ref.name:
            continue
        by_name_hit = by_name.get(normalize_set_name(ref.name))
        if by_name_hit is not None and by_name_hit not in used:
            result[ref.external_id] = by_name_hit
            used.add(by_name_hit)
    return result


class PokemontcgDataset:
    """Liest Sets und Karten aus dem GitHub-Datensatz."""

    def __init__(self, client: PoliteClient, base_url: str = DEFAULT_DATA_URL) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def sets(self) -> list[PtcgSet]:
        data = await self._client.get_json(f"{self._base_url}/sets/en.json")
        if not isinstance(data, list):
            raise SourceError("pokemontcg.io: Set-Liste erwartet")
        return _valid(PtcgSet, data)

    async def cards(self, set_id: str) -> list[PtcgCard]:
        data = await self._client.get_json(f"{self._base_url}/cards/en/{set_id}.json")
        if not isinstance(data, list):
            raise SourceError(f"pokemontcg.io: Kartenliste für {set_id} erwartet")
        return _valid(PtcgCard, data)


def _valid[M: _Model](model: type[M], items: list[object]) -> list[M]:
    result: list[M] = []
    for item in items:
        try:
            result.append(model.model_validate(item))
        except ValidationError:
            continue  # einzelne kaputte Einträge überspringen
    return result
