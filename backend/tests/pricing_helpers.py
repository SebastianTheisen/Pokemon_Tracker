"""Hilfsmittel für Preistests: steuerbare Preisquelle und Testkarten."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet
from app.providers.pricing import CardRef, PriceKind, PriceQuote

UPDATED = datetime(2026, 10, 16, 8, 51, tzinfo=UTC)
CM_URL = "https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273"


def cardmarket(
    metric: str,
    value: str,
    *,
    variant: str = "normal",
    updated: datetime = UPDATED,
    condition: str | None = None,
    source: str = "cardmarket",
    currency: str = "EUR",
) -> PriceQuote:
    return PriceQuote(
        source=source,
        variant=variant,
        metric=metric,
        value=Decimal(value),
        currency=currency,
        source_updated_at=updated,
        source_url=CM_URL,
        condition=condition,
    )


@dataclass
class FakeProvider:
    """Preisquelle für Tests: liefert ``quotes``, wirft ``error`` oder wartet ``delay``."""

    name: str = "tcgdex"
    kind: PriceKind = "verified"
    quotes: list[PriceQuote] = field(default_factory=list)
    error: Exception | None = None
    delay: float = 0.0
    calls: list[CardRef] = field(default_factory=list)

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        self.calls.append(card)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return list(self.quotes)


async def make_card(
    factory: async_sessionmaker[AsyncSession],
    *,
    external_id: str | None = "swsh7-215",
    name: str = "Nachtara VMAX",
    number: str = "215",
    language: str = "de",
) -> Card:
    async with factory() as session:
        card_set = CardSet(
            external_id=f"set-{external_id or name}", language=language, name="Drachenwandel"
        )
        session.add(card_set)
        await session.flush()
        card = Card(
            external_id=external_id,
            language=language,
            set_id=card_set.id,
            number=number,
            number_norm=number.lstrip("0") or "0",
            name=name,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card, ["card_set"])
        return card
