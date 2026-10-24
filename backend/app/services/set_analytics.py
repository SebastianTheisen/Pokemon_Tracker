"""Set-Analyse (wie Collectr „Set Analytics“) aus dem täglichen Cardmarket-Preisführer.

Der Preisführer enthält für **jede** Karte eines Sets Trend sowie Ø 1, Ø 7 und Ø 30 Tage –
auch für Reverse Holo (``…-holo``). Daraus, ohne eigene Historie:

* **Setwert:** Summe der Trendpreise (eine Karte je Nummer); **Master-Set** zusätzlich die
  Reverse-Holo-Trends.
* **Veränderung (≈ 30 Tage):** Trend gegenüber Ø 30 Tage – je Karte und für das ganze Set.
* **Stabilität:** Median der Abweichung Ø 1 Tag ↔ Ø 30 Tage über alle Karten ab 1 €;
  unter 5 % „ruhig“, unter 15 % „normal“, sonst „bewegt“.
* **Gewinner/Verlierer:** größte Veränderung (Karten ab 1 €, mindestens 5 %).
* **Wertvollste Karten:** höchster Trend.

Verkaufszahlen stehen nicht im Preisführer – daher keine „Sales Volume“.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CmPrice
from app.services.cardmarket_catalog import resolve_product
from app.services.errors import NotFoundError

MIN_PRICE = 1.0
MIN_MOVE = 0.05
CALM = 0.05  # Schwankung unter 5 %: „ruhig“
NORMAL = 0.15  # unter 15 %: „normal“, sonst „bewegt“
TOP = 5
Stability = Literal["ruhig", "normal", "bewegt"]
CENT = Decimal("0.01")


@dataclass(frozen=True)
class CardMarket:
    card: Card
    trend: float
    avg1: float | None
    avg30: float | None
    reverse_trend: float | None

    @property
    def change(self) -> float | None:
        """Trend gegenüber Ø 30 Tage (Anteil, z. B. 0.12 = +12 %)."""
        if not self.avg30:
            return None
        return (self.trend - self.avg30) / self.avg30


@dataclass(frozen=True)
class SetAnalytics:
    card_set: CardSet
    cards_total: int
    cards: list[CardMarket]

    @property
    def cards_priced(self) -> int:
        return len(self.cards)

    @property
    def set_value(self) -> Decimal:
        return _money(sum(c.trend for c in self.cards))

    @property
    def master_value(self) -> Decimal:
        return _money(sum(c.trend + (c.reverse_trend or 0) for c in self.cards))

    @property
    def change(self) -> float | None:
        """Setwert gegenüber Ø 30 Tage (nur Karten mit beiden Werten)."""
        pairs = [(c.trend, c.avg30) for c in self.cards if c.avg30]
        before = sum(avg30 for _, avg30 in pairs)
        return (sum(t for t, _ in pairs) - before) / before if before else None

    @property
    def volatility(self) -> float | None:
        swings = [
            abs(c.avg1 - c.avg30) / c.avg30
            for c in self.cards
            if c.avg1 is not None and c.avg30 and c.trend >= MIN_PRICE
        ]
        return statistics.median(swings) if swings else None

    @property
    def stability(self) -> Stability | None:
        swing = self.volatility
        if swing is None:
            return None
        return "ruhig" if swing < CALM else ("normal" if swing < NORMAL else "bewegt")

    def _movers(self) -> list[CardMarket]:
        return [
            c
            for c in self.cards
            if c.trend >= MIN_PRICE and c.change is not None and abs(c.change) >= MIN_MOVE
        ]

    @property
    def gainers(self) -> list[CardMarket]:
        up = [c for c in self._movers() if (c.change or 0) > 0]
        return sorted(up, key=lambda c: c.change or 0, reverse=True)[:TOP]

    @property
    def losers(self) -> list[CardMarket]:
        down = [c for c in self._movers() if (c.change or 0) < 0]
        return sorted(down, key=lambda c: c.change or 0)[:TOP]

    @property
    def top_cards(self) -> list[CardMarket]:
        return sorted(self.cards, key=lambda c: c.trend, reverse=True)[:10]


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT)


def _number(metrics: dict[str, float], key: str) -> float | None:
    value = metrics.get(key)
    return float(value) if isinstance(value, int | float) and value > 0 else None


async def set_analytics(session: AsyncSession, set_id: uuid.UUID) -> SetAnalytics:
    card_set = await session.get(CardSet, set_id)
    if card_set is None:
        raise NotFoundError("Set nicht gefunden.")
    cards = list((await session.scalars(select(Card).where(Card.set_id == set_id))).all())
    products = {card.id: (await resolve_product(session, card)).product_id for card in cards}
    ids = [p for p in products.values() if p is not None]
    guide = {
        row.id_product: row.metrics
        for row in (await session.scalars(select(CmPrice).where(CmPrice.id_product.in_(ids))))
    }
    markets = []
    for card in cards:
        metrics = guide.get(products[card.id] or -1)
        trend = _number(metrics, "trend") if metrics else None
        if metrics is None or trend is None:
            continue
        reverse = (card.variants or {}).get("reverse")
        markets.append(
            CardMarket(
                card=card,
                trend=trend,
                avg1=_number(metrics, "avg1"),
                avg30=_number(metrics, "avg30"),
                reverse_trend=_number(metrics, "trend-holo") if reverse else None,
            )
        )
    return SetAnalytics(card_set=card_set, cards_total=len(cards), cards=markets)
