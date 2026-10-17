"""Hintergrund-Worker: tägliche Preisaktualisierung.

Start (im Container eigener Dienst ``worker``)::

    python -m app.worker

Zur eingestellten Uhrzeit (``PT_PRICE_REFRESH_TIME``, Ortszeit ``PT_TIMEZONE``) werden die
Preise aller vorgemerkten Karten neu geholt (Sammlungen, Merklisten, angesehene Karten) und
danach der Tageswert jeder Sammlung gespeichert. Daraus entstehen die Kurven.
Fehler einzelner Karten oder Quellen brechen die Runde nicht ab.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.models import Card
from app.providers.pricing import PriceProvider
from app.providers.pricing.registry import build_price_providers
from app.providers.tcgdex import TcgdexClient
from app.services.collection import CollectionService, users_with_items
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService, tracked_card_ids

log = structlog.get_logger(__name__)


@dataclass
class RefreshSummary:
    cards: int = 0
    quotes_stored: int = 0
    failed_cards: int = 0
    snapshots: int = 0


def next_run_after(now: datetime, at: str, timezone: str) -> datetime:
    """Nächster Zeitpunkt ``at`` (``"HH:MM"``, Ortszeit) nach ``now`` – als UTC.

    Berücksichtigt Sommer-/Winterzeit, weil die Ortszeit je Tag neu umgerechnet wird.
    """
    zone = ZoneInfo(timezone)
    hour, minute = (int(part) for part in at.split(":"))
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
    if candidate <= local_now:
        candidate = datetime.combine(
            local_now.date() + timedelta(days=1), time(hour, minute), tzinfo=zone
        )
    return candidate.astimezone(UTC)


async def refresh_tracked_prices(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    providers: Sequence[PriceProvider],
    health: SourceHealth,
) -> RefreshSummary:
    """Eine Runde: alle vorgemerkten Karten aktualisieren (begrenzt parallel)."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        card_ids = await tracked_card_ids(session, settings, now)
    summary = RefreshSummary(cards=len(card_ids))
    semaphore = asyncio.Semaphore(settings.price_refresh_concurrency)

    async def refresh_one(card_id: uuid.UUID) -> None:
        async with semaphore, session_factory() as session:
            card = await session.get(Card, card_id)
            if card is None:
                return
            service = PriceService(session, settings, providers, health)
            report = await service.refresh(card, force=True)
            await session.commit()
            summary.quotes_stored += report.quotes_stored
            if "failed" in report.outcomes.values():
                summary.failed_cards += 1

    await asyncio.gather(*(refresh_one(card_id) for card_id in card_ids))

    # Danach Tageswert jeder Sammlung speichern (Grundlage der Wertkurve).
    async with session_factory() as session:
        prices = PriceService(session, settings, providers, health)
        for owner in await users_with_items(session):
            await CollectionService(session, owner, prices).take_snapshot()
            summary.snapshots += 1
        await session.commit()

    log.info(
        "pricing.refresh_done",
        cards=summary.cards,
        stored=summary.quotes_stored,
        failed=summary.failed_cards,
        snapshots=summary.snapshots,
    )
    return summary


async def run_forever(settings: Settings) -> None:
    """Endlosschleife: bis zur nächsten Uhrzeit schlafen, Runde ausführen, wiederholen."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    health = SourceHealth(
        threshold=settings.price_breaker_threshold,
        pause=timedelta(minutes=settings.price_breaker_pause_minutes),
    )
    try:
        async with TcgdexClient(
            base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
        ) as client:
            providers = build_price_providers(settings, client)
            while True:
                next_run = next_run_after(
                    datetime.now(UTC), settings.price_refresh_time, settings.timezone
                )
                log.info("worker.sleeping", next_run=next_run.isoformat())
                await asyncio.sleep((next_run - datetime.now(UTC)).total_seconds())
                try:
                    await refresh_tracked_prices(session_factory, settings, providers, health)
                except Exception:
                    log.exception("worker.refresh_failed")  # nächste Runde versucht es erneut
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
