"""Tausch-Rechner: Wert von „Ich gebe“ gegen „Ich bekomme“ – bewerten, speichern, vergleichen.

Eine Zeile beschreibt Karte oder Produkt mit Fassung, Zustand, Slab und Menge. Sie kommt
* aus der **eigenen Sammlung** (``item_id``; dann zählt auch ein eigener Preis),
* aus dem **Showcase eines Freundes** (``item_id`` aus einem freigegebenen Ordner) oder
* aus dem **Katalog** (``card_id``/``product_id``).

Bewertet wird genau wie in der Sammlung (``app.services.valuation``). Gespeicherte Tausche
behalten die damaligen Stückwerte; „heute“ wird bei jedem Abruf neu gerechnet.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CollectionItem, GradingCompany, Product, Trade, User
from app.providers.pricing import CONDITIONS
from app.services.display_names import card_display_name, set_display_name
from app.services.errors import InvalidInputError, NotFoundError
from app.services.friends import FriendsService
from app.services.pricing import PriceService
from app.services.sealed import sealed_prices
from app.services.valuation import CENT, unit_value

Side = Literal["give", "get"]
ZERO = Decimal("0.00")
MAX_LINES = 100
MAX_TRADES_PER_USER = 500


@dataclass(frozen=True)
class TradeLine:
    side: Side
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant: str = "normal"
    condition: str | None = "NM"
    grading_company: str | None = None
    grade: str | None = None
    quantity: int = 1
    custom_price: Decimal | None = None
    """Nur bei eigenen Positionen mit Eigenpreis."""


@dataclass(frozen=True)
class ValuedLine:
    line: TradeLine
    label: str
    image_url: str | None
    unit_value: Decimal | None

    @property
    def total(self) -> Decimal | None:
        if self.unit_value is None:
            return None
        return (self.unit_value * self.line.quantity).quantize(CENT)


@dataclass(frozen=True)
class TradeResult:
    lines: list[ValuedLine]

    def value(self, side: Side) -> Decimal:
        return sum((v.total or ZERO for v in self.lines if v.line.side == side), ZERO)

    @property
    def unvalued(self) -> int:
        return sum(1 for v in self.lines if v.unit_value is None)


def _label(card: Card | None, product: Product | None, line: TradeLine) -> str:
    if product is not None:
        return product.name
    if card is None:
        return "Unbekannt"
    parts = [f"{card_display_name(card)} ({set_display_name(card.card_set)} {card.number})"]
    if line.grading_company:
        parts.append(f"{line.grading_company} {line.grade or ''}".strip())
    else:
        if line.variant == "reverse":
            parts.append("Reverse Holo")
        if line.condition and line.condition != "NM":
            parts.append(line.condition)
    return " · ".join(parts)


class TradeService:
    def __init__(self, session: AsyncSession, owner: User, prices: PriceService) -> None:
        self._session = session
        self._owner = owner
        self._prices = prices

    async def line_from_item(self, side: Side, item_id: uuid.UUID, quantity: int) -> TradeLine:
        """Zeile aus eigener Position oder aus dem Showcase eines Freundes."""
        item = await self._session.get(CollectionItem, item_id)
        own = item is not None and item.user_id == self._owner.id
        if not own:
            item = (
                await FriendsService(self._session, self._owner, self._prices).shared_item(item_id)
            ).item
        assert item is not None  # noqa: S101 – sonst NotFoundError oben
        return TradeLine(
            side=side,
            card_id=item.card_id,
            product_id=item.product_id,
            variant=item.variant,
            condition=item.condition,
            grading_company=item.grading_company.value if item.grading_company else None,
            grade=item.grade,
            quantity=min(quantity, item.quantity),
            custom_price=item.custom_price if own else None,
        )

    async def evaluate(self, lines: Sequence[TradeLine]) -> TradeResult:
        if len(lines) > MAX_LINES:
            raise InvalidInputError(f"Höchstens {MAX_LINES} Zeilen.")
        card_ids = [line.card_id for line in lines if line.card_id]
        product_ids = [line.product_id for line in lines if line.product_id]
        cards = {
            c.id: c
            for c in (await self._session.scalars(select(Card).where(Card.id.in_(card_ids))))
            .unique()
            .all()
        }
        products = {
            p.id: p
            for p in (
                await self._session.scalars(select(Product).where(Product.id.in_(product_ids)))
            )
            .unique()
            .all()
        }
        prices = await self._prices.prices_for_cards(list(cards), self._owner)
        sealed = await sealed_prices(self._session, list(products))
        valued = []
        for line in lines:
            card = cards.get(line.card_id) if line.card_id else None
            product = products.get(line.product_id) if line.product_id else None
            if (line.card_id and card is None) or (line.product_id and product is None):
                raise NotFoundError("Karte oder Produkt nicht gefunden.")
            if (card is None) == (product is None):
                raise InvalidInputError("Je Zeile genau eine Karte oder ein Produkt.")
            if line.condition is not None and line.condition not in CONDITIONS:
                raise InvalidInputError("Unbekannter Zustand.")
            transient = CollectionItem(
                card_id=line.card_id,
                product_id=line.product_id,
                variant=line.variant,
                condition=None if line.grading_company or product else (line.condition or "NM"),
                grading_company=GradingCompany(line.grading_company)
                if line.grading_company
                else None,
                grade=line.grade,
                quantity=line.quantity,
                custom_price=line.custom_price,
            )
            value = unit_value(
                transient,
                prices.get(card.id) if card else None,
                sealed.get(product.id) if product else None,
            )
            image = card.image_url if card else (product.image_url if product else None)
            valued.append(ValuedLine(line, _label(card, product, line), image, value.unit_value))
        return TradeResult(valued)

    # -------------------------------------------------------------- Speichern

    async def save(
        self, lines: Sequence[TradeLine], *, partner: str | None, note: str | None
    ) -> Trade:
        if not lines:
            raise InvalidInputError("Ein Tausch braucht mindestens eine Karte.")
        count = len(
            (
                await self._session.scalars(select(Trade.id).where(Trade.user_id == self._owner.id))
            ).all()
        )
        if count >= MAX_TRADES_PER_USER:
            raise InvalidInputError("Zu viele gespeicherte Tausche – bitte alte löschen.")
        result = await self.evaluate(lines)
        trade = Trade(
            user_id=self._owner.id,
            partner=(partner or "").strip() or None,
            note=(note or "").strip() or None,
            lines=[_line_json(v) for v in result.lines],
            give_value=result.value("give"),
            get_value=result.value("get"),
        )
        self._session.add(trade)
        await self._session.flush()
        await self._session.refresh(trade)
        return trade

    async def trades(self) -> list[tuple[Trade, TradeResult]]:
        """Gespeicherte Tausche (neueste zuerst) mit heutiger Bewertung."""
        rows = (
            await self._session.scalars(
                select(Trade)
                .where(Trade.user_id == self._owner.id)
                .order_by(Trade.created_at.desc())
            )
        ).all()
        return [(trade, await self.evaluate(_lines_from_json(trade.lines))) for trade in rows]

    async def delete(self, trade_id: uuid.UUID) -> None:
        trade = await self._session.scalar(
            select(Trade).where(Trade.id == trade_id, Trade.user_id == self._owner.id)
        )
        if trade is None:
            raise NotFoundError("Tausch nicht gefunden.")
        await self._session.delete(trade)
        await self._session.flush()


def _line_json(valued: ValuedLine) -> dict[str, Any]:
    data = {
        k: (str(v) if isinstance(v, uuid.UUID | Decimal) else v)
        for k, v in asdict(valued.line).items()
    }
    data["label"] = valued.label
    data["image_url"] = valued.image_url
    data["unit_value"] = str(valued.unit_value) if valued.unit_value is not None else None
    return data


def _lines_from_json(lines: list[dict[str, Any]]) -> list[TradeLine]:
    def uid(value: Any) -> uuid.UUID | None:
        return uuid.UUID(value) if value else None

    return [
        TradeLine(
            side=line["side"],
            card_id=uid(line.get("card_id")),
            product_id=uid(line.get("product_id")),
            variant=line.get("variant", "normal"),
            condition=line.get("condition"),
            grading_company=line.get("grading_company"),
            grade=line.get("grade"),
            quantity=int(line.get("quantity", 1)),
            custom_price=Decimal(line["custom_price"]) if line.get("custom_price") else None,
        )
        for line in lines
    ]
