"""Wochenrückblick: Mitteilung sonntags, nur mit Mitteilungen und wenn nicht abgeschaltet."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import PortfolioSnapshot, PushSubscription
from app.services import push
from app.services.weekly import is_summary_day, send_weekly_summaries
from tests.conftest import RegisterUser
from tests.test_alerts import Device

API = "/api/v1"
SUNDAY = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)  # 14:00 in Berlin


def test_summary_day_is_sunday_in_local_time(settings: Settings) -> None:
    assert is_summary_day(SUNDAY, settings.timezone)
    assert not is_summary_day(SUNDAY - timedelta(days=1), settings.timezone)
    # Samstag 23:30 UTC ist in Berlin schon Sonntag
    assert is_summary_day(datetime(2026, 10, 24, 23, 30, tzinfo=UTC), settings.timezone)


async def test_weekly_summary_and_opt_out(
    client: AsyncClient,
    register_user: RegisterUser,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[push.PushMessage] = []

    async def fake_send(
        _client: httpx.AsyncClient,
        _settings: Settings,
        _subscription: PushSubscription,
        message: push.PushMessage,
    ) -> push.PushOutcome:
        sent.append(message)
        return push.PushOutcome.SENT

    monkeypatch.setattr(push, "send", fake_send)
    alice = await register_user("alice@example.com")
    bob = await register_user("bob@example.com")  # ohne Gerät: bekommt nichts
    await client.post(
        f"{API}/push/subscriptions", json=Device().subscription(), headers=alice.headers
    )
    today = date(2026, 10, 25)
    async with session_factory() as session:
        for user_id in (alice.user_id, bob.user_id):
            for day, value in ((today - timedelta(days=8), "1000.00"), (today, "1042.10")):
                session.add(
                    PortfolioSnapshot(
                        user_id=user_id,
                        day=day,
                        total_value=Decimal(value),
                        raw_value=Decimal(value),
                        graded_value=Decimal(0),
                        sealed_value=Decimal(0),
                        estimated_value=Decimal(0),
                        item_count=1,
                        position_count=1,
                    )
                )
        await session.commit()

    assert await send_weekly_summaries(session_factory, settings, now=SUNDAY) == 1
    assert sent[0].title == "Deine Woche in der Kartenkiste"
    assert sent[0].body == "Wert 1.042,10 € (+42,10 € · +4,2 %)."

    config = (await client.get(f"{API}/push/config", headers=alice.headers)).json()
    assert config["weekly_summary"] is True
    off = await client.patch(
        f"{API}/push/preferences", json={"weekly_summary": False}, headers=alice.headers
    )
    assert off.json()["weekly_summary"] is False
    assert await send_weekly_summaries(session_factory, settings, now=SUNDAY) == 0
