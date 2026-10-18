"""PriceService gegen echte Datenbank: Abruf, Historie, Frische, Fehler, Anzeige."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, PriceCheck, PricePoint, Role, User
from app.providers.pricing import PriceNotAvailableError
from app.services.price_health import SourceHealth
from app.services.pricing import CardPrices, PriceService, nm_basis, tracked_card_ids
from app.services.user_settings import update_user_settings
from tests.pricing_helpers import UPDATED, FakeProvider, cardmarket, make_card


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def health(clock: Clock) -> SourceHealth:
    return SourceHealth(threshold=3, pause=timedelta(minutes=60), clock=clock)


@pytest.fixture
async def card(session_factory: async_sessionmaker[AsyncSession]) -> Card:
    return await make_card(session_factory)


@pytest.fixture
async def user(session_factory: async_sessionmaker[AsyncSession]) -> User:
    async with session_factory() as session:
        account = User(email="u@example.com", display_name="U", password_hash="x", role=Role.USER)
        session.add(account)
        await session.commit()
        return account


ServiceFactory = Callable[[AsyncSession, list[FakeProvider]], PriceService]


@pytest.fixture
def make_service(settings: Settings, health: SourceHealth, clock: Clock) -> ServiceFactory:
    def _make(session: AsyncSession, providers: list[FakeProvider]) -> PriceService:
        return PriceService(session, settings, providers, health, clock=clock)

    return _make


async def _refresh(
    factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    providers: list[FakeProvider],
    **kwargs: bool,
) -> dict[str, str]:
    async with factory() as session:
        report = await make_service(session, providers).refresh(
            await session.get_one(Card, card.id), **kwargs
        )
        await session.commit()
    return dict(report.outcomes)


async def _point_count(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        return int(await session.scalar(select(func.count()).select_from(PricePoint)) or 0)


# ------------------------------------------------------------------------- Abruf


async def test_refresh_stores_quotes_and_respects_max_age(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    clock: Clock,
) -> None:
    provider = FakeProvider(quotes=[cardmarket("trend", "1805.90"), cardmarket("low", "220")])

    assert await _refresh(session_factory, make_service, card, [provider]) == {"tcgdex": "fetched"}
    assert await _point_count(session_factory) == 2

    clock.now += timedelta(hours=11)
    assert await _refresh(session_factory, make_service, card, [provider]) == {"tcgdex": "fresh"}
    assert len(provider.calls) == 1

    clock.now += timedelta(hours=2)  # älter als 12 h → neu holen
    assert await _refresh(session_factory, make_service, card, [provider]) == {"tcgdex": "fetched"}
    assert len(provider.calls) == 2


async def test_same_source_state_is_not_stored_twice_but_new_state_is(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
) -> None:
    provider = FakeProvider(quotes=[cardmarket("trend", "1805.90")])
    await _refresh(session_factory, make_service, card, [provider], force=True)
    await _refresh(session_factory, make_service, card, [provider], force=True)
    assert await _point_count(session_factory) == 1

    provider.quotes = [cardmarket("trend", "1700.00", updated=UPDATED + timedelta(days=1))]
    await _refresh(session_factory, make_service, card, [provider], force=True)
    assert await _point_count(session_factory) == 2


async def test_failure_is_recorded_retried_later_and_pauses_source(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    clock: Clock,
    health: SourceHealth,
) -> None:
    provider = FakeProvider(error=RuntimeError("TCGdex down"))

    assert await _refresh(session_factory, make_service, card, [provider]) == {"tcgdex": "failed"}
    async with session_factory() as session:
        check = await session.get_one(PriceCheck, (card.id, "tcgdex"))
        assert (check.ok, check.message) == (False, "RuntimeError: TCGdex down")

    clock.now += timedelta(minutes=30)
    assert await _refresh(session_factory, make_service, card, [provider]) == {
        "tcgdex": "retry_later"
    }

    for _ in range(2):  # Fehler 2 und 3 in Folge → Sicherung greift
        await _refresh(session_factory, make_service, card, [provider], force=True)
    assert health.is_paused("tcgdex")
    assert await _refresh(session_factory, make_service, card, [provider], force=True) == {
        "tcgdex": "paused"
    }

    clock.now += timedelta(minutes=61)
    provider.error = None
    assert await _refresh(session_factory, make_service, card, [provider], force=True) == {
        "tcgdex": "fetched"
    }
    assert not health.is_paused("tcgdex")


async def test_slow_source_times_out_without_blocking_others(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    health: SourceHealth,
    clock: Clock,
    card: Card,
) -> None:
    slow = FakeProvider(name="langsam", kind="external", delay=1.0)
    fast = FakeProvider(quotes=[cardmarket("trend", "10")])
    fast_settings = settings.model_copy(update={"price_provider_timeout_seconds": 0.05})

    async with session_factory() as session:
        service = PriceService(session, fast_settings, [slow, fast], health, clock=clock)
        report = await service.refresh(await session.get_one(Card, card.id))
        await session.commit()

    assert report.outcomes == {"langsam": "failed", "tcgdex": "fetched"}


async def test_unknown_card_is_ok_not_a_failure(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    health: SourceHealth,
) -> None:
    provider = FakeProvider(error=PriceNotAvailableError("404"))
    for _ in range(5):
        outcome = await _refresh(session_factory, make_service, card, [provider], force=True)
        assert outcome == {"tcgdex": "not_available"}
    assert not health.is_paused("tcgdex")


async def test_external_sources_cannot_pose_as_builtin_sources(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
) -> None:
    plugin = FakeProvider(
        name="meine_quelle",
        kind="external",
        quotes=[cardmarket("lowest", "1650", condition="NM", source="cardmarket")],
    )
    await _refresh(session_factory, make_service, card, [plugin])

    async with session_factory() as session:
        sources = (await session.scalars(select(PricePoint.source))).all()
    assert sources == ["meine_quelle"]


# ------------------------------------------------------------------------ Anzeige


async def _prices(
    factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> CardPrices:
    async with factory() as session:
        return await make_service(session, []).get_prices(
            await session.get_one(Card, card.id), await session.get_one(User, user.id)
        )


async def test_prices_show_latest_values_and_estimated_conditions(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    old = UPDATED - timedelta(days=1)
    provider = FakeProvider(
        quotes=[
            cardmarket("trend", "1700.00", updated=old),
            cardmarket("trend", "1805.90"),
            cardmarket("low", "220"),
            cardmarket("trend", "3.00", variant="reverse"),
        ]
    )
    await _refresh(session_factory, make_service, card, [provider])

    prices = await _prices(session_factory, make_service, card, user)

    normal = next(o for o in prices.offers if o.variant == "normal")
    assert normal.metrics == {"trend": Decimal("1805.90"), "low": Decimal("220.00")}
    assert (normal.kind, normal.updated_at) == ("verified", UPDATED)
    nm = next(c for c in prices.conditions if c.variant == "normal" and c.condition == "NM")
    ex = next(c for c in prices.conditions if c.variant == "normal" and c.condition == "EX")
    assert (nm.value, nm.kind, nm.basis_metric) == (Decimal("1805.90"), "estimated", "trend")
    assert (ex.value, ex.factor) == (Decimal("1535.02"), Decimal("0.85"))
    assert {c.variant for c in prices.conditions} == {"normal", "reverse"}
    assert len(prices.conditions) == 14


async def test_custom_factors_and_external_condition_prices_take_precedence(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    builtin = FakeProvider(quotes=[cardmarket("trend", "100")])
    plugin = FakeProvider(
        name="meine_quelle",
        kind="external",
        quotes=[cardmarket("lowest", "93.50", condition="NM")],
    )
    await _refresh(session_factory, make_service, card, [builtin, plugin])
    async with session_factory() as session:
        await update_user_settings(
            session, await session.get_one(User, user.id), condition_factors={"EX": Decimal("0.9")}
        )
        await session.commit()

    prices = await _prices(session_factory, make_service, card, user)

    by_condition = {c.condition: c for c in prices.conditions if c.variant == "normal"}
    assert (by_condition["NM"].kind, by_condition["NM"].value) == ("external", Decimal("93.50"))
    assert by_condition["NM"].source == "meine_quelle"
    assert (by_condition["EX"].kind, by_condition["EX"].value) == ("estimated", Decimal("90.00"))


async def test_language_factor_applies_to_estimates_only(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    builtin = FakeProvider(quotes=[cardmarket("trend", "100")])
    plugin = FakeProvider(
        name="meine_quelle",
        kind="external",
        quotes=[cardmarket("lowest", "93.50", condition="NM")],
    )
    await _refresh(session_factory, make_service, card, [builtin, plugin])
    async with session_factory() as session:
        await update_user_settings(
            session,
            await session.get_one(User, user.id),
            language_factors={card.language: Decimal("0.8")},  # type: ignore[dict-item]
        )
        await session.commit()

    prices = await _prices(session_factory, make_service, card, user)

    by_condition = {c.condition: c for c in prices.conditions if c.variant == "normal"}
    assert by_condition["NM"].value == Decimal("93.50")  # Beleg bleibt unverändert
    ex = by_condition["EX"]
    assert (ex.value, ex.factor, ex.language_factor) == (
        Decimal("68.00"),  # 100 × 0,85 × 0,8
        Decimal("0.85"),
        Decimal("0.80"),
    )


async def test_external_condition_prices_without_cardmarket_reference(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    plugin = FakeProvider(
        name="meine_quelle",
        kind="external",
        quotes=[cardmarket("lowest", "12.00", condition="EX")],
    )
    await _refresh(session_factory, make_service, card, [plugin])

    prices = await _prices(session_factory, make_service, card, user)

    assert [(c.condition, c.kind, c.value) for c in prices.conditions] == [
        ("EX", "external", Decimal("12.00"))
    ]


async def test_no_verified_price_means_no_estimate(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    await _refresh(session_factory, make_service, card, [FakeProvider()])

    prices = await _prices(session_factory, make_service, card, user)

    assert not prices.has_prices
    assert prices.conditions == []


async def test_history_one_point_per_day_and_extremes(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    clock: Clock,
) -> None:
    provider = FakeProvider()
    for day, value in enumerate(["100", "120", "90", "110"]):
        provider.quotes = [cardmarket("trend", value, updated=UPDATED + timedelta(days=day))]
        await _refresh(session_factory, make_service, card, [provider], force=True)
    clock.now = UPDATED + timedelta(days=4)

    async with session_factory() as session:
        service = make_service(session, [])
        history = await service.get_history(await session.get_one(Card, card.id), days=2)
        full = await service.get_history(await session.get_one(Card, card.id), days=30)

    assert [p.value for p in history.points] == [Decimal("90.00"), Decimal("110.00")]
    assert [p.value for p in full.points] == [Decimal(v) for v in ("100", "120", "90", "110")]
    assert (history.lowest, history.highest) == (Decimal("90.00"), Decimal("120.00"))
    assert history.observed_since == UPDATED
    assert history.currency == "EUR"


async def test_viewed_cards_are_tracked_for_daily_refresh(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    settings: Settings,
    card: Card,
    clock: Clock,
) -> None:
    other = await make_card(
        session_factory, external_id="swsh7-188", name="Nachtara V", number="188"
    )
    provider = FakeProvider()
    await _refresh(session_factory, make_service, card, [provider], viewed=True)
    await _refresh(session_factory, make_service, other, [provider])  # nicht angesehen

    async with session_factory() as session:
        assert await tracked_card_ids(session, settings, clock.now) == [card.id]
        assert await tracked_card_ids(session, settings, clock.now + timedelta(days=31)) == []


# ----------------------------------------------------------------- NM-Basis (Median)


def _metrics(**values: str) -> dict[str, Decimal]:
    return {key: Decimal(value) for key, value in values.items()}


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        # Echte Werte vom VPS (17.10.2026): Glurak Grundset – Trend unter günstigstem Angebot
        (
            _metrics(trend="58.10", avg7="423.40", avg30="765.81", low="95", avg="741.93"),
            ("median(trend, avg7, avg30)", Decimal("423.40")),
        ),
        # Nachtara VMAX – unauffällig: Median = Trend
        (
            _metrics(trend="1805.90", avg7="2249.80", avg30="1772.15"),
            ("median(trend, avg7, avg30)", Decimal("1805.90")),
        ),
        (_metrics(trend="100", avg30="200"), ("median(trend, avg30)", Decimal("150.00"))),
        (_metrics(trend="42"), ("trend", Decimal("42"))),
        (_metrics(avg="7.5", low="1"), ("avg", Decimal("7.5"))),
        (_metrics(low="1"), None),
    ],
)
def test_nm_basis_is_median_of_trend_avg7_avg30(
    metrics: dict[str, Decimal], expected: tuple[str, Decimal] | None
) -> None:
    assert nm_basis(metrics) == expected


async def test_outlier_trend_does_not_distort_condition_prices(
    session_factory: async_sessionmaker[AsyncSession],
    make_service: ServiceFactory,
    card: Card,
    user: User,
) -> None:
    provider = FakeProvider(
        quotes=[
            cardmarket("trend", "58.10"),
            cardmarket("avg7", "423.40"),
            cardmarket("avg30", "765.81"),
            cardmarket("low", "95"),
        ]
    )
    await _refresh(session_factory, make_service, card, [provider])

    prices = await _prices(session_factory, make_service, card, user)

    nm = next(c for c in prices.conditions if c.condition == "NM")
    assert (nm.value, nm.basis_value) == (Decimal("423.40"), Decimal("423.40"))
    assert nm.basis_metric == "median(trend, avg7, avg30)"
    assert nm.value > Decimal("95")  # nicht mehr unter dem günstigsten Angebot
