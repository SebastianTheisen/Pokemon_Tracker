# ruff: noqa: E501 – nachgebaute HTML-Zeilen der Kartenliste bleiben am Stück
"""One Piece als zweites Spiel: Kartenliste einlesen, Cardmarket (Spiel 18), Preise, Filter.

Die Seiten sind dem Aufbau der offiziellen Kartenliste nachgebaut (Spike
``docs/phase5/onepiece.md``; Selektoren wie im Open-Source-Scraper ``arjunkai/optcg-api``):
``<select id="series">`` mit doppelt kodierten Bezeichnungen, je Karte ein
``<dl class="modalCol" id="OP01-001_p1">``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CmPrice, CmProduct, Game
from app.services.cardmarket_catalog import product_url, run_catalog_import
from app.services.catalog_search import onepiece_number, search_cards
from app.services.onepiece_catalog import (
    OnePieceCatalog,
    Series,
    best_expansion,
    parse_cards,
    parse_series,
    product_code,
    render_report,
)
from app.services.sealed_images import ONEPIECE_KEY, TcgProduct, match_sealed_images
from tests.conftest import RegisterUser
from tests.pricing_helpers import make_card

API = "/api/v1"
OP01_SERIES, PRB01_SERIES, PROMO_SERIES = "569101", "569301", "569801"
OP01_EXPANSION, PRB01_EXPANSION = 5229, 5900

INDEX_EN = """
<form><select name="series" id="series">
  <option value="">ALL</option>
  <option value="569801">Promotion card</option>
  <option value="569301">PREMIUM BOOSTER &lt;br class=&quot;spInline&quot;&gt;-ONE PIECE CARD THE BEST- [PRB-01]</option>
  <option value="569101">BOOSTER PACK &lt;br class=&quot;spInline&quot;&gt;-ROMANCE DAWN- [OP-01]</option>
</select></form>
"""
INDEX_JA = """
<select id="series">
  <option value="550101">ブースターパック ROMANCE DAWN【OP-01】</option>
</select>
"""


def card_block(card_id: str, name: str, rarity: str, category: str = "CHARACTER") -> str:
    number = card_id.split("_", maxsplit=1)[0]
    return f"""
<a class="modalOpen" data-src="#{card_id}"><img data-src="../images/cardlist/card/{card_id}.png?261016" class="lazy"></a>
<dl class="modalCol" id="{card_id}">
  <dt>
    <div class="infoCol"><span>{number}</span> | <span>{rarity}</span> | <span>{category}</span></div>
    <div class="cardName">{name}</div>
  </dt>
  <dd><div class="backCol"><div class="color"><h3>Color</h3>Red</div></div></dd>
</dl>"""


SERIES_PAGES = {
    OP01_SERIES: "".join(
        [
            card_block("OP01-001", "Roronoa Zoro", "L", "LEADER"),
            card_block("OP01-001_p1", "Roronoa Zoro", "L", "LEADER"),
            card_block("OP01-002", "Trafalgar Law", "L", "LEADER"),
            card_block("OP01-003", "Monkey.D.Luffy", "L", "LEADER"),
            '<dl class="modalCol" id="kaputt"><dt><div class="cardName">x</div></dt></dl>',
        ]
    ),
    # Premium-Booster listet die Karte aus OP01 erneut – sie bleibt in OP01.
    PRB01_SERIES: card_block("OP01-001", "Roronoa Zoro", "L", "LEADER")
    + card_block("OP01-120_p2", "Shanks", "SEC"),
    PROMO_SERIES: "",
    "550101": card_block("OP01-001", "ロロノア・ゾロ", "L", "LEADER"),
}


def site_transport(requests: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        series = request.url.params.get("series")
        if request.url.path != "/cardlist/":
            return httpx.Response(404)
        if series is None:
            index = INDEX_JA if request.url.host.startswith("www.") else INDEX_EN
            return httpx.Response(200, text=index)
        return httpx.Response(200, text=SERIES_PAGES.get(series, ""))

    return httpx.MockTransport(handler)


async def no_sleep(_seconds: float) -> None:
    return None


def cardmarket_transport() -> httpx.MockTransport:
    """Cardmarket-Downloads für One Piece (Spiel 18): Zoro normal + Parallel, Law, Luffy."""
    products = [
        {"idProduct": 690368, "name": "Roronoa Zoro (OP01-001)", "idExpansion": OP01_EXPANSION},
        {"idProduct": 690369, "name": "Roronoa Zoro (OP01-001)", "idExpansion": OP01_EXPANSION},
        {"idProduct": 690370, "name": "Trafalgar Law (OP01-002)", "idExpansion": OP01_EXPANSION},
        {"idProduct": 690371, "name": "Monkey.D.Luffy (OP01-003)", "idExpansion": OP01_EXPANSION},
        {"idProduct": 800001, "name": "Shanks (OP01-120)", "idExpansion": PRB01_EXPANSION},
        {"idProduct": 800002, "name": "Shanks (OP01-120)", "idExpansion": PRB01_EXPANSION},
    ]
    for product in products:
        product |= {
            "idCategory": 1621,
            "categoryName": "One Piece Single",
            "idMetacard": 415000 + product["idProduct"] % 1000,
            "dateAdded": "2022-12-28 22:11:43",
        }
    sealed = [
        {
            "idProduct": 691244,
            "name": "Romance Dawn Booster Box",
            "idCategory": 1624,
            "categoryName": "One Piece Booster Boxes",
            "idExpansion": OP01_EXPANSION,
            "idMetacard": 0,
            "dateAdded": "2023-01-09 15:43:14",
        }
    ]
    guide = [
        {"idProduct": 690368, "idCategory": 1621, "trend": 2.31, "low": 0.8, "trend-foil": 0},
        {"idProduct": 690369, "idCategory": 1621, "trend": 45.5, "low": 39.0},
        {"idProduct": 691244, "idCategory": 1624, "trend": 410.0, "low": 380.0},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("products_singles_18.json"):
            body: dict[str, Any] = {"createdAt": "2026-10-24T11:13:37+0200", "products": products}
        elif path.endswith("products_nonsingles_18.json"):
            body = {"createdAt": "2026-10-24T11:13:37+0200", "products": sealed}
        elif path.endswith("price_guide_18.json"):
            body = {"createdAt": "2026-10-25T02:47:25+0200", "priceGuides": guide}
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


async def import_all(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> list[str]:
    requests: list[str] = []
    await run_catalog_import(
        session_factory,
        settings,
        tcgdex=None,
        transport=cardmarket_transport(),
        game=Game.ONEPIECE.value,
    )
    catalog = OnePieceCatalog(
        session_factory, settings, transport=site_transport(requests), sleep=no_sleep
    )
    report = await catalog.run()
    assert report.link is not None
    return requests


# --------------------------------------------------------------- Einlesen


def test_series_labels_are_decoded_named_and_grouped() -> None:
    series = parse_series(INDEX_EN)

    assert [s.series_id for s in series] == [PROMO_SERIES, PRB01_SERIES, OP01_SERIES]
    promo, prb, op01 = series
    assert (op01.code, op01.external_id, op01.name, op01.group) == (
        "OP01",
        "op-OP01",
        "Romance Dawn",
        "Booster",
    )
    assert (prb.code, prb.name, prb.group) == (
        "PRB01",
        "One Piece Card The Best",
        "Premium-Booster",
    )
    # Ohne Kürzel: letzte vier Ziffern – in allen Sprachen gleich.
    assert (promo.code, promo.external_id, promo.group) == (None, "op-S9801", "Promos & Sonstiges")
    japanese = parse_series(INDEX_JA)[0]
    assert (japanese.code, japanese.external_id) == ("OP01", "op-OP01")
    assert japanese.name == "ブースターパック Romance Dawn"


def test_series_title_keeps_mixed_case_words() -> None:
    entry = Series("569302", "PREMIUM BOOSTER -ONE PIECE CARD THE BEST vol.2- [PRB-02]", "PRB02")
    assert entry.name == "One Piece Card The Best vol.2"


def test_cards_with_parallels_and_broken_blocks() -> None:
    cards = parse_cards(SERIES_PAGES[OP01_SERIES])

    assert [c.card_id for c in cards] == ["OP01-001", "OP01-001_p1", "OP01-002", "OP01-003"]
    zoro, parallel = cards[0], cards[1]
    assert (zoro.number, zoro.name, zoro.rarity, zoro.category) == (
        "OP01-001",
        "Roronoa Zoro",
        "L",
        "LEADER",
    )
    assert (parallel.number, parallel.display_name, parallel.variant_rank) == (
        "OP01-001",
        "Roronoa Zoro (Parallel)",
        1,
    )
    assert parse_cards(card_block("P-001", "Monkey.D.Luffy", "P"))[0].number == "P-001"


def test_product_codes_and_best_expansion() -> None:
    assert product_code("Roronoa Zoro (OP01-001)") == "OP01-001"
    assert product_code("Nami (P-012) (Gold)") == "P-012"
    assert product_code("Romance Dawn Booster") is None


def test_onepiece_numbers_in_queries() -> None:
    assert onepiece_number("OP01-001") == ("OP01-001", "")
    assert onepiece_number("zoro op01 001") == ("OP01001", "zoro")
    assert onepiece_number("p-001") == ("P-001", "")
    assert onepiece_number("nachtara 215") is None
    assert onepiece_number("PFL077") is None


# ----------------------------------------------------------------- Import


async def test_import_creates_sets_cards_and_links_cardmarket(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    requests = await import_all(session_factory, settings)

    # Startseite + 3 Sets (EN) und Startseite + 1 Set (JP) – je Set genau ein Abruf.
    assert len(requests) == 6
    async with session_factory() as session:
        sets = {
            (s.language, s.external_id): s
            for s in (await session.scalars(select(CardSet).where(CardSet.game == "onepiece")))
        }
        cards = {
            (c.language, c.external_id): c
            for c in (
                await session.scalars(select(Card).join(CardSet).where(CardSet.game == "onepiece"))
            ).unique()
        }

    assert set(sets) == {("en", "op-OP01"), ("en", "op-PRB01"), ("ja", "op-OP01")}
    op01 = sets[("en", "op-OP01")]
    assert (op01.name, op01.series_name, op01.code, op01.card_count_official) == (
        "Romance Dawn",
        "Booster",
        "OP01",
        3,
    )
    assert op01.cardmarket_expansion_id == OP01_EXPANSION
    assert op01.release_date == date(2022, 12, 28)  # aus der Cardmarket-Ausgabe
    zoro = cards[("en", "op-OP01-001")]
    assert zoro.set_id == op01.id  # nicht im später gelisteten Premium-Booster
    assert zoro.number == "OP01-001"
    assert zoro.variants == {"normal": True, "reverse": False, "holo": False}
    assert zoro.image_url == "https://en.onepiece-cardgame.com/images/cardlist/card/OP01-001.png"
    # Normal und Parallel in Produkt-ID-Reihenfolge.
    assert zoro.cardmarket_product_id == 690368
    assert cards[("en", "op-OP01-001_p1")].cardmarket_product_id == 690369
    assert cards[("en", "op-OP01-001_p1")].name == "Roronoa Zoro (Parallel)"
    # Japanische Karte: dasselbe Produkt (Cardmarket führt One Piece sprachübergreifend).
    assert cards[("ja", "op-OP01-001")].cardmarket_product_id == 690368
    # Shanks: 2 Produkte, aber nur die Parallel-Fassung gelistet → nicht raten.
    assert cards[("en", "op-OP01-120_p2")].cardmarket_product_id is None


async def test_dry_run_stores_nothing(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    catalog = OnePieceCatalog(
        session_factory, settings, transport=site_transport([]), sleep=no_sleep
    )
    report = await catalog.run(["en"], dry_run=True)

    assert report.languages[0].cards == 5  # OP01: 4, PRB01: Shanks (Zoro ist doppelt)
    assert report.languages[0].duplicates == 1
    assert report.languages[0].empty_series == ["Promotion card"]
    assert "Probelauf" in render_report(report)
    async with session_factory() as session:
        assert (await session.scalar(select(CardSet).where(CardSet.game == "onepiece"))) is None


async def test_onepiece_guide_import_keeps_pokemon_prices(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with session_factory() as session:
        session.add(
            CmPrice(
                id_product=574273,
                metrics={"trend": 1805.9},
                updated_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
        )
        await session.commit()

    await import_all(session_factory, settings)

    async with session_factory() as session:
        assert await session.get(CmPrice, 574273) is not None  # Pokémon-Preis bleibt
        booster_box = await session.get(CmProduct, 691244)
        assert booster_box is not None and booster_box.game == "onepiece"
        assert (await session.get_one(CmPrice, 690368)).game == "onepiece"


def test_cardmarket_links_point_to_the_game() -> None:
    assert product_url(690368, "onepiece") == (
        "https://www.cardmarket.com/de/OnePiece/Products?idProduct=690368"
    )
    assert "/Pokemon/" in product_url(574273)


def test_best_expansion_needs_half_of_the_numbers() -> None:
    from app.services.onepiece_catalog import _Products  # noqa: PLC0415

    products = _Products()
    products.codes_by_expansion[1] = {"OP01-001", "OP01-002", "OP01-003"}
    products.codes_by_expansion[2] = {"OP01-001", "EB01-001", "EB01-002", "EB01-003"}
    assert best_expansion({"OP01-001", "OP01-002"}, products) == 1
    assert best_expansion({"OP01-001", "ST01-001", "ST01-002"}, products) is None


# --------------------------------------------------------- Preise und Filter


async def test_onepiece_card_prices_come_from_the_guide(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    price_provider: Any,
) -> None:
    user = await register_user("nami@example.com")
    await import_all(session_factory, settings)
    async with session_factory() as session:
        parallel = await session.scalar(
            select(Card).where(Card.external_id == "op-OP01-001_p1", Card.language == "en")
        )
    assert parallel is not None

    body = (await client.get(f"{API}/cards/{parallel.id}/prices", headers=user.headers)).json()

    offer = body["offers"][0]
    assert offer["metrics"]["trend"] == "45.50"
    assert offer["url"] == "https://www.cardmarket.com/de/OnePiece/Products?idProduct=690369"
    assert price_provider.calls == []  # Pokémon-Quellen werden gar nicht gefragt


async def test_search_and_collection_filter_by_game(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    user = await register_user("ruffy@example.com")
    await import_all(session_factory, settings)
    pokemon = await make_card(session_factory)
    async with session_factory() as session:
        hits = await search_cards(session, "OP01-001", language="en")
        assert [h.card.external_id for h in hits] == ["op-OP01-001", "op-OP01-001_p1"]
        zoro = hits[0].card
        assert await search_cards(session, "zoro", game="pokemon") == []
        assert {h.card.external_id for h in await search_cards(session, "zoro", game="onepiece")}

    for card_id in (zoro.id, pokemon.id):
        response = await client.post(
            f"{API}/collection/items", json={"card_id": str(card_id)}, headers=user.headers
        )
        assert response.status_code == 201, response.text

    async def names(**params: str) -> list[str]:
        response = await client.get(f"{API}/collection/items", params=params, headers=user.headers)
        return sorted(item["card"]["name"] for item in response.json()["items"])

    assert await names() == ["Nachtara VMAX", "Roronoa Zoro"]
    assert await names(game="onepiece") == ["Roronoa Zoro"]
    assert await names(game="pokemon") == ["Nachtara VMAX"]

    dashboard = (await client.get(f"{API}/dashboard", headers=user.headers)).json()
    assert set(dashboard["by_game"]) == {"pokemon", "onepiece"}
    assert Decimal(dashboard["by_game"]["onepiece"]) == Decimal("2.31")
    only_onepiece = (
        await client.get(f"{API}/dashboard", params={"game": "onepiece"}, headers=user.headers)
    ).json()
    assert only_onepiece["positions"] == 1
    assert only_onepiece["by_game"] == {}

    sets = (
        await client.get(f"{API}/sets", params={"game": "onepiece"}, headers=user.headers)
    ).json()
    assert {s["external_id"] for s in sets} == {"op-OP01", "op-PRB01"}
    assert all(s["game"] == "onepiece" and s["translated_name"] is None for s in sets)


async def test_sealed_images_never_cross_games_or_touch_singles(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await import_all(session_factory, settings)
    cdn = "https://tcgplayer-cdn.tcgplayer.com/product"
    catalog = [
        TcgProduct(450086, "Romance Dawn - Booster Box", f"{cdn}/450086_200w.jpg", ONEPIECE_KEY),
        # Gleicher Name im Pokémon-Katalog – darf One Piece nie treffen (und umgekehrt).
        TcgProduct(1, "Romance Dawn Booster Box", f"{cdn}/1_200w.jpg", "en"),
    ]

    async with session_factory() as session:
        report = await match_sealed_images(session, catalog)
        await session.commit()

    assert report.sealed == 1  # nur die Booster Box, keine der One-Piece-Einzelkarten
    async with session_factory() as session:
        box = await session.get_one(CmProduct, 691244)
        single = await session.get_one(CmProduct, 690368)
    assert box.image_url == f"{cdn}/450086_200w.jpg"
    assert single.image_url is None


def test_double_set_codes_use_the_first_code() -> None:
    page = """<select id="series">
      <option value="569114">BOOSTER PACK -THE AZURE SEA&#39;S SEVEN- [OP14-EB04]</option>
      <option value="550114">ブースターパック 蒼海の七傑【OP-14】</option>
    </select>"""
    english, japanese = parse_series(page)
    assert (english.code, english.external_id, english.group) == ("OP14", "op-OP14", "Booster")
    assert japanese.external_id == english.external_id


async def test_import_removes_sets_left_without_cards(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with session_factory() as session:
        session.add(CardSet(external_id="op-OP14EB04", language="en", game="onepiece", name="Alt"))
        await session.commit()

    catalog = OnePieceCatalog(
        session_factory, settings, transport=site_transport([]), sleep=no_sleep
    )
    report = await catalog.run(["en"])

    assert report.sets_removed == 1
    assert "Leere Sets entfernt: 1" in render_report(report)
    async with session_factory() as session:
        names = set(await session.scalars(select(CardSet.external_id)))
    assert "op-OP14EB04" not in names
    assert {"op-OP01", "op-PRB01"} <= names
