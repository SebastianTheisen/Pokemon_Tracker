"""Kartendatenbank Taiwan (traditionelles Chinesisch) ``asia.pokemon-card.com/tw``.

* Liste: ``/tw/card-search/list/?pageNo=N`` (HTML, 20 Karten je Seite) mit Links
  ``/tw/card-search/detail/{id}/`` und Bildern ``/tw/card-img/tw00019913.png``.
* Detail: ``/tw/card-search/detail/{id}/`` – Name in ``<h1 class="pageHeader cardDetail">``
  (davor die Entwicklungsstufe, z. B. „基礎“), Nummer in ``class="collectorNumber"``.

Den Setcode suchen wir auf der Detailseite an mehreren Stellen (Link auf die Setsuche,
Set-Symbol). Ohne Setcode wird über Nummer, Setgröße und Name zugeordnet.
"""

from __future__ import annotations

import re

from app.models import ImageSource
from app.providers.card_images.http import PoliteClient
from app.providers.card_images.official import (
    ListPage,
    OfficialDetail,
    OfficialEntry,
    absolute,
    find_number,
    plain_text,
)

BASE_URL = "https://asia.pokemon-card.com"
_DETAIL_LINK = re.compile(r"/tw/card-search/detail/(\d+)/")
_IMG = re.compile(r"<img[^>]+?(?:data-original|data-src|src)=\"([^\"]+)\"", re.S)
_ALT = re.compile(r"<img[^>]+?alt=\"([^\"]*)\"", re.S)
_H1 = re.compile(r'<h1[^>]*class="[^"]*pageHeader[^"]*"[^>]*>(.*?)</h1>', re.S)
_STAGE = re.compile(r'<span[^>]*class="[^"]*evolveMarker[^"]*"[^>]*>.*?</span>', re.S)
_COLLECTOR = re.compile(r'class="[^"]*collectorNumber[^"]*"[^>]*>(.*?)<', re.S)
_CARD_IMAGE = re.compile(r'class="[^"]*cardImage[^"]*".*?<img[^>]+?src="([^"]+)"', re.S)
_SET_PATTERNS = (
    re.compile(r"expansionCodes?=([A-Za-z0-9-]{2,12})"),
    re.compile(r'class="[^"]*expansionSymbol[^"]*".*?<img[^>]+?alt="([A-Za-z0-9-]{2,12})"', re.S),
    re.compile(r"/expansion[^\"']*/([A-Za-z0-9-]{2,12})\.(?:png|jpg|svg)", re.I),
    re.compile(r'class="[^"]*alpha[^"]*"[^>]*>\s*([A-Za-z0-9-]{2,12})\s*<', re.S),
)
# Entwicklungsstufen vor dem Namen, falls sie nicht als eigenes Element markiert sind.
_STAGE_WORDS = ("基礎", "1階進化", "2階進化", "復原", "V進化", "VMAX", "VSTAR", "樂園")


def parse_list(html: str) -> ListPage:
    """Kartenliste einer Seite. Das Bild steht im selben Listeneintrag wie der Link."""
    entries: list[OfficialEntry] = []
    seen: set[str] = set()
    matches = list(_DETAIL_LINK.finditer(html))
    for index, match in enumerate(matches):
        card_id = match.group(1)
        if card_id in seen:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        block = html[match.start() : end]
        image = _IMG.search(block)
        if image is None:
            continue
        alt = _ALT.search(block)
        seen.add(card_id)
        entries.append(
            OfficialEntry(
                official_id=card_id,
                name=plain_text(alt.group(1)) if alt else "",
                image_url=absolute(BASE_URL, image.group(1)),
            )
        )
    return ListPage(entries=entries, max_page=None)


def _clean_name(raw: str) -> str | None:
    text = plain_text(_STAGE.sub(" ", raw))
    for word in _STAGE_WORDS:
        if text.startswith(word + " "):
            text = text[len(word) :].strip()
    return text or None


def parse_detail(html: str) -> OfficialDetail:
    name = _H1.search(html)
    collector = _COLLECTOR.search(html)
    image = _CARD_IMAGE.search(html)
    set_code = next(
        (match.group(1) for pattern in _SET_PATTERNS if (match := pattern.search(html))), None
    )
    return OfficialDetail(
        name=_clean_name(name.group(1)) if name else None,
        number=find_number(plain_text(collector.group(1))) if collector else None,
        set_code=set_code,
        image_url=absolute(BASE_URL, image.group(1)) if image else None,
    )


class PokemonCardTw:
    """Zugriff auf die Datenbank Taiwan (sanft, über :class:`PoliteClient`)."""

    source = ImageSource.POKEMON_CARD_TW.value
    language = "zh-tw"
    host = "asia.pokemon-card.com"

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    async def list_page(self, page: int) -> ListPage:
        response = await self._client.get(
            f"{BASE_URL}/tw/card-search/list/", params={"pageNo": page}
        )
        return parse_list(response.text)

    async def detail(self, official_id: str) -> tuple[OfficialDetail, str]:
        response = await self._client.get(f"{BASE_URL}/tw/card-search/detail/{official_id}/")
        return parse_detail(response.text), response.text
