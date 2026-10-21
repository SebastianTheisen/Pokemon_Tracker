"""Preisbewegungen der eigenen Sammlung: Gewinner und Verlierer der letzten Tage.

Grundlage ist der tägliche Cardmarket-Trend, den der Worker für alle Sammlungskarten speichert
(``price_points``, Quelle ``cardmarket``, Kennzahl ``trend``). Verglichen wird je Karte und
Variante der neueste Wert mit dem letzten Wert vor Beginn des Zeitraums; gewichtet mit der
Anzahl im Besitz (alle Ordner zusammen). Gegradete Karten (eBay-Median) und versiegelte
Produkte haben keinen täglichen Verlauf und fehlen hier – ihr Wert steckt in der Wertkurve.

Rauschen wird ausgeblendet: Karten unter :data:`MIN_VALUE` Euro und Änderungen unter
:data:`MIN_CHANGE_PCT` Prozent.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CollectionItem, PricePoint
from app.providers.pricing.tcgdex_prices import CARDMARKET

MIN_VALUE = Decimal("1.00")
MIN_CHANGE_PCT = Decimal("5")
CENT = Decimal("0.01")
TREND = "trend"


@dataclass(frozen=True)
class Mover:
    card: Card
    variant: str
    quantity: int
    before: Decimal
    now: Decimal
    since: datetime

    @property
    def change(self) -> Decimal:
        """Veränderung des Gesamtwerts (alle Exemplare)."""
        return ((self.now - self.before) * self.quantity).quantize(CENT)

    @property
    def change_pct(self) -> Decimal:
        return ((self.now - self.before) / self.before * 100).quantize(Decimal("0.1"))


@dataclass
class Movers:
    days: int
    gainers: list[Mover] = field(default_factory=list)
    losers: list[Mover] = field(default_factory=list)


async def _trend_points(
    session: AsyncSession, card_ids: list[uuid.UUID], *, before: datetime | None
) -> dict[tuple[uuid.UUID, str], tuple[Decimal, datetime]]:
    """Neuester Trend je Karte und Variante (optional: neuester bis ``before``)."""
    statement = (
        select(
            PricePoint.card_id, PricePoint.variant, PricePoint.value, PricePoint.source_updated_at
        )
        .where(
            PricePoint.card_id.in_(card_ids),
            PricePoint.source == CARDMARKET,
            PricePoint.metric == TREND,
            PricePoint.condition.is_(None),
        )
        .ext(distinct_on(PricePoint.card_id, PricePoint.variant))
        .order_by(PricePoint.card_id, PricePoint.variant, PricePoint.source_updated_at.desc())
    )
    if before is not None:
        statement = statement.where(PricePoint.source_updated_at <= before)
    rows = await session.execute(statement)
    return {(row.card_id, row.variant): (row.value, row.source_updated_at) for row in rows}


async def price_movers(
    session: AsyncSession, owner_id: uuid.UUID, *, now: datetime, days: int = 7, limit: int = 5
) -> Movers:
    """Größte Gewinner und Verlierer (nach Veränderung des Gesamtwerts) im Zeitraum."""
    holdings: defaultdict[tuple[uuid.UUID, str], int] = defaultdict(int)
    rows = await session.execute(
        select(CollectionItem.card_id, CollectionItem.variant, func.sum(CollectionItem.quantity))
        .where(
            CollectionItem.user_id == owner_id,
            CollectionItem.card_id.is_not(None),
            CollectionItem.grading_company.is_(None),
        )
        .group_by(CollectionItem.card_id, CollectionItem.variant)
    )
    for card_id, variant, quantity in rows:
        if card_id is not None:
            holdings[(card_id, variant)] = int(quantity or 0)
    result = Movers(days=days)
    if not holdings:
        return result
    card_ids = list({card_id for card_id, _ in holdings})
    latest = await _trend_points(session, card_ids, before=None)
    earlier = await _trend_points(session, card_ids, before=now - timedelta(days=days))
    cards = {
        card.id: card
        for card in (await session.scalars(select(Card).where(Card.id.in_(card_ids)))).unique()
    }
    movers: list[Mover] = []
    for key, quantity in holdings.items():
        if key not in latest or key not in earlier or key[0] not in cards:
            continue
        (now_value, _), (before_value, since) = latest[key], earlier[key]
        if before_value < MIN_VALUE or now_value == before_value:
            continue
        mover = Mover(
            card=cards[key[0]],
            variant=key[1],
            quantity=quantity,
            before=before_value,
            now=now_value,
            since=since,
        )
        if abs(mover.change_pct) >= MIN_CHANGE_PCT:
            movers.append(mover)
    movers.sort(key=lambda m: m.change, reverse=True)
    result.gainers = [m for m in movers if m.change > 0][:limit]
    result.losers = sorted((m for m in movers if m.change < 0), key=lambda m: m.change)[:limit]
    return result
