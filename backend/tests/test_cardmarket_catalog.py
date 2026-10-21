"""Cardmarket-Katalog: Einlesen, Zwillinge, Import, Umhängen der Karten, Auswahl in der App.

Modell wie im Spike (``docs/phase5/cardmarket_mapping.md``): Zum 30th-Jubiläum hat Cardmarket
gleichzeitig die japanische (6602) und die vereinfacht-chinesische Ausgabe (6603) angelegt;
TCGdex verknüpft ``ja/M6a`` mit 6603. Glurak hat in beiden die Metakarte 211560.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    AuditLog,
    Card,
    CardPriceLink,
    CardSet,
    CmExpansion,
    CmImport,
    CmPrice,
    CmProduct,
    PriceCheck,
    PricePoint,
)
from app.providers.pricing import PriceQuote
from app.providers.pricing.tcgdex_prices import product_id_from_url
from app.providers.tcgdex import TcgdexClient, TcgdexError
from app.services.cardmarket_catalog import (
    CatalogError,
    ExpansionStats,
    ProductRow,
    catalog_status,
    expansion_stats,
    find_twins,
    link_sets,
    parse_created_at,
    parse_price_guide,
    parse_products,
    remap_product,
    render_status,
    run_catalog_import,
)
from app.worker import CARDMARKET_START_DELAY, next_catalog_import
from tests.conftest import RegisterUser
from tests.pricing_helpers import UPDATED, FakeProvider, cardmarket

API = "/api/v1"
GUIDE_CREATED = "2026-10-20T02:44:49+0200"
CHINESE_GLURAK = 908315
JAPANESE_GLURAK = 907902


def product(
    id_product: int, expansion: int, metacard: int, name: str, added: str = "2026-09-10 14:11:55"
) -> dict[str, Any]:
    return {
        "idProduct": id_product,
        "name": name,
        "idCategory": 51,
        "categoryName": "Pokémon Single",
        "idExpansion": expansion,
        "idMetacard": metacard,
        "dateAdded": added,
    }


def guide(
    id_product: int, trend: float, low: float | None, **extra: float | None
) -> dict[str, Any]:
    return {"idProduct": id_product, "idCategory": 51, "trend": trend, "low": low, **extra}


# Japanisch (6602) und Chinesisch (6603) mit denselben drei Karten; Pikachu hat zwei Versionen.
CN_ADDED = "2026-09-11 10:28:18"
# Japanisch (6602) und Chinesisch (6603) mit fast denselben Karten: Pikachu in zwei Versionen,
# Mew nur japanisch, Evoli nur chinesisch, dazu zehn gemeinsame Karten.
PRODUCTS = [
    product(JAPANESE_GLURAK, 6602, 211560, "Charizard [Energy Burn | Fire Spin]"),
    product(907903, 6602, 300001, "Pikachu [Gnaw]"),
    product(907904, 6602, 300001, "Pikachu [Gnaw]"),
    product(907905, 6602, 300002, "Mew [Psywave]"),
    product(CHINESE_GLURAK, 6603, 211560, "Charizard [Energy Burn | Fire Spin]", CN_ADDED),
    product(908316, 6603, 300001, "Pikachu [Gnaw]", CN_ADDED),
    product(908317, 6603, 300001, "Pikachu [Gnaw]", CN_ADDED),
    product(908318, 6603, 300003, "Eevee [Tackle]", CN_ADDED),
    *(product(910000 + n, 6602, 300100 + n, f"Karte {n}") for n in range(10)),
    *(product(920000 + n, 6603, 300100 + n, f"Karte {n}", CN_ADDED) for n in range(10)),
    # Eigene Ausgabe (z. B. Trainer Gallery): gleiche Metakarte, aber keine Sprachfassung.
    product(930000, 7000, 211560, "Charizard [Energy Burn | Fire Spin]", "2026-01-05 09:00:00"),
    # Grundset 1999: dieselbe Glurak-Metakarte, aber Jahrzehnte früher – kein Zwilling.
    product(273699, 1523, 211560, "Charizard [Energy Burn | Fire Spin]", "0000-00-00 00:00:00"),
]
SEALED = [
    {
        "idProduct": 700001,
        "name": "Prismatic Evolutions Elite Trainer Box",
        "idCategory": 61,
        "categoryName": "Pokémon Elite Trainer Box",
        "idExpansion": 6100,
        "idMetacard": 0,
        "dateAdded": "2025-01-10 10:00:00",
    },
    {
        "idProduct": 700002,
        "name": "Prismatic Evolutions Booster Bundle",
        "idCategory": 52,
        "categoryName": "Pokémon Booster",
        "idExpansion": 6100,
        "idMetacard": 0,
        "dateAdded": "2025-01-10 10:00:00",
    },
]
GUIDE = [
    guide(JAPANESE_GLURAK, 158.67, 120.0, **{"avg7": 150.0, "avg30": 160.0}),
    guide(CHINESE_GLURAK, 66.34, 70.0),
    guide(907904, 12.5, 9.0, **{"trend-holo": 20.0}),
    guide(908316, 0, None),  # ohne Preis → wird nicht gespeichert
    guide(700001, 95.0, 89.0, **{"avg7": 99.0, "avg30": 110.0}),
]


def catalog_transport(
    products: list[dict[str, Any]] | None = None,
    prices: list[dict[str, Any]] | None = None,
    *,
    status: int = 200,
    guide_created: str = GUIDE_CREATED,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        if request.url.path.endswith("products_singles_6.json"):
            body = {
                "version": 1,
                "createdAt": "2026-10-20T14:24:46+0200",
                "products": PRODUCTS if products is None else products,
            }
        elif request.url.path.endswith("products_nonsingles_6.json"):
            body = {"version": 1, "createdAt": "2026-10-20T14:24:49+0200", "products": SEALED}
        elif request.url.path.endswith("price_guide_6.json"):
            body = {
                "version": 1,
                "createdAt": guide_created,
                "priceGuides": GUIDE if prices is None else prices,
            }
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


async def make_set_card(
    factory: async_sessionmaker[AsyncSession],
    *,
    set_id: str = "SV-P30",
    language: str = "ja",
    number: str = "137",
    name: str = "リザードン",
    external_id: str | None = None,
) -> Card:
    async with factory() as session:
        card_set = await session.scalar(
            select(CardSet).where(CardSet.external_id == set_id, CardSet.language == language)
        )
        if card_set is None:
            card_set = CardSet(external_id=set_id, language=language, name="30th CELEBRATION")
            session.add(card_set)
            await session.flush()
        card = Card(
            external_id=external_id or f"{set_id}-{number}",
            language=language,
            set_id=card_set.id,
            number=number,
            number_norm=number.lstrip("0") or "0",
            name=name,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card, ["card_set"])
        return card


def quotes_for(product_id: int, trend: str = "66.34") -> list[PriceQuote]:
    url = f"https://www.cardmarket.com/de/Pokemon/Products?idProduct={product_id}"
    return [
        replace(cardmarket("trend", trend), source_url=url),
        replace(cardmarket("low", "70"), source_url=url),
    ]


@pytest.fixture
async def imported(session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    summary = await run_catalog_import(
        session_factory, settings, tcgdex=None, transport=catalog_transport()
    )
    assert summary.error is None


# ------------------------------------------------------------------- Einlesen


def test_parse_products_skips_broken_rows_and_unknown_dates() -> None:
    created, rows = parse_products(
        {
            "createdAt": "2026-10-20T14:24:46+0200",
            "products": [
                product(1, 10, 5, "  Glurak  "),
                product(2, 10, 0, "Alt", "0000-00-00 00:00:00"),
                {"idProduct": True, "idExpansion": 10, "name": "kaputt"},
                {"idProduct": 3, "name": "ohne Ausgabe"},
                "kein Objekt",
            ],
        }
    )

    assert created == datetime(2026, 10, 20, 12, 24, 46, tzinfo=UTC)
    assert rows == [
        ProductRow(1, 10, 5, "Glurak", date(2026, 9, 10), 51, "Pokémon Single"),
        ProductRow(2, 10, 0, "Alt", None, 51, "Pokémon Single"),
    ]


def test_parse_price_guide_keeps_positive_values_only() -> None:
    _, rows = parse_price_guide(
        {
            "createdAt": GUIDE_CREATED,
            "priceGuides": [
                guide(1, 10.5, 0, **{"avg-holo": 3.0, "trend-holo": None}),
                guide(2, 0, 0),
                {"idProduct": 3, "trend": True},
            ],
        }
    )

    assert [(row.id_product, row.metrics) for row in rows] == [
        (1, {"trend": 10.5, "avg-holo": 3.0})
    ]


def test_parse_rejects_unknown_format() -> None:
    with pytest.raises(CatalogError):
        parse_products({"items": []})
    assert parse_created_at("kein Datum") is None
    assert parse_created_at(None) is None


def test_product_id_from_url() -> None:
    assert product_id_from_url("https://x/Products?idProduct=908315") == 908315
    assert product_id_from_url("https://x/Products?idProduct=0") is None
    assert product_id_from_url("https://x/Products/Singles/Set/Karte") is None
    assert product_id_from_url(None) is None


# ------------------------------------------------------------------ Zwillinge


def test_twins_are_same_cards_at_the_same_time() -> None:
    _, rows = parse_products({"products": PRODUCTS})
    twins = find_twins(expansion_stats(rows))

    assert twins == {6602: [6603], 6603: [6602]}  # 1523 ohne Datum → kein Zwilling


def test_twins_need_similar_cards_and_close_dates() -> None:
    def stats(expansion: int, day: date, cards: set[int]) -> ExpansionStats:
        return ExpansionStats(expansion, len(cards), day, frozenset(cards))

    same = set(range(100))
    data = {
        1: stats(1, date(2026, 1, 1), same),
        2: stats(2, date(2026, 1, 20), same | {500}),  # Zwilling von 1
        3: stats(3, date(2026, 6, 1), same),  # zu spät
        4: stats(4, date(2026, 1, 2), set(range(50, 300))),  # zu wenig gemeinsam
    }

    assert find_twins(data) == {1: [2], 2: [1]}


# --------------------------------------------------------------------- Import


async def test_import_stores_catalog_prices_expansions_and_labels(
    session_factory: async_sessionmaker[AsyncSession], imported: None
) -> None:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(CmProduct))
        assert count == len(PRODUCTS) + len(SEALED)
        price = await session.get_one(CmPrice, JAPANESE_GLURAK)
        assert price.metrics == {"trend": 158.67, "low": 120.0, "avg7": 150.0, "avg30": 160.0}
        assert price.updated_at == datetime(2026, 10, 20, 0, 44, 49, tzinfo=UTC)
        assert await session.get(CmPrice, 908316) is None
        japanese = await session.get_one(CmExpansion, 6602)
        assert (japanese.product_count, japanese.twin_ids, japanese.label) == (
            14,
            [6603],
            "Japanisch",
        )
        run = await session.scalar(select(CmImport))
        assert run is not None and run.finished_at is not None and run.error is None
        assert run.products == len(PRODUCTS) + len(SEALED)


async def test_import_keeps_user_labels_and_drops_outdated_prices(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, imported: None
) -> None:
    async with session_factory() as session:
        expansion = await session.get_one(CmExpansion, 6603)
        expansion.label = "S-Chinesisch"
        await session.commit()

    await run_catalog_import(
        session_factory,
        settings,
        tcgdex=None,
        transport=catalog_transport(
            prices=[guide(JAPANESE_GLURAK, 1.0, 1.0)], guide_created="2026-10-21T02:44:49+0200"
        ),
    )

    async with session_factory() as session:
        assert (await session.get_one(CmExpansion, 6603)).label == "S-Chinesisch"
        # Was im neuen Preisführer fehlt, hat keinen aktuellen Preis mehr.
        assert await session.scalar(select(func.count()).select_from(CmPrice)) == 1
        assert (await session.get_one(CmPrice, JAPANESE_GLURAK)).metrics["trend"] == 1.0


async def test_import_failure_is_recorded(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    summary = await run_catalog_import(
        session_factory, settings, tcgdex=None, transport=catalog_transport(status=503)
    )

    assert summary.error is not None and "503" in summary.error
    async with session_factory() as session:
        run = await session.scalar(select(CmImport))
        assert run is not None and run.error == summary.error and run.finished_at is not None


async def test_known_wrong_set_is_fixed_on_import(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """``ja/M6a`` ist fest auf die japanische Ausgabe gesetzt; alte Werte werden verworfen."""
    card = await make_set_card(session_factory, set_id="M6a")
    async with session_factory() as session:
        session.add(
            PricePoint(
                card_id=card.id,
                source="cardmarket",
                variant="normal",
                metric="trend",
                value=Decimal("66.34"),
                currency="EUR",
                source_updated_at=UPDATED,
            )
        )
        session.add(PriceCheck(card_id=card.id, source="tcgdex", checked_at=UPDATED, ok=True))
        await session.commit()

    await run_catalog_import(session_factory, settings, tcgdex=None, transport=catalog_transport())

    async with session_factory() as session:
        card_set = await session.get_one(CardSet, card.set_id)
        assert (card_set.cardmarket_expansion_id, card_set.cardmarket_expansion_source) == (
            6602,
            "builtin",
        )
        assert await session.scalar(select(func.count()).select_from(PricePoint)) == 0
        check = await session.get_one(PriceCheck, (card.id, "tcgdex"))
        assert check.checked_at.year == 2000  # Neuabruf beim nächsten Aufruf


# ------------------------------------------------------------- Ausgabe je Set


class FakeTcgdex:
    """Liefert je Karten-ID die Cardmarket-ID (oder einen Fehler)."""

    def __init__(self, products: dict[str, int | None]) -> None:
        self.products = products
        self.calls: list[str] = []

    async def get_card(self, language: str, card_id: str) -> dict[str, object]:
        self.calls.append(card_id)
        product_id = self.products.get(card_id)
        if product_id is None:
            raise TcgdexError("nicht gefunden", status_code=404)
        return {"id": card_id, "pricing": {"cardmarket": {"idProduct": product_id}}}


async def test_link_sets_asks_tcgdex_once_per_set(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, imported: None
) -> None:
    first = await make_set_card(session_factory, number="001")
    await make_set_card(session_factory, number="137")
    empty = await make_set_card(session_factory, set_id="ohne", number="1")
    fake = FakeTcgdex({"SV-P30-137": CHINESE_GLURAK})
    now = datetime(2026, 10, 21, tzinfo=UTC)

    linked = await link_sets(session_factory, cast(TcgdexClient, fake), settings, now=now)

    assert linked == 1
    assert sorted(fake.calls) == ["SV-P30-001", "SV-P30-137", "ohne-1"]
    async with session_factory() as session:
        card_set = await session.get_one(CardSet, first.set_id)
        assert (card_set.cardmarket_expansion_id, card_set.cardmarket_expansion_source) == (
            6603,
            "tcgdex",
        )
        assert (await session.get_one(CardSet, empty.set_id)).cardmarket_checked_at == now

    # Zweiter Lauf: verknüpftes Set nie wieder, Set ohne ID erst nach der Wartezeit.
    fake.calls.clear()
    await link_sets(session_factory, cast(TcgdexClient, fake), settings, now=now)
    assert fake.calls == []
    later = now + timedelta(days=settings.cardmarket_set_recheck_days + 1)
    await link_sets(session_factory, cast(TcgdexClient, fake), settings, now=later)
    assert fake.calls == ["ohne-1"]


async def test_remap_uses_metacard_and_order(
    session_factory: async_sessionmaker[AsyncSession], imported: None
) -> None:
    async with session_factory() as session:
        chinese_pikachu = await session.get_one(CmProduct, 908317)
        assert await remap_product(session, chinese_pikachu, 6602) == 907904  # zweite Version
        eevee = await session.get_one(CmProduct, 908318)
        assert await remap_product(session, eevee, 6602) is None  # gibt es dort nicht
        glurak = await session.get_one(CmProduct, CHINESE_GLURAK)
        assert await remap_product(session, glurak, 6602) == JAPANESE_GLURAK
        assert await remap_product(session, glurak, 6603) == CHINESE_GLURAK


# ------------------------------------------------------------ Preise und API


async def test_prices_use_known_set_expansion_right_away(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    imported: None,
) -> None:
    """Glurak M6a: TCGdex meldet das chinesische Produkt → Preis und Link des japanischen."""
    user = await register_user("max@example.com")
    card = await make_set_card(session_factory, set_id="M6a")
    price_provider.quotes = quotes_for(CHINESE_GLURAK)

    body = (await client.get(f"{API}/cards/{card.id}/prices", headers=user.headers)).json()

    offer = next(o for o in body["offers"] if o["source"] == "cardmarket")
    assert offer["url"].endswith(f"idProduct={JAPANESE_GLURAK}")
    assert offer["metrics"]["trend"] == "158.67"
    assert offer["updated_at"].startswith("2026-10-20T00:44")
    choice = (await client.get(f"{API}/cards/{card.id}/cardmarket", headers=user.headers)).json()
    assert choice["product_id"] == JAPANESE_GLURAK
    assert (choice["reason"], choice["set_source"], choice["uncertain"]) == (
        "set",
        "builtin",
        False,
    )
    labels = {o["product_id"]: o["expansion_label"] for o in choice["options"]}
    assert labels == {JAPANESE_GLURAK: "Japanisch", CHINESE_GLURAK: "Chinesisch (vereinfacht)"}


async def test_uncertain_set_and_choice_fixes_whole_set(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    imported: None,
) -> None:
    user = await register_user("max@example.com")
    glurak = await make_set_card(session_factory)
    pikachu = await make_set_card(session_factory, number="025", name="ピカチュウ")
    price_provider.quotes = quotes_for(CHINESE_GLURAK)
    await client.get(f"{API}/cards/{glurak.id}/prices", headers=user.headers)
    price_provider.quotes = quotes_for(908316, trend="3.00")
    await client.get(f"{API}/cards/{pikachu.id}/prices", headers=user.headers)

    choice = (await client.get(f"{API}/cards/{glurak.id}/cardmarket", headers=user.headers)).json()
    assert (choice["reason"], choice["set_source"], choice["uncertain"]) == (
        "tcgdex",
        "tcgdex",
        True,
    )
    assert [o["product_id"] for o in choice["options"]] == [JAPANESE_GLURAK, CHINESE_GLURAK]
    assert choice["options"][1]["selected"] and choice["options"][1]["from_tcgdex"]
    assert choice["options"][0]["trend"] == "158.67"

    response = await client.put(
        f"{API}/cards/{glurak.id}/cardmarket",
        json={"product_id": JAPANESE_GLURAK},
        headers=user.headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["set_changed"], result["cards_affected"], result["uncertain"]) == (
        True,
        2,
        False,
    )
    assert (result["product_id"], result["reason"], result["set_source"]) == (
        JAPANESE_GLURAK,
        "set",
        "user",
    )
    # Pikachu (anderes Produkt, gleiches Set) hängt jetzt automatisch an der japanischen Ausgabe.
    price_provider.quotes = quotes_for(908316, trend="3.00")
    body = (await client.get(f"{API}/cards/{pikachu.id}/prices", headers=user.headers)).json()
    # 907903 steht nicht im Preisführer → kein (falscher) Preis, aber der richtige Link.
    assert [o for o in body["offers"] if o["source"] == "cardmarket"] == []
    assert body["conditions"] == []
    assert body["cardmarket_link"].endswith("idProduct=907903")
    async with session_factory() as session:
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.action == "cardmarket.product_chosen")
        )
        assert audit is not None and audit.details["expansion_id"] == 6602


async def test_cards_in_other_non_twin_expansions_stay(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    imported: None,
) -> None:
    """Set liegt bei Cardmarket in zwei Ausgaben (keine Sprachfassungen) → nichts umhängen."""
    user = await register_user("max@example.com")
    glurak = await make_set_card(session_factory)
    gallery = await make_set_card(session_factory, number="TG01")
    price_provider.quotes = quotes_for(CHINESE_GLURAK)
    await client.get(f"{API}/cards/{glurak.id}/prices", headers=user.headers)
    price_provider.quotes = quotes_for(930000, trend="12.00")

    body = (await client.get(f"{API}/cards/{gallery.id}/prices", headers=user.headers)).json()

    offer = next(o for o in body["offers"] if o["source"] == "cardmarket")
    assert (offer["url"].endswith("idProduct=930000"), offer["metrics"]["trend"]) == (True, "12.00")
    choice = (await client.get(f"{API}/cards/{gallery.id}/cardmarket", headers=user.headers)).json()
    assert (choice["reason"], choice["product_id"], choice["uncertain"]) == (
        "tcgdex",
        930000,
        False,
    )

    # Wählt jemand für diese Karte ein Produkt der Set-Ausgabe, gilt das nur für die Karte.
    result = (
        await client.put(
            f"{API}/cards/{gallery.id}/cardmarket",
            json={"product_id": CHINESE_GLURAK},
            headers=user.headers,
        )
    ).json()
    assert (result["reason"], result["set_changed"]) == ("card", False)


async def test_choice_within_expansion_is_card_override(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    price_provider: FakeProvider,
    imported: None,
) -> None:
    user = await register_user("max@example.com")
    pikachu = await make_set_card(session_factory, number="025", name="ピカチュウ")
    async with session_factory() as session:
        session.add(CardPriceLink(card_id=pikachu.id, cardmarket_url="https://alt/seite"))
        await session.commit()
    price_provider.quotes = quotes_for(908316, trend="3.00")
    await client.get(f"{API}/cards/{pikachu.id}/prices", headers=user.headers)

    result = (
        await client.put(
            f"{API}/cards/{pikachu.id}/cardmarket",
            json={"product_id": 908317},
            headers=user.headers,
        )
    ).json()

    assert (result["set_changed"], result["cards_affected"], result["reason"]) == (
        False,
        1,
        "card",
    )
    async with session_factory() as session:
        card = await session.get_one(Card, pikachu.id)
        assert card.cardmarket_product_override == 908317
        assert await session.get(CardPriceLink, pikachu.id) is None  # Auswahl ersetzt Lesezeichen


async def test_unknown_product_and_unknown_card(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    imported: None,
) -> None:
    user = await register_user("max@example.com")
    card = await make_set_card(session_factory)

    missing = await client.put(
        f"{API}/cards/{card.id}/cardmarket", json={"product_id": 1}, headers=user.headers
    )
    choice = (await client.get(f"{API}/cards/{card.id}/cardmarket", headers=user.headers)).json()

    assert missing.status_code == 404
    assert (choice["reason"], choice["options"], choice["catalog_ready"]) == ("none", [], True)
    assert (await client.get(f"{API}/cards/{card.id}/cardmarket")).status_code == 401


async def test_label_expansion(
    client: AsyncClient, register_user: RegisterUser, imported: None
) -> None:
    user = await register_user("max@example.com")

    response = await client.put(
        f"{API}/cardmarket/expansions/6603", json={"label": "  S-Chinesisch "}, headers=user.headers
    )
    cleared = await client.put(
        f"{API}/cardmarket/expansions/6602", json={"label": ""}, headers=user.headers
    )
    missing = await client.put(
        f"{API}/cardmarket/expansions/1", json={"label": "x"}, headers=user.headers
    )

    assert response.json() == {
        "expansion_id": 6603,
        "label": "S-Chinesisch",
        "product_count": 14,
        "twin_ids": [6602],
    }
    assert cleared.json()["label"] is None
    assert missing.status_code == 404


async def test_status_lists_uncertain_sets(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, imported: None
) -> None:
    await make_set_card(session_factory)
    fake = FakeTcgdex({"SV-P30-137": CHINESE_GLURAK})
    await link_sets(session_factory, cast(TcgdexClient, fake), settings, now=datetime.now(UTC))

    async with session_factory() as session:
        status = await catalog_status(session)

    assert [(u.external_id, u.expansion_id, u.twins) for u in status.uncertain] == [
        ("SV-P30", 6603, [(6602, "Japanisch")])
    ]
    text = render_status(status)
    assert "ja/SV-P30" in text and "6602 (Japanisch)" in text


# ---------------------------------------------------------------------- Worker


def test_next_catalog_import() -> None:
    now = datetime(2026, 10, 21, 12, tzinfo=UTC)

    assert next_catalog_import(now, None, 24) == now + CARDMARKET_START_DELAY
    assert next_catalog_import(now, now - timedelta(hours=2), 24) == now + timedelta(hours=22)
    assert next_catalog_import(now, now - timedelta(days=3), 24) == now + CARDMARKET_START_DELAY
    assert next_catalog_import(now, None, 0) is None


async def test_western_sets_are_not_uncertain(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    imported: None,
) -> None:
    """DE/EN teilen sich bei Cardmarket eine Ausgabe; der „Zwilling“ ist die asiatische."""
    user = await register_user("max@example.com")
    card = await make_set_card(session_factory, language="de", name="Glurak")
    fake = FakeTcgdex({"SV-P30-137": CHINESE_GLURAK})
    await link_sets(session_factory, cast(TcgdexClient, fake), settings, now=datetime.now(UTC))

    choice = (await client.get(f"{API}/cards/{card.id}/cardmarket", headers=user.headers)).json()
    async with session_factory() as session:
        status = await catalog_status(session)

    assert (choice["uncertain"], len(choice["options"])) == (False, 2)  # wählbar, aber kein Hinweis
    assert status.uncertain == []
