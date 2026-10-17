"""Tägliche Preisrunde: Zeitplanung und Ablauf."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import PriceCheck, PricePoint
from app.services.price_health import SourceHealth
from app.worker import next_run_after, refresh_tracked_prices
from tests.pricing_helpers import FakeProvider, cardmarket, make_card


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Sommerzeit (UTC+2): 12:30 Berlin = 10:30 UTC
        (datetime(2026, 10, 17, 8, 0, tzinfo=UTC), datetime(2026, 10, 17, 10, 30, tzinfo=UTC)),
        # schon vorbei → morgen
        (datetime(2026, 10, 17, 11, 0, tzinfo=UTC), datetime(2026, 10, 18, 10, 30, tzinfo=UTC)),
        # Umstellung auf Winterzeit am 25.10.2026 (UTC+1): 12:30 Berlin = 11:30 UTC
        (datetime(2026, 10, 24, 12, 0, tzinfo=UTC), datetime(2026, 10, 25, 11, 30, tzinfo=UTC)),
    ],
)
def test_next_run_after_respects_local_time_and_dst(now: datetime, expected: datetime) -> None:
    assert next_run_after(now, "12:30", "Europe/Berlin") == expected


async def test_refresh_round_updates_only_tracked_cards(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    viewed = await make_card(session_factory)
    ignored = await make_card(session_factory, external_id="swsh7-188", number="188")
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            [
                PriceCheck(
                    card_id=viewed.id, source="tcgdex", checked_at=now, ok=True, last_viewed_at=now
                ),
                PriceCheck(card_id=ignored.id, source="tcgdex", checked_at=now, ok=True),
            ]
        )
        await session.commit()
    provider = FakeProvider(quotes=[cardmarket("trend", "10")])
    health = SourceHealth(threshold=3, pause=timedelta(minutes=60))

    summary = await refresh_tracked_prices(session_factory, settings, [provider], health)

    assert (summary.cards, summary.quotes_stored, summary.failed_cards) == (1, 1, 0)
    assert [call.card_id for call in provider.calls] == [viewed.id]  # trotz frischem Stand: force
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(PricePoint)) == 1


async def test_refresh_round_counts_failures_and_continues(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    cards = [
        await make_card(session_factory, external_id=f"x-{i}", number=str(i)) for i in range(3)
    ]
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add_all(
            PriceCheck(card_id=c.id, source="tcgdex", checked_at=now, ok=True, last_viewed_at=now)
            for c in cards
        )
        await session.commit()
    provider = FakeProvider(error=RuntimeError("down"))
    health = SourceHealth(threshold=10, pause=timedelta(minutes=60))

    summary = await refresh_tracked_prices(session_factory, settings, [provider], health)

    assert (summary.cards, summary.failed_cards) == (3, 3)
