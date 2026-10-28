"""PriceCharting: Suche, Trefferwahl, Umrechnung, Budget, Einbindung in Preise und Bewertung."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CmPrice,
    CmProduct,
    CollectionItem,
    GradingCompany,
    PricePoint,
)
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates, FxError, parse_ecb
from app.providers.pricing import CardRef
from app.providers.pricing.pricecharting import (
    ApifyBudgetError,
    PriceChartingProvider,
    choose,
    quotes_from_details,
    quotes_from_item,
    search_query,
)
from app.services.price_health import SourceHealth
from app.services.pricing import CardPrices, Offer, PriceService
from app.services.valuation import pricecharting_metric, unit_value
from tests.conftest import RegisterUser
from tests.pricing_helpers import FakeProvider, cardmarket

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)
ECB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope><Cube><Cube time='2026-10-21'>
<Cube currency='USD' rate='1.2500'/><Cube currency='JPY' rate='160.10'/>
</Cube></Cube></gesmes:Envelope>"""


def item(
    name: str, console: str, number: str, ungraded: float | None, **extra: Any
) -> dict[str, Any]:
    prices: dict[str, Any] = {
        "ungraded": {"label": "Ungraded", "price": ungraded},
        "grade_9": {"label": "Grade 9", "price": 562.5},
        "psa_10": {"label": "PSA 10", "price": 1050},
        "grade_7": {"label": "Grade 7", "price": None},
    }
    return {
        "name": name,
        "console": console,
        "category": "trading-card",
        "card_number": number,
        "prices": prices,
        "currency": "USD",
        "url": "https://www.pricecharting.com/game/x/y",
        **extra,
    }


def ref(**fields: Any) -> CardRef:
    values: dict[str, Any] = {
        "card_id": uuid.uuid4(),
        "external_id": "S12-110",
        "language": "ja",
        "name": "ルギアV",
        "number": "110",
        "set_name": "パラダイムトリガー",
        "english_name": "Lugia V",
        "release_date": date(2022, 10, 21),
    }
    return CardRef(**(values | fields))


# ------------------------------------------------------------------ Bausteine


def test_ecb_rate_and_conversion() -> None:
    rate = parse_ecb(ECB_XML, "USD")
    assert (rate.per_euro, rate.day) == (Decimal("1.2500"), date(2026, 10, 21))
    assert rate.to_euro(Decimal("100")) == Decimal("80")
    with pytest.raises(FxError):
        parse_ecb(ECB_XML, "GBP")


def test_search_query_uses_english_name_number_and_language() -> None:
    assert search_query(ref()) == "Lugia V 110 Japanese"
    assert search_query(ref(language="en", number="199", english_name="Charizard ex")) == (
        "Charizard ex 199"
    )
    assert search_query(ref(language="zh-tw", number="033")) == "Lugia V 33 Chinese"
    assert search_query(ref(english_name=None)) is None


def test_choose_needs_language_number_and_name() -> None:
    japanese = item("Lugia V #110", "Pokemon Japanese Paradigm Trigger", "#110", 741.17)
    english = item("Lugia V #110", "Pokemon Silver Tempest", "#110", 20)
    other_number = item("Lugia V #79", "Pokemon Japanese Paradigm Trigger", "#79", 10)
    other_name = item("Pikachu #110", "Pokemon Japanese Promo", "#110", 5)

    assert choose(ref(), [english, other_number, other_name, japanese]) is japanese
    assert choose(ref(language="en", english_set_name="Silver Tempest"), [japanese, english]) is (
        english
    )
    assert choose(ref(), [english, other_name]) is None


def test_choose_prefers_set_or_release_date_and_rejects_ties() -> None:
    old = item("Pikachu #25", "Pokemon Japanese Old Set", "#25", 3, release_date="May 1, 2010")
    new = item("Pikachu #25", "Pokemon Japanese New Set", "#25", 9, release_date="October 1, 2022")
    pikachu = ref(english_name="Pikachu", number="025")

    assert choose(pikachu, [old, new]) is new  # Erscheinungsdatum passt
    assert choose(ref(english_name="Pikachu", number="25", release_date=None), [old, new]) is None


def test_quotes_are_converted_to_euro() -> None:
    lugia = item("Lugia V #110", "Pokemon Japanese Paradigm Trigger", "#110", 741.17)
    quotes = {
        (q.variant, q.metric): q
        for q in quotes_from_item(lugia, per_euro=Decimal("1.25"), fetched_at=NOW)
    }

    assert quotes[("normal", "ungraded")].value.quantize(Decimal("0.01")) == Decimal("592.94")
    assert quotes[("graded", "psa_10")].value == Decimal("840")
    assert ("graded", "grade_7") not in quotes  # ohne Preis
    assert {q.currency for q in quotes.values()} == {"EUR"}


# ------------------------------------------------------------ Quelle (Apify)


DETAIL = {
    "url": "https://www.pricecharting.com/game/pokemon-japanese-paradigm-trigger/lugia-v-110",
    "images": ["https://storage.googleapis.com/images.pricecharting.com/a/1600.jpg"],
    "salesVolume": {"PSA 10": 30, "Ungraded": 60},
    "populationReport": {"PSA": {"9": 47519, "10": 27631}},
    "recentSales": {
        "PSA 10": [
            {
                "date": "2026-10-19",
                "title": "Lugia V PSA 10",
                "price": 1040,
                "source": "ebay",
                "url": "https://www.ebay.com/itm/1",
            },
        ],
        "Ungraded": [
            {
                "date": "2026-10-20",
                "title": "Lugia V 110 NM",
                "price": 735,
                "source": "ebay",
                "url": "https://www.ebay.com/itm/2",
            },
        ],
    },
    "fullPrices": {
        "Ungraded": 741.17,
        "Grade 9": 562.5,
        "Grade 9.5": 675.48,
        "PSA 10": 1050,
        "BGS 10": 2500,
        "BGS 10 Black": 10000,
        "CGC 10 Pristine": 1800,
        "Grade 7": None,
        "Box Only": 5,
    },
}


def apify_transport(
    items: list[dict[str, Any]],
    *,
    used: float = 1.0,
    query: str = "Lugia V 110 Japanese",
    calls: list[str] | None = None,
    details: list[dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(f"{request.method} {request.url.path}")
        if request.url.host == "www.ecb.europa.eu":
            return httpx.Response(200, text=ECB_XML)
        path = request.url.path
        if path.endswith("/users/me/limits"):
            body: Any = {
                "data": {
                    "current": {"monthlyUsageUsd": used},
                    "limits": {"maxMonthlyUsageUsd": 8},
                }
            }
        elif path.endswith("/runs"):
            detail = "parsebird" in path
            payload = json.loads(request.content)
            if not detail:
                assert payload["searchQueries"] == [query]
            body = {
                "data": {
                    "id": "run1",
                    "status": "SUCCEEDED",
                    "defaultDatasetId": "details" if detail else "ds1",
                    "usageTotalUsd": 0.003 if detail else 0.005,
                }
            }
        elif path.endswith("/datasets/ds1/items"):
            body = items
        elif path.endswith("/datasets/details/items"):
            body = [DETAIL] if details is None else details
        else:
            return httpx.Response(404)
        return httpx.Response(200, content=json.dumps(body).encode())

    return httpx.MockTransport(handler)


def provider(settings: Settings, transport: httpx.MockTransport) -> PriceChartingProvider:
    rates = EcbRates(user_agent="test", transport=transport, clock=lambda: NOW)
    return PriceChartingProvider(
        settings,
        rates,
        lambda: ApifyClient("token", user_agent="test", transport=transport),
        clock=lambda: NOW,
    )


LUGIA = item("Lugia V #110", "Pokemon Japanese Paradigm Trigger", "#110", 741.17)


async def test_provider_fetches_and_converts(settings: Settings) -> None:
    quotes = await provider(settings, apify_transport([LUGIA])).fetch(ref())

    raw = next(q for q in quotes if q.metric == "ungraded")
    assert (raw.source, raw.variant, raw.currency) == ("pricecharting", "normal", "EUR")
    assert raw.value.quantize(Decimal("0.01")) == Decimal("592.94")
    assert raw.source_url == "https://www.pricecharting.com/game/x/y"


async def test_provider_keeps_reserve_for_ebay(settings: Settings) -> None:
    calls: list[str] = []
    transport = apify_transport([LUGIA], used=5.99, calls=calls)  # Budget 7 $, Reserve 2 $

    with pytest.raises(ApifyBudgetError):
        await provider(settings, transport).fetch(ref())
    assert not any(call.endswith("/runs") for call in calls)  # nichts bezahlt


# ------------------------------------------------------ Einbindung in Preise


async def _japanese_card(factory: async_sessionmaker[AsyncSession]) -> Card:
    async with factory() as session:
        card_set = CardSet(
            external_id="S12", language="ja", name="パラダイムトリガー",
            release_date=date(2022, 10, 21),
        )  # fmt: skip
        session.add(card_set)
        await session.flush()
        card = Card(
            external_id="S12-110", language="ja", set_id=card_set.id, number="110",
            number_norm="110", name="ルギアV",
        )  # fmt: skip
        session.add(card)
        await session.commit()
        return card


async def _service(session: AsyncSession, settings: Settings, *providers: Any) -> PriceService:
    return PriceService(
        session,
        settings,
        list(providers),
        SourceHealth(threshold=3, pause=timedelta(minutes=60)),
        clock=lambda: NOW,
    )


async def test_service_uses_pricecharting_only_without_cardmarket(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    card = await _japanese_card(session_factory)
    calls: list[str] = []
    pricecharting = provider(settings, apify_transport([LUGIA], calls=calls))

    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        service = await _service(session, settings, FakeProvider(), pricecharting)
        report = await service.refresh(loaded, viewed=True)
        await session.commit()
        prices = await service.get_prices(loaded, None)

    assert report.outcomes == {"tcgdex": "fetched", "pricecharting": "fetched"}
    nm = next(c for c in prices.conditions if c.condition == "NM")
    assert (nm.source, nm.kind) == ("pricecharting", "estimated")
    assert nm.basis_metric == "US-Preis PriceCharting (umgerechnet)"
    assert nm.value == Decimal("592.94")

    # Zweiter Abruf (auch erzwungen) innerhalb der Gültigkeit: nichts Neues, nichts bezahlt.
    runs = sum(call.endswith("/runs") for call in calls)
    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        service = await _service(session, settings, FakeProvider(), pricecharting)
        again = await service.refresh(loaded, force=True)
    assert again.outcomes["pricecharting"] == "fresh"
    assert sum(call.endswith("/runs") for call in calls) == runs


async def test_service_skips_pricecharting_when_cardmarket_has_a_price(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    card = await _japanese_card(session_factory)
    calls: list[str] = []
    pricecharting = provider(settings, apify_transport([LUGIA], calls=calls))
    tcgdex = FakeProvider(quotes=[cardmarket("trend", "100.00")])

    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        report = await (await _service(session, settings, tcgdex, pricecharting)).refresh(loaded)
        await session.commit()
        stored = (
            await session.scalars(select(PricePoint.source).where(PricePoint.card_id == card.id))
        ).all()

    assert report.outcomes["pricecharting"] == "not_needed"
    assert set(stored) == {"cardmarket"}
    assert calls == []


async def test_service_fetches_pricecharting_for_slabs_even_with_cardmarket(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: AsyncClient,
    register_user: RegisterUser,
) -> None:
    card = await _japanese_card(session_factory)
    pricecharting = provider(settings, apify_transport([LUGIA]))
    tcgdex = FakeProvider(quotes=[cardmarket("trend", "100.00")])
    user = await register_user("slab@example.com")
    added = await client.post(
        "/api/v1/collection/items",
        json={"card_id": str(card.id), "grading_company": "PSA", "grade": "10"},
        headers=user.headers,
    )
    assert added.status_code == 201, added.text

    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        report = await (await _service(session, settings, tcgdex, pricecharting)).refresh(loaded)
    assert report.outcomes["pricecharting"] == "fetched"


# ------------------------------------------------------------------ Bewertung


def _offer(variant: str, metrics: dict[str, str]) -> Offer:
    return Offer(
        source="pricecharting", variant=variant, condition=None, currency="EUR",
        kind="verified", updated_at=NOW, url=None,
        metrics={k: Decimal(v) for k, v in metrics.items()},
    )  # fmt: skip


@pytest.mark.parametrize(
    ("company", "grade", "expected"),
    [
        (GradingCompany.PSA, "10", Decimal("840.00")),
        (GradingCompany.BGS, "10", None),  # „PSA 10“ gilt nicht für andere Firmen
        (GradingCompany.CGC, "9", Decimal("450.00")),
        (GradingCompany.PSA, "6", None),
    ],
)
def test_slab_value_from_pricecharting_grade(
    company: GradingCompany, grade: str, expected: Decimal | None
) -> None:
    prices = CardPrices(
        card_id=uuid.uuid4(),
        last_checked_at=NOW,
        offers=[_offer("graded", {"psa_10": "840.00", "grade_9": "450.00"})],
        conditions=[],
    )
    item = CollectionItem(
        card_id=prices.card_id, product_id=None, variant="normal", condition=None, quantity=1,
        custom_price=None, grading_company=company, grade=grade, value_at_add=None,
    )  # fmt: skip

    value = unit_value(item, prices)

    assert value.unit_value == expected
    if expected is not None:
        assert value.source == "pricecharting"
        assert value.basis is not None and "umgerechnet" in value.basis


# ------------------------------------------------------- Details (parsebird)


def test_detail_metrics_per_company() -> None:
    quotes = {
        q.metric: q.value
        for q in quotes_from_details(DETAIL, per_euro=Decimal("1.25"), fetched_at=NOW)
    }
    assert set(quotes) == {
        "ungraded", "grade_9", "grade_9_5", "psa_10", "bgs_10", "bgs_10_black", "cgc_10_pristine"
    }  # fmt: skip
    assert quotes["bgs_10_black"] == Decimal("8000")


async def test_known_product_page_uses_details_without_search(settings: Settings) -> None:
    calls: list[str] = []
    known = ref(pricecharting_url=DETAIL["url"])

    quotes = await provider(settings, apify_transport([], calls=calls)).fetch(known)

    runs = [call for call in calls if call.endswith("/runs")]
    assert len(runs) == 1 and "parsebird" in runs[0]  # keine Suche
    assert {q.metric for q in quotes} >= {"ungraded", "bgs_10"}


async def test_slab_without_known_page_searches_then_loads_details(settings: Settings) -> None:
    calls: list[str] = []
    lugia = item(
        "Lugia V #110", "Pokemon Japanese Paradigm Trigger", "#110", 741.17,
        url=DETAIL["url"],
    )  # fmt: skip

    quotes = await provider(settings, apify_transport([lugia], calls=calls)).fetch(ref(graded=True))

    runs = [call for call in calls if call.endswith("/runs")]
    assert len(runs) == 2 and "gio21" in runs[0] and "parsebird" in runs[1]
    assert "bgs_10_black" in {q.metric for q in quotes}


@pytest.mark.parametrize(
    ("company", "grade", "metric"),
    [
        (GradingCompany.BGS, "10", "bgs_10"),
        (GradingCompany.BGS, "10 BL", "bgs_10_black"),
        (GradingCompany.CGC, "10 BL", "cgc_10_pristine"),
        (GradingCompany.SGC, "10", "sgc_10"),
        (GradingCompany.OTHER, "10", None),
        (GradingCompany.PSA, "9.5", "grade_9_5"),
    ],
)
def test_pricecharting_metric_for_company_and_grade(
    company: GradingCompany, grade: str, metric: str | None
) -> None:
    assert pricecharting_metric(company, grade) == metric


async def test_slab_details_are_stored_and_served(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: AsyncClient,
    register_user: RegisterUser,
) -> None:
    card = await _japanese_card(session_factory)
    user = await register_user("details@example.com")
    empty = await client.get(f"/api/v1/cards/{card.id}/pricecharting", headers=user.headers)
    assert empty.json() == {
        "available": False, "fetched_at": None, "product_url": None, "population": {},
        "sales_volume": {}, "recent_sales": [], "images": [],
    }  # fmt: skip
    added = await client.post(
        "/api/v1/collection/items",
        json={"card_id": str(card.id), "grading_company": "PSA", "grade": "10"},
        headers=user.headers,
    )
    assert added.status_code == 201, added.text
    lugia = item(
        "Lugia V #110", "Pokemon Japanese Paradigm Trigger", "#110", 741.17, url=DETAIL["url"]
    )
    pricecharting = provider(settings, apify_transport([lugia]))
    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        service = await _service(session, settings, FakeProvider(), pricecharting)
        await service.refresh(loaded)
        await session.commit()

    response = await client.get(f"/api/v1/cards/{card.id}/pricecharting", headers=user.headers)

    data = response.json()
    assert data["available"] is True
    assert data["population"] == {"PSA": {"9": 47519, "10": 27631}}
    assert data["sales_volume"] == {"PSA 10": 30, "Ungraded": 60}
    assert [(s["grade"], s["date"], s["price_usd"]) for s in data["recent_sales"]] == [
        ("Ungraded", "2026-10-20", 735.0),
        ("PSA 10", "2026-10-19", 1040.0),
    ]
    assert data["images"] == DETAIL["images"]


# ------------------------------------------------------------------ One Piece

ZORO = item("Roronoa Zoro #OP01-001", "One Piece Romance Dawn", "OP01-001", 2.5)
ZORO_ALT = item("Roronoa Zoro [Alternate Art] #OP01-001", "One Piece Romance Dawn", "OP01-001", 60)
ZORO_JP = item("Roronoa Zoro #OP01-001", "One Piece Japanese Romance Dawn", "OP01-001", 1.5)


def zoro(**fields: Any) -> CardRef:
    values: dict[str, Any] = {
        "external_id": "op-OP01-001",
        "language": "en",
        "name": "Roronoa Zoro",
        "number": "OP01-001",
        "set_name": "Romance Dawn",
        "english_name": "Roronoa Zoro",
        "english_set_name": "Romance Dawn",
        "release_date": date(2022, 12, 2),
        "game": "onepiece",
    }
    return ref(**(values | fields))


def test_one_piece_search_and_choice_respect_game_and_variant() -> None:
    parallel = zoro(name="Roronoa Zoro (Parallel)", english_name="Roronoa Zoro (Parallel)")
    pokemon_twin = item("Roronoa Zoro #OP01-001", "Pokemon Promo", "OP01-001", 1)

    assert search_query(parallel) == "Roronoa Zoro OP01-001"
    assert search_query(zoro(language="ja")) == "Roronoa Zoro OP01-001 Japanese"
    items = [pokemon_twin, ZORO_ALT, ZORO_JP, ZORO]
    assert choose(zoro(), items) is ZORO
    assert choose(parallel, items) is ZORO_ALT
    assert choose(zoro(language="ja"), items) is ZORO_JP
    # Pokémon-Karten sehen nie One-Piece-Einträge (und umgekehrt).
    assert choose(ref(english_name="Roronoa Zoro", number="OP01-001"), [ZORO]) is None


async def test_one_piece_slab_gets_pricecharting_without_pokemon_sources(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: AsyncClient,
    register_user: RegisterUser,
) -> None:
    async with session_factory() as session:
        card_set = CardSet(
            external_id="op-OP01", language="en", game="onepiece", name="Romance Dawn",
            release_date=date(2022, 12, 2),
        )  # fmt: skip
        session.add(card_set)
        session.add(
            CmProduct(
                id_product=690368,
                game="onepiece",
                id_expansion=5229,
                id_metacard=1,
                name="Roronoa Zoro (OP01-001)",
                id_category=1621,
            )
        )
        session.add(CmPrice(id_product=690368, game="onepiece", metrics={"trend": 2.31},
                            updated_at=NOW))  # fmt: skip
        await session.flush()
        card = Card(
            external_id="op-OP01-001", language="en", set_id=card_set.id, number="OP01-001",
            number_norm="OP1001", name="Roronoa Zoro", cardmarket_product_id=690368,
        )  # fmt: skip
        session.add(card)
        await session.commit()
    user = await register_user("zoro@example.com")
    added = await client.post(
        "/api/v1/collection/items",
        json={"card_id": str(card.id), "grading_company": "PSA", "grade": "10"},
        headers=user.headers,
    )
    assert added.status_code == 201, added.text
    tcgdex = FakeProvider()
    pricecharting = provider(
        settings, apify_transport([ZORO_ALT, ZORO], query="Roronoa Zoro OP01-001")
    )

    async with session_factory() as session:
        loaded = await session.get_one(Card, card.id)
        report = await (await _service(session, settings, tcgdex, pricecharting)).refresh(loaded)
        await session.commit()
        sources = set(
            await session.scalars(select(PricePoint.source).where(PricePoint.card_id == card.id))
        )

    # Der Preisführer-Wert kam schon beim Hinzufügen (frisch), PriceCharting jetzt für den Slab.
    assert set(report.outcomes) == {"cardmarket-guide", "pricecharting"}
    assert report.outcomes["pricecharting"] == "fetched"
    assert tcgdex.calls == []
    assert sources == {"cardmarket", "pricecharting"}
