"""Wochenrückblick: sonntags nach der Preisrunde eine Mitteilung „Deine Woche“.

Nur für Nutzer mit eingeschalteten Mitteilungen und ``weekly_summary`` (Standard: an).
Grundlage sind die gespeicherten Tageswerte (heute gegen den letzten Wert vor ≥ 7 Tagen)
und die größte Preisbewegung einer eigenen Rohkarte (Cardmarket-Trend, 7 Tage).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import PortfolioSnapshot, PushSubscription, User, UserSettings
from app.services.display_names import card_display_name
from app.services.movers import price_movers
from app.services.push import PushMessage, notify_user

log = structlog.get_logger(__name__)

SUMMARY_WEEKDAY = 6  # Sonntag (Montag = 0)


def is_summary_day(now: datetime, timezone: str) -> bool:
    return now.astimezone(ZoneInfo(timezone)).weekday() == SUMMARY_WEEKDAY


def _euro(value: Decimal) -> str:
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sign = "−" if value < 0 else ("+" if value > 0 else "")
    return f"{sign}{text} €"


@dataclass(frozen=True)
class WeeklyNumbers:
    total: Decimal
    change: Decimal
    percent: Decimal | None


async def weekly_numbers(session: AsyncSession, user: User, today: date) -> WeeklyNumbers | None:
    """Wert heute gegen den letzten Tageswert vor mindestens 7 Tagen (sonst ``None``)."""

    async def snapshot(until: date) -> PortfolioSnapshot | None:
        return await session.scalar(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.user_id == user.id, PortfolioSnapshot.day <= until)
            .order_by(PortfolioSnapshot.day.desc())
            .limit(1)
        )

    now, before = await snapshot(today), await snapshot(today - timedelta(days=7))
    if now is None or before is None or now.day == before.day:
        return None
    change = now.total_value - before.total_value
    percent = (
        (change / before.total_value * 100).quantize(Decimal("0.1")) if before.total_value else None
    )
    return WeeklyNumbers(total=now.total_value, change=change, percent=percent)


def weekly_message(numbers: WeeklyNumbers, top: tuple[str, Decimal] | None) -> PushMessage:
    pct = "" if numbers.percent is None else f" · {numbers.percent:+} %".replace(".", ",")
    body = f"Wert {_euro(numbers.total).lstrip('+')} ({_euro(numbers.change)}{pct})."
    if top is not None:
        body += f" Top: {top[0]} {_euro(top[1])}."
    return PushMessage(title="Deine Woche in der Kartenkiste", body=body, url="/", tag="weekly")


async def send_weekly_summaries(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Rückblick an alle, die ihn wollen und Mitteilungen eingeschaltet haben."""
    now = now or datetime.now(UTC)
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    sent = 0
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=20)
    try:
        async with session_factory() as session:
            users = (
                await session.scalars(
                    select(User)
                    .outerjoin(UserSettings, UserSettings.user_id == User.id)
                    .where(
                        User.is_active,
                        select(PushSubscription.id)
                        .where(PushSubscription.user_id == User.id)
                        .exists(),
                        UserSettings.weekly_summary.is_not(False),
                    )
                )
            ).all()
            for user in users:
                numbers = await weekly_numbers(session, user, today)
                if numbers is None:
                    continue
                movers = await price_movers(session, user.id, now=now, days=7, limit=1)
                top = (
                    (card_display_name(movers.gainers[0].card), movers.gainers[0].change)
                    if movers.gainers
                    else None
                )
                if await notify_user(
                    session, http, settings, user.id, weekly_message(numbers, top)
                ):
                    sent += 1
            await session.commit()
    finally:
        if own_client:
            await http.aclose()
    log.info("weekly.sent", users=sent)
    return sent
