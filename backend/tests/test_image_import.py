"""Bild-Import: Quellen-Parser, Zuordnung, Bildregeln und ein kompletter Lauf (simuliert)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CardSource,
    ImageImportRun,
    ImageProbe,
    ImageSource,
    OfficialCard,
)
from app.providers.card_images import pokemon_card_jp, pokemon_card_tw
from app.providers.card_images.official import find_number
from app.providers.card_images.pokemon_com import official_image_url
from app.providers.card_images.pokemontcg import PtcgSet, SetRef, match_sets, normalize_set_id
from app.providers.tcgdex import TcgdexClient
from app.services.catalog_numbers import normalize_number
from app.services.catalog_sync import sync_catalog
from app.services.image_import import (
    ImageCandidate,
    _should_replace,
    render_report,
    run_image_import,
)
from tests.fake_tcgdex import FakeTcgdex

PTCG = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"
JP = "https://www.pokemon-card.com"
TW = "https://asia.pokemon-card.com"


# --------------------------------------------------------------------------- pokemontcg.io


@pytest.mark.parametrize(
    ("tcgdex_id", "expected"),
    [
        ("swsh7", ["swsh7"]),
        ("sv03.5", ["sv3pt5", "sv35"]),
        ("swsh4.5sv", ["swsh4pt5sv", "swsh45sv"]),
        ("me01", ["me1"]),
        ("swsh12.5gg", ["swsh12pt5gg", "swsh125gg"]),
    ],
)
def test_normalize_set_id(tcgdex_id: str, expected: list[str]) -> None:
    assert normalize_set_id(tcgdex_id) == expected


def test_match_sets_by_id_alias_and_name() -> None:
    theirs = [
        PtcgSet(id="swsh7", name="Evolving Skies"),
        PtcgSet(id="sv3pt5", name="151"),
        PtcgSet(id="swsh45sv", name="Shining Fates Shiny Vault"),
        PtcgSet(id="pgo", name="Pokémon GO"),
        PtcgSet(id="mcd22", name="McDonald's Collection 2022"),
        PtcgSet(id="swsh35", name="Champion's Path"),
    ]
    ours = [
        SetRef("swsh7", "Evolving Skies"),
        SetRef("sv03.5", "151"),
        SetRef("swsh4.5sv", "Shining Fates Shiny Vault"),
        SetRef("swsh10.5", "Pokemon GO"),  # Name ohne Akzent
        SetRef("2022swsh", "McDonald's Collection 2022"),
        SetRef("swsh3.5", "Champion's Path"),
        SetRef("tk-hs-r", "HS trainer Kit (Raichu)"),  # gibt es dort nicht
    ]
    assert match_sets(ours, theirs) == {
        "swsh7": "swsh7",
        "sv03.5": "sv3pt5",
        "swsh4.5sv": "swsh45sv",
        "swsh10.5": "pgo",
        "2022swsh": "mcd22",
        "swsh3.5": "swsh35",
    }


def test_match_sets_assigns_each_of_their_sets_once() -> None:
    theirs = [PtcgSet(id="base1", name="Base")]
    ours = [SetRef("base1", "Base"), SetRef("other", "Base")]
    assert match_sets(ours, theirs) == {"base1": "base1"}


# --------------------------------------------------------------------------- pokemon.com


def test_pokemon_com_url_pattern() -> None:
    base = "https://assets.pokemon.com/static-assets/content-assets"
    assert official_image_url("swsh7", "215", "de") == (
        f"{base}/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png"
    )
    assert official_image_url("sv08", "007", "en") == (
        f"{base}/cms2/img/cards/web/SV08/SV08_EN_7.png"
    )
    assert official_image_url("swsh10tg", "TG24", "de") == (
        f"{base}/cms2-de-de/img/cards/web/SWSH10TG/SWSH10TG_DE_TG24.png"
    )
    assert official_image_url(
        "swsh4.5sv",
        "SV068",
        "de",
    ).endswith("SWSH45SV/SWSH45SV_DE_SV068.png")  # type: ignore[union-attr]
    assert official_image_url("swsh7", "215", "ja") is None
    assert official_image_url("swsh7", "21/5", "de") is None  # nur sichere Zeichen


# --------------------------------------------------------------------------- Japan / Taiwan


JP_LIST: dict[str, Any] = {
    "result": 1,
    "hitCnt": 3,
    "maxPage": 1,
    "cardList": [
        {
            "cardID": "50613",
            "cardThumbFile": "/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg",
            "cardNameAltText": "タマタマ",
            "cardNameViewText": "タマタマ",
        },
        {
            "cardID": "48000",
            "cardThumbFile": "/assets/images/card_images/large/M-P/048000_P_PIKACHUEX.jpg",
            "cardNameAltText": "ピカチュウex",
            "cardNameViewText": "ピカチュウex",
        },
        {
            "cardID": "47000",
            "cardThumbFile": "/assets/images/card_images/large/ZZ9/047000_P_X.jpg",
            "cardNameAltText": "なぞ",
            "cardNameViewText": "なぞ",
        },
        {"cardID": "kaputt", "cardThumbFile": "", "cardNameViewText": ""},
    ],
}


def jp_detail(name: str, number: str) -> str:
    return f"""
    <html><body><section>
      <h1 class="Heading1 mt-20">{name}</h1>
      <div class="subtext Text-fjalla">
        <img class="img-regulation" src="/assets/images/card/regulation_logo_1/H.gif" alt="M6a">
        &nbsp;{number.replace("/", "&nbsp;/&nbsp;")}&nbsp;
      </div>
    </section></body></html>"""


TW_LIST = """
<ul class="list">
  <li class="card"><a href="/tw/card-search/detail/19913/">
    <img class="lazy" data-original="https://asia.pokemon-card.com/tw/card-img/tw00019913.png"
         alt="蛋蛋"></a></li>
  <li class="card"><a href="/tw/card-search/detail/19914/">
    <img src="/tw/card-img/tw00019914.png" alt="皮卡丘"></a></li>
</ul>"""


def tw_detail(card_id: str, name: str, number: str, expansion: str = "SV7a") -> str:
    return f"""
    <h1 class="pageHeader cardDetail"><span class="evolveMarker">基礎</span>
        {name}</h1>
    <div class="cardImage"><img src="/tw/card-img/tw000{card_id}.png"></div>
    <span class="expansionLinkColumn"><a href="/tw/card-search/list/?expansionCodes={expansion}">
      set</a></span>
    <span class="collectorNumber">{number}</span>"""


def test_jp_parsers() -> None:
    page = pokemon_card_jp.parse_list(JP_LIST)
    assert page.max_page == 1
    assert [(e.official_id, e.name, e.set_code) for e in page.entries] == [
        ("50613", "タマタマ", "M6a"),
        ("48000", "ピカチュウex", "M-P"),
        ("47000", "なぞ", "ZZ9"),
    ]
    assert page.entries[0].image_url == (
        f"{JP}/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg"
    )
    detail = pokemon_card_jp.parse_detail(jp_detail("タマタマ", "001/103"))
    assert (detail.name, detail.number) == ("タマタマ", "001/103")


def test_tw_parsers() -> None:
    page = pokemon_card_tw.parse_list(TW_LIST)
    assert [(e.official_id, e.name, e.image_url) for e in page.entries] == [
        ("19913", "蛋蛋", f"{TW}/tw/card-img/tw00019913.png"),
        ("19914", "皮卡丘", f"{TW}/tw/card-img/tw00019914.png"),
    ]
    detail = pokemon_card_tw.parse_detail(tw_detail("19913", "蛋蛋", "001/103"))
    assert (detail.name, detail.number, detail.set_code) == ("蛋蛋", "001/103", "SV7a")
    assert detail.image_url == f"{TW}/tw/card-img/tw00019913.png"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("001 / 103", "001/103"),
        ("132/M-P", "132/M-P"),
        ("SV001/SV-P", "SV001/SV-P"),
        ("ohne Nummer", None),
    ],
)
def test_find_number(text: str, expected: str | None) -> None:
    assert find_number(text) == expected


# --------------------------------------------------------------------------- Bildregeln


def _candidate(language: str = "de", source: ImageSource = ImageSource.POKEMON_COM) -> Any:
    return ImageCandidate(card_id=1, url="https://neu", language=language, source=source)


@pytest.mark.parametrize(
    ("image_url", "image_language", "image_source", "candidate", "expected"),
    [
        (None, None, None, _candidate("en", ImageSource.POKEMONTCG), True),  # gar kein Bild
        ("https://tcgdex", None, None, _candidate(), False),  # TCGdex bleibt
        ("https://en", "en", "fallback", _candidate("de"), True),  # eigene Sprache ersetzt
        ("https://en", "en", "fallback", _candidate("en", ImageSource.POKEMONTCG), False),
        ("https://alt", None, "pokemon.com", _candidate("de"), True),  # Adresse aktualisiert
        ("https://neu", None, "pokemon.com", _candidate("de"), False),  # unverändert
        ("https://de", None, "pokemon.com", _candidate("en", ImageSource.POKEMONTCG), False),
    ],
)
def test_should_replace(
    image_url: str | None,
    image_language: str | None,
    image_source: str | None,
    candidate: ImageCandidate,
    expected: bool,
) -> None:
    assert (
        _should_replace(
            card_language="de",
            image_url=image_url,
            image_language=image_language,
            image_source=image_source,
            candidate=candidate,
        )
        is expected
    )


# --------------------------------------------------------------------------- Katalog-Import


async def test_tcgdex_sync_keeps_images_from_other_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake = FakeTcgdex()
    for card in fake.catalog["de"]["swsh7"]["cards"]:
        card["image"] = None
    fake.catalog["en"]["swsh7"]["cards"][3]["image"] = None  # Charizard ohne Bild

    async def sync() -> None:
        async with TcgdexClient(
            base_url="https://api.tcgdex.net/v2", user_agent="t", transport=fake.transport()
        ) as client:
            await sync_catalog(client, session_factory, ["de", "en"], full=True)

    await sync()
    async with session_factory() as session:
        de = {
            card.number: card
            for card in await session.scalars(select(Card).where(Card.language == "de"))
        }
        assert de["215"].image_source == ImageSource.FALLBACK  # englisches Ersatzbild
        de["215"].image_url = "https://assets.pokemon.com/x/SWSH7_DE_215.png"
        de["215"].image_language = None
        de["215"].image_source = ImageSource.POKEMON_COM.value
        await session.commit()

    await sync()  # TCGdex liefert weiter kein Bild → offizielles Bild bleibt
    async with session_factory() as session:
        rows = {
            card.number: card
            for card in await session.scalars(select(Card).where(Card.language == "de"))
        }
    assert rows["215"].image_url == "https://assets.pokemon.com/x/SWSH7_DE_215.png"
    assert rows["215"].image_source == "pokemon.com"
    assert rows["188"].image_source == "fallback"  # Ersatzbild neu bestimmt
    assert rows["007"].image_url is None  # kein Bild in keiner Sprache

    fake.catalog["de"]["swsh7"]["cards"][2]["image"] = "https://assets.tcgdex.net/de/swsh/swsh7/215"
    await sync()  # jetzt hat TCGdex ein eigenes Bild → hat Vorrang
    async with session_factory() as session:
        card = await session.scalar(select(Card).where(Card.language == "de", Card.number == "215"))
        assert card is not None
        assert (card.image_url, card.image_source, card.image_language) == (
            "https://assets.tcgdex.net/de/swsh/swsh7/215",
            None,
            None,
        )


# --------------------------------------------------------------------------- kompletter Lauf


async def _seed(factory: async_sessionmaker[AsyncSession]) -> dict[str, Card]:
    """Katalog: EN/DE-Set ohne Bilder, japanisches Set M6a und Promo-Set M-P."""
    async with factory() as session:
        sets = {
            ("swsh4.5sv", "en"): CardSet(
                external_id="swsh4.5sv", language="en", name="Shining Fates Shiny Vault"
            ),
            ("swsh4.5sv", "de"): CardSet(
                external_id="swsh4.5sv", language="de", name="Glänzendes Schicksal Shiny Vault"
            ),
            ("M6a", "ja"): CardSet(
                external_id="M6a", language="ja", name="メガドリームex", card_count_official=103
            ),
            ("M-P", "ja"): CardSet(external_id="M-P", language="ja", name="プロモ"),
            ("SV7a", "zh-tw"): CardSet(
                external_id="SV7a", language="zh-tw", name="樂園騰龍", card_count_official=64
            ),
        }
        session.add_all(sets.values())
        await session.flush()

        def card(set_key: tuple[str, str], number: str, name: str, ext: str) -> Card:
            return Card(
                external_id=ext,
                language=set_key[1],
                set_id=sets[set_key].id,
                number=number,
                number_norm=normalize_number(number),
                name=name,
            )

        cards = {
            "en68": card(("swsh4.5sv", "en"), "SV068", "Eiscue", "swsh4.5sv-SV068"),
            "de68": card(("swsh4.5sv", "de"), "SV068", "Kubuin", "swsh4.5sv-SV068"),
            "de84": card(("swsh4.5sv", "de"), "SV084", "Pelzebub", "swsh4.5sv-SV084"),
            "ja1": card(("M6a", "ja"), "001", "タマタマ", "M6a-001"),
            "tw1": card(("SV7a", "zh-tw"), "001", "蛋蛋", "SV7a-001"),
        }
        session.add_all(cards.values())
        await session.commit()
        return cards


class FakeSources:
    """Simuliert pokemontcg.io (GitHub), pokemon.com und die Datenbanken JP/TW."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.official_pngs = {
            "https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/"
            "SWSH45SV/SWSH45SV_DE_SV068.png"
        }

    def handler(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911 – ein Fall je Server
        url = str(request.url.copy_with(query=None))
        self.requests.append(str(request.url))
        if url == f"{PTCG}/sets/en.json":
            return httpx.Response(
                200, json=[{"id": "swsh45sv", "name": "Shining Fates Shiny Vault"}]
            )
        if url == f"{PTCG}/cards/en/swsh45sv.json":
            cards = [
                {
                    "id": f"swsh45sv-SV0{n}",
                    "name": name,
                    "number": f"SV0{n}",
                    "images": {
                        "small": f"https://images.pokemontcg.io/swsh45sv/SV0{n}.png",
                        "large": f"https://images.pokemontcg.io/swsh45sv/SV0{n}_hires.png",
                    },
                }
                for n, name in ((68, "Eiscue"), (84, "Grimmsnarl"))
            ]
            return httpx.Response(200, content=json.dumps(cards))
        if request.url.host == "assets.pokemon.com":
            if url in self.official_pngs:
                return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")
            return httpx.Response(404, headers={"content-type": "text/html"}, text="nope")
        if url == f"{JP}/card-search/resultAPI.php":
            return httpx.Response(200, json=JP_LIST)
        if url.startswith(f"{JP}/card-search/details.php/card/"):
            card_id = url.rsplit("/", 1)[1]
            detail = {
                "50613": ("タマタマ", "001/103"),
                "48000": ("ピカチュウex", "132/M-P"),
                "47000": ("なぞ", "005/050"),
            }[card_id]
            return httpx.Response(200, text=jp_detail(*detail))
        if url == f"{TW}/tw/card-search/list/":
            page = int(request.url.params.get("pageNo", "1"))
            return httpx.Response(200, text=TW_LIST if page == 1 else "<ul></ul>")
        if url.startswith(f"{TW}/tw/card-search/detail/"):
            card_id = url.rstrip("/").rsplit("/", 1)[1]
            name, number = {"19913": ("蛋蛋", "001/064"), "19914": ("皮卡丘", "099/064")}[card_id]
            return httpx.Response(200, text=tw_detail(card_id, name, number))
        return httpx.Response(404)


@pytest.fixture
def fast_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"image_import_request_interval_seconds": 0})


async def test_full_run_fills_images_from_all_sources(
    session_factory: async_sessionmaker[AsyncSession], fast_settings: Settings
) -> None:
    cards = await _seed(session_factory)
    fake = FakeSources()

    report = await run_image_import(
        session_factory, fast_settings, transport=httpx.MockTransport(fake.handler)
    )

    by_source = {item.source: item for item in report.sources}
    assert by_source["pokemontcg"].images_set == 3  # EN eigene Sprache, 2× DE als Ersatz
    assert by_source["pokemon.com"].images_set == 1  # DE-Bild ersetzt englisches Ersatzbild
    assert by_source["pokemon-card.com"].cards_created == 1  # Promo 132/M-P
    assert by_source["pokemon-card.com"].unmatched == 1  # Set ZZ9 unbekannt → nicht angelegt
    assert by_source["asia.pokemon-card.com/tw"].cards_created == 1  # 099/064 im bekannten Set
    async with session_factory() as session:
        rows = {
            card.id: card
            for card in await session.scalars(
                select(Card).execution_options(populate_existing=True)
            )
        }
        assert rows[cards["en68"].id].image_url == (
            "https://images.pokemontcg.io/swsh45sv/SV068_hires.png"
        )
        assert rows[cards["en68"].id].image_language is None
        de68 = rows[cards["de68"].id]
        assert de68.image_url is not None and de68.image_url.endswith("SWSH45SV_DE_SV068.png")
        assert (de68.image_language, de68.image_source) == (None, "pokemon.com")
        de84 = rows[cards["de84"].id]
        assert (de84.image_language, de84.image_source) == ("en", "pokemontcg")
        ja1 = rows[cards["ja1"].id]
        assert ja1.image_url == f"{JP}/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg"
        assert ja1.image_source == "pokemon-card.com"
        promo = next(card for card in rows.values() if card.external_id == "M-P-132")
        assert (promo.source, promo.name, promo.number) == (
            CardSource.OFFICIAL,
            "ピカチュウex",
            "132",
        )
        assert rows[cards["tw1"].id].image_url == f"{TW}/tw/card-img/tw00019913.png"
        assert await session.scalar(select(func.count()).select_from(OfficialCard)) == 5
        probes = (await session.scalars(select(ImageProbe))).all()
        # Nur DE-Karten brauchten noch ein Bild in eigener Sprache; SV084 gibt es dort nicht.
        assert {(p.url.rsplit("_", 1)[1], p.found) for p in probes} == {
            ("SV068.png", True),
            ("SV084.png", False),
        }
        run = await session.scalar(select(ImageImportRun))
        assert run is not None and run.finished_at is not None
    assert "pokemon-card.com" in render_report(report)

    # Zweiter Lauf: Detailseiten werden nicht erneut geladen, nichts ändert sich.
    fake.requests.clear()
    again = await run_image_import(
        session_factory, fast_settings, transport=httpx.MockTransport(fake.handler)
    )
    assert not [url for url in fake.requests if "details.php" in url or "/detail/" in url]
    assert all(item.images_set == 0 for item in again.sources)
    assert all(item.cards_created == 0 for item in again.sources)


async def test_detail_pages_without_numbers_abort_without_saving(
    session_factory: async_sessionmaker[AsyncSession], fast_settings: Settings
) -> None:
    await _seed(session_factory)
    many = {
        **JP_LIST,
        "cardList": [
            {
                "cardID": str(10000 + i),
                "cardThumbFile": f"/assets/images/card_images/large/M6a/0{10000 + i}_P_X.jpg",
                "cardNameViewText": "X",
            }
            for i in range(25)
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "resultAPI" in str(request.url):
            return httpx.Response(200, json=many)
        return httpx.Response(200, text="<main>ganz neues Layout</main>")

    report = await run_image_import(
        session_factory, fast_settings, sources=["jp"], transport=httpx.MockTransport(handler)
    )

    jp = report.sources[0]
    assert jp.details_fetched == 20
    assert any("keine Kartennummer" in error for error in jp.errors)
    async with session_factory() as session:
        fetched = await session.scalar(
            select(func.count())
            .select_from(OfficialCard)
            .where(OfficialCard.detail_fetched_at.is_not(None))
        )
    assert fetched == 0  # beim nächsten Lauf (mit korrigiertem Parser) erneut versuchen


async def test_old_cards_without_number_are_stored_not_aborted(
    session_factory: async_sessionmaker[AsyncSession], fast_settings: Settings
) -> None:
    await _seed(session_factory)
    old_cards = {
        **JP_LIST,
        "cardList": [
            {
                "cardID": str(900 + i),
                "cardThumbFile": f"/assets/images/card_images/large/PMCG/000{900 + i}_X.jpg",
                "cardNameViewText": "X",
            }
            for i in range(25)
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "resultAPI" in str(request.url):
            return httpx.Response(200, json=old_cards)
        return httpx.Response(200, text="<h1>リザードン</h1>")  # Name, aber keine Nummer

    report = await run_image_import(
        session_factory, fast_settings, sources=["jp"], transport=httpx.MockTransport(handler)
    )

    jp = report.sources[0]
    assert (jp.details_fetched, jp.details_without_number, jp.errors) == (25, 25, [])
    async with session_factory() as session:
        fetched = await session.scalar(
            select(func.count())
            .select_from(OfficialCard)
            .where(OfficialCard.detail_fetched_at.is_not(None))
        )
    assert fetched == 25


async def test_dry_run_saves_nothing(
    session_factory: async_sessionmaker[AsyncSession], fast_settings: Settings
) -> None:
    cards = await _seed(session_factory)
    report = await run_image_import(
        session_factory,
        fast_settings,
        dry_run=True,
        transport=httpx.MockTransport(FakeSources().handler),
    )
    assert report.dry_run
    jp = next(item for item in report.sources if item.source == "pokemon-card.com")
    assert jp.details_fetched == 3
    assert any("HTML-Ausschnitt" in note for note in jp.notes)
    async with session_factory() as session:
        card = await session.get(Card, cards["en68"].id)
        assert card is not None and card.image_url is None
        assert await session.scalar(select(func.count()).select_from(OfficialCard)) == 0
        assert await session.scalar(select(func.count()).select_from(ImageImportRun)) == 0
