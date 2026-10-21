"""Kartendetails aus TCGdex nachladen: Seltenheit, Varianten, Illustrator, Cardmarket-Produkt.

Der Katalog-Import liest nur die Set-Listen (Name, Nummer, Bild). Die Details stehen erst in
``GET /{lang}/cards/{id}`` – eine Anfrage je Karte. Der Worker holt sie deshalb im Hintergrund
nach (zuerst Deutsch und Englisch), danach nur noch für neue Karten:

* ``rarity`` (in der Sprache der Karte, z. B. „Selten, Holo“),
* ``variants`` – welche Fassungen es gibt (``normal``, ``reverse``, ``holo``,
  ``firstEdition``); die App bietet beim Hinzufügen nur diese an,
* ``illustrator``,
* nebenbei die Cardmarket-ID → verbessert die Verknüpfung mit dem Cardmarket-Katalog
  (:func:`app.services.cardmarket_catalog.learn_tcgdex_product`).

Karten, die TCGdex nicht (mehr) kennt (HTTP 404), gelten als abgeglichen; andere Fehler
werden beim nächsten Lauf erneut versucht.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSource
from app.providers.tcgdex import TcgdexClient, TcgdexError
from app.services.cardmarket_catalog import learn_tcgdex_product, tcgdex_product_id

log = structlog.get_logger(__name__)

HTTP_NOT_FOUND = 404
VARIANT_KEYS = ("normal", "reverse", "holo", "firstEdition")
# Reihenfolge des Abgleichs: zuerst die Sprachen, die die meisten von euch sammeln.
LANGUAGE_ORDER = ("de", "en", "ja", "zh-tw", "ko", "zh-cn")
WRITE_BATCH = 100

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class CardDetails:
    rarity: str | None
    illustrator: str | None
    variants: dict[str, bool] | None
    cardmarket_product_id: int | None


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:limit]


def parse_details(data: dict[str, Any]) -> CardDetails:
    """Relevante Felder aus der TCGdex-Antwort; Unbekanntes bleibt ``None``."""
    raw_variants = data.get("variants")
    variants = (
        {key: bool(raw_variants[key]) for key in VARIANT_KEYS if key in raw_variants}
        if isinstance(raw_variants, dict)
        else None
    )
    return CardDetails(
        rarity=_text(data.get("rarity"), 100),
        illustrator=_text(data.get("illustrator"), 120),
        variants=variants or None,
        cardmarket_product_id=tcgdex_product_id(data),
    )


async def apply_details(
    session: AsyncSession, card: Card, details: CardDetails, *, now: datetime
) -> None:
    """Details übernehmen (vorhandene Werte bleiben, wenn TCGdex nichts liefert)."""
    card.rarity = details.rarity or card.rarity
    card.illustrator = details.illustrator or card.illustrator
    card.variants = details.variants or card.variants
    card.details_synced_at = now
    if details.cardmarket_product_id is not None:
        await learn_tcgdex_product(session, card, details.cardmarket_product_id)


@dataclass
class DetailsReport:
    pending: int = 0
    updated: int = 0
    not_found: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


async def sync_card_details(
    session_factory: async_sessionmaker[AsyncSession],
    client: TcgdexClient,
    *,
    concurrency: int = 4,
    limit: int | None = None,
    clock: Clock = _utc_now,
) -> DetailsReport:
    """Details aller Karten ohne Abgleich holen (höchstens ``limit``)."""
    language_rank = case(
        {language: rank for rank, language in enumerate(LANGUAGE_ORDER)},
        value=Card.language,
        else_=len(LANGUAGE_ORDER),
    )
    statement = (
        select(Card.id, Card.language, Card.external_id)
        .where(
            Card.details_synced_at.is_(None),
            Card.external_id.is_not(None),
            Card.source == CardSource.TCGDEX,
        )
        .order_by(language_rank, Card.external_id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    async with session_factory() as session:
        pending = (await session.execute(statement)).all()
    report = DetailsReport(pending=len(pending))
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch(
        card_id: uuid.UUID, language: str, external_id: str
    ) -> tuple[uuid.UUID, CardDetails | None, bool]:
        """(Karte, Details oder None, gefunden?)"""
        async with semaphore:
            try:
                data = await client.get_card(language, external_id)
            except TcgdexError as exc:
                if exc.status_code == HTTP_NOT_FOUND:
                    return card_id, None, False
                if len(report.errors) < 5:  # noqa: PLR2004 – nur Beispiele berichten
                    report.errors.append(str(exc)[:200])
                report.failed += 1
                return card_id, None, True
        return card_id, parse_details(data), True

    tasks = [fetch(row.id, row.language, str(row.external_id)) for row in pending]
    batch: list[tuple[uuid.UUID, CardDetails | None, bool]] = []
    for next_result in asyncio.as_completed(tasks):
        batch.append(await next_result)
        if len(batch) >= WRITE_BATCH:
            await _write(session_factory, batch, report, clock())
            batch = []
    if batch:
        await _write(session_factory, batch, report, clock())
    log.info(
        "card_details.synced",
        pending=report.pending,
        updated=report.updated,
        not_found=report.not_found,
        failed=report.failed,
    )
    return report


async def _write(
    session_factory: async_sessionmaker[AsyncSession],
    batch: list[tuple[uuid.UUID, CardDetails | None, bool]],
    report: DetailsReport,
    now: datetime,
) -> None:
    async with session_factory() as session:
        for card_id, details, found in batch:
            card = await session.get(Card, card_id)
            if card is None:
                continue
            if details is not None:
                await apply_details(session, card, details, now=now)
                report.updated += 1
            elif not found:
                card.details_synced_at = now  # TCGdex kennt die Karte nicht – nicht erneut
                report.not_found += 1
        await session.commit()
