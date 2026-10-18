"""Japanische Kartendatenbank ``www.pokemon-card.com``.

* Liste: ``/card-search/resultAPI.php?keyword=&regulation_sidebar_form=all&page=N`` (JSON,
  ``maxPage``, ``cardList`` mit ``cardID``, ``cardNameViewText``, ``cardThumbFile``). Der
  Bildpfad enthält den Setcode: ``/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg``.
* Detail: ``/card-search/details.php/card/{cardID}`` – Name in ``<h1>``, Nummer in
  ``<div class="subtext">`` („001 / 103“).

Laut Nutzungsbedingungen ist das Weiterverbreiten der Bilder untersagt. Wir speichern nur
die Adresse; die App lädt das Bild direkt von pokemon-card.com (privater Kreis).
"""

from __future__ import annotations

import re

from app.models import ImageSource
from app.providers.card_images.http import PoliteClient, SourceError
from app.providers.card_images.official import (
    ListPage,
    OfficialDetail,
    OfficialEntry,
    absolute,
    find_number,
    plain_text,
)

BASE_URL = "https://www.pokemon-card.com"
_SET_FROM_PATH = re.compile(r"/card_images/[^/]+/([A-Za-z0-9-]+)/")
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_SUBTEXT = re.compile(r'class="subtext[^"]*"[^>]*>(.*?)</div>', re.S)


def set_code_from_image(path: str) -> str | None:
    """``/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg`` → ``M6a``."""
    match = _SET_FROM_PATH.search(path)
    return match.group(1) if match else None


def parse_list(data: object) -> ListPage:
    """Antwort der Such-API → Einträge. Wirft :class:`SourceError` bei fremdem Format."""
    if not isinstance(data, dict) or not isinstance(data.get("cardList"), list):
        raise SourceError("pokemon-card.com: unerwartete Antwort der Suche")
    entries: list[OfficialEntry] = []
    for item in data["cardList"]:
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("cardID") or "").strip()
        thumb = str(item.get("cardThumbFile") or "").strip()
        name = str(item.get("cardNameViewText") or item.get("cardNameAltText") or "").strip()
        if not card_id.isdigit() or not thumb or not name:
            continue
        entries.append(
            OfficialEntry(
                official_id=card_id,
                name=plain_text(name),
                image_url=absolute(BASE_URL, thumb),
                set_code=set_code_from_image(thumb),
            )
        )
    max_page = str(data.get("maxPage") or "")
    return ListPage(entries=entries, max_page=int(max_page) if max_page.isdigit() else None)


def parse_detail(html: str) -> OfficialDetail:
    name = _H1.search(html)
    subtext = _SUBTEXT.search(html)
    return OfficialDetail(
        name=plain_text(name.group(1)) or None if name else None,
        number=find_number(plain_text(subtext.group(1))) if subtext else None,
    )


class PokemonCardJp:
    """Zugriff auf die japanische Datenbank (sanft, über :class:`PoliteClient`)."""

    source = ImageSource.POKEMON_CARD_JP.value
    language = "ja"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    async def list_page(self, page: int) -> ListPage:
        data = await self._client.get_json(
            f"{BASE_URL}/card-search/resultAPI.php",
            params={"keyword": "", "regulation_sidebar_form": "all", "page": page},
        )
        return parse_list(data)

    async def detail(self, official_id: str) -> tuple[OfficialDetail, str]:
        response = await self._client.get(f"{BASE_URL}/card-search/details.php/card/{official_id}")
        return parse_detail(response.text), response.text
