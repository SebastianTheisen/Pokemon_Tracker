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
from app.models import Card, CardSet, CollectionItem, GradingCompany, PricePoint
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates, FxError, parse_ecb
from app.providers.pricing import CardRef
from app.providers.pricing.pricecharting import (
    ApifyBudgetError,
    PriceChartingProvider,
    choose,
    quotes_from_item,
    search_query,
)
from app.services.price_health import SourceHealth
from app.services.pricing import CardPrices, Offer, PriceService
from app.services.valuation import unit_value
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


def apify_transport(
    items: list[dict[str, Any]], *, used: float = 1.0, calls: list[str] | None = None
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
            assert json.loads(request.content)["searchQueries"] == ["Lugia V 110 Japanese"]
            body = {
                "data": {
                    "id": "run1",
                    "status": "SUCCEEDED",
                    "defaultDatasetId": "ds1",
                    "usageTotalUsd": 0.005,
                }
            }
        elif path.endswith("/datasets/ds1/items"):
            body = items
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
