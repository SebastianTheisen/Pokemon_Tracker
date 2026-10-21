"""Hintergrund-Worker: tägliche Preisaktualisierung und Scanner-Pflege.

Start (im Container eigener Dienst ``worker``)::

    python -m app.worker

Zur eingestellten Uhrzeit (``PT_PRICE_REFRESH_TIME``, Ortszeit ``PT_TIMEZONE``) werden die
Preise aller vorgemerkten Karten neu geholt (Sammlungen, Merklisten, angesehene Karten) und
danach der Tageswert jeder Sammlung gespeichert. Daraus entstehen die Kurven.
Fehler einzelner Karten oder Quellen brechen die Runde nicht ab.

Danach räumt der Worker auf: alte Einträge im Scan-Protokoll (``PT_SCAN_LOG_RETENTION_DAYS``)
und Referenzbild-Dateien, deren Karte oder Nutzer gelöscht wurde.

Unabhängig davon ergänzt der Worker alle ``PT_IMAGE_IMPORT_INTERVAL_DAYS`` Tage fehlende
Kartenbilder (:mod:`app.services.image_import`). Der erste Lauf startet kurz nach dem Start,
wenn noch nie einer fertig wurde; er dauert wegen der sanften Abfrage einige Stunden.

Alle ``PT_CARDMARKET_CATALOG_INTERVAL_HOURS`` Stunden lädt der Worker den offiziellen
Cardmarket-Katalog samt Preisführer und verknüpft neue Sets mit ihrer Cardmarket-Ausgabe
(:mod:`app.services.cardmarket_catalog`).

Alle ``PT_CARD_DETAILS_INTERVAL_HOURS`` Stunden holt er fehlende Kartendetails aus TCGdex
(Seltenheit, Varianten, Illustrator; :mod:`app.services.card_details`). Der erste Lauf
betrifft den ganzen Katalog und dauert einige Stunden, danach nur neue Karten.
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
from app.scanner.storage import ReferenceStore
from app.services.card_details import sync_card_details
from app.services.cardmarket_catalog import last_successful_import, run_catalog_import
from app.services.collection import CollectionService, users_with_items
from app.services.image_import import last_finished_run, last_run_incomplete, run_image_import
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService, tracked_card_ids
from app.services.scan import prune_reference_files, purge_scan_logs

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


@dataclass
class HousekeepingSummary:
    scan_logs_deleted: int = 0
    reference_files_deleted: int = 0


async def scanner_housekeeping(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> HousekeepingSummary:
    """Altes Scan-Protokoll löschen und verwaiste Referenzbild-Dateien entfernen."""
    async with session_factory() as session:
        summary = HousekeepingSummary(
            scan_logs_deleted=await purge_scan_logs(
                session, retention_days=settings.scan_log_retention_days
            )
        )
        await session.commit()
        summary.reference_files_deleted = await prune_reference_files(
            session, ReferenceStore(settings.scanner_data_dir)
        )
    log.info(
        "scanner.housekeeping_done",
        scan_logs_deleted=summary.scan_logs_deleted,
        reference_files_deleted=summary.reference_files_deleted,
    )
    return summary


IMAGE_IMPORT_START_DELAY = timedelta(minutes=5)


def next_image_import(
    now: datetime,
    last_finished: datetime | None,
    interval_days: int,
    *,
    retry_after: timedelta | None = None,
) -> datetime | None:
    """Wann ist der nächste Bild-Import fällig? ``None`` = abgeschaltet.

    ``retry_after``: Der letzte Lauf war unvollständig (Quelle abgebrochen) – dann früher.
    """
    if interval_days <= 0:
        return None
    earliest = now + IMAGE_IMPORT_START_DELAY
    if last_finished is None:
        return earliest
    wait = retry_after if retry_after is not None else timedelta(days=interval_days)
    return max(earliest, last_finished + wait)


async def image_import_forever(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Endlosschleife des Bild-Imports (läuft neben der Preisrunde)."""
    while True:
        try:
            async with session_factory() as session:
                last = await last_finished_run(session)
                incomplete = await last_run_incomplete(session)
        except Exception:  # z. B. Migration beim Start noch nicht durch
            log.exception("worker.image_import_status_failed")
            await asyncio.sleep(IMAGE_IMPORT_START_DELAY.total_seconds())
            continue
        due = next_image_import(
            datetime.now(UTC),
            last,
            settings.image_import_interval_days,
            retry_after=timedelta(hours=settings.image_import_retry_hours) if incomplete else None,
        )
        if due is None:
            log.info("worker.image_import_disabled")
            return
        log.info("worker.image_import_scheduled", next_run=due.isoformat())
        await asyncio.sleep(max((due - datetime.now(UTC)).total_seconds(), 0))
        try:
            await run_image_import(session_factory, settings, sources=settings.image_import_sources)
        except Exception:
            log.exception("worker.image_import_failed")
            await asyncio.sleep(3600)  # nicht in einer Fehlerschleife hämmern


CARDMARKET_START_DELAY = timedelta(minutes=2)


def next_catalog_import(
    now: datetime, last_success: datetime | None, interval_hours: int
) -> datetime | None:
    """Wann ist der nächste Cardmarket-Import fällig? ``None`` = abgeschaltet."""
    if interval_hours <= 0:
        return None
    earliest = now + CARDMARKET_START_DELAY
    if last_success is None:
        return earliest
    return max(earliest, last_success + timedelta(hours=interval_hours))


async def cardmarket_forever(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, client: TcgdexClient
) -> None:
    """Endlosschleife des Cardmarket-Imports (Katalog, Preisführer, Ausgabe je Set)."""
    while True:
        try:
            async with session_factory() as session:
                last = await last_successful_import(session)
        except Exception:  # z. B. Migration beim Start noch nicht durch
            log.exception("worker.cardmarket_status_failed")
            await asyncio.sleep(CARDMARKET_START_DELAY.total_seconds())
            continue
        due = next_catalog_import(
            datetime.now(UTC), last, settings.cardmarket_catalog_interval_hours
        )
        if due is None:
            log.info("worker.cardmarket_disabled")
            return
        log.info("worker.cardmarket_scheduled", next_run=due.isoformat())
        await asyncio.sleep(max((due - datetime.now(UTC)).total_seconds(), 0))
        summary = await run_catalog_import(session_factory, settings, tcgdex=client)
        if summary.error:
            await asyncio.sleep(3600)  # nicht in einer Fehlerschleife hämmern


CARD_DETAILS_START_DELAY = timedelta(minutes=10)


async def card_details_forever(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, client: TcgdexClient
) -> None:
    """Endlosschleife: fehlende Kartendetails nachladen, dann warten."""
    if settings.card_details_interval_hours <= 0:
        log.info("worker.card_details_disabled")
        return
    await asyncio.sleep(CARD_DETAILS_START_DELAY.total_seconds())
    while True:
        try:
            await sync_card_details(
                session_factory, client, concurrency=settings.card_details_concurrency
            )
        except Exception:
            log.exception("worker.card_details_failed")
        await asyncio.sleep(timedelta(hours=settings.card_details_interval_hours).total_seconds())


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
            # Bild-Import läuft unabhängig (dauert Stunden); Referenz halten, am Ende beenden.
            images = asyncio.create_task(image_import_forever(session_factory, settings))
            cardmarket = asyncio.create_task(cardmarket_forever(session_factory, settings, client))
            details = asyncio.create_task(card_details_forever(session_factory, settings, client))
            try:
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
                    try:
                        await scanner_housekeeping(session_factory, settings)
                    except Exception:
                        log.exception("worker.housekeeping_failed")
            finally:
                images.cancel()
                cardmarket.cancel()
                details.cancel()
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
