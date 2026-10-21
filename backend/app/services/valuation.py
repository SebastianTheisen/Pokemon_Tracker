"""Wert einer Sammlungsposition (Nutzerentscheidung 17.10.2026: „Zustandspreis“).

Reihenfolge je Stück:

1. **Eigener Preis** (``custom_price``) – immer vorrangig, gekennzeichnet als „dein Preis“.
2. Nur Rohkarten: **belegter Zustandspreis** einer externen Quelle für Variante + Zustand
   (z. B. ausgelesene Cardmarket-Angebote).
3. Nur Rohkarten: **Schätzung** = NM-Basis × Zustandsfaktor (gekennzeichnet).
4. Gegradete Karten: **Median der ausgelesenen eBay-Verkäufe** mit gleicher Firma und Note.
5. Versiegelte Produkte: **Cardmarket-Preisführer** (Median aus Trend, Ø 7, Ø 30), wenn das
   Produkt mit Cardmarket verknüpft ist.
6. Sonst **kein Wert**.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.models import CollectionItem
from app.services.ebay_sold import SOURCE as EBAY_SOLD
from app.services.ebay_sold import graded_variant
from app.services.pricing import CardPrices
from app.services.sealed import SealedPrice

ItemKind = Literal["raw", "graded", "sealed"]
ValueKind = Literal["manual", "external", "estimated", "none"]
CENT = Decimal("0.01")
DEFAULT_CONDITION = "NM"


def item_kind(item: CollectionItem) -> ItemKind:
    if item.product_id is not None:
        return "sealed"
    if item.grading_company is not None:
        return "graded"
    return "raw"


@dataclass(frozen=True)
class ItemValue:
    """Bewertung einer Position."""

    kind: ValueKind
    unit_value: Decimal | None
    total_value: Decimal | None
    source: str | None = None
    basis: str | None = None
    change: Decimal | None = None
    """Veränderung des Gesamtwerts seit dem Hinzufügen (Zukäufe zählen nicht mit)."""

    @property
    def has_value(self) -> bool:
        return self.unit_value is not None


NO_VALUE = ItemValue(kind="none", unit_value=None, total_value=None)


def unit_value(
    item: CollectionItem, prices: CardPrices | None, sealed: SealedPrice | None = None
) -> ItemValue:
    """Stückwert ohne Menge (für ``value_at_add`` und Anzeige)."""
    if item.custom_price is not None:
        return ItemValue("manual", item.custom_price, item.custom_price, source="manual")
    kind = item_kind(item)
    if kind == "sealed":
        return _sealed_value(sealed)
    if prices is None:
        return NO_VALUE
    if kind == "graded" and item.grading_company is not None:
        return _graded_value(item.grading_company, item.grade, prices)
    return _raw_value(item, prices)


def _raw_value(item: CollectionItem, prices: CardPrices) -> ItemValue:
    """Zustandspreis der Variante: externer Beleg oder Schätzung."""
    condition = item.condition or DEFAULT_CONDITION
    match = next(
        (
            price
            for price in prices.conditions
            if price.variant == item.variant and price.condition == condition
        ),
        None,
    )
    if match is None:
        return NO_VALUE
    basis = None
    if match.kind == "estimated":
        basis = f"{match.basis_metric} = {match.basis_value} × {match.factor}"
        if match.language_factor is not None and match.language_factor != 1:
            basis += f" × Sprache {match.language_factor}"
    return ItemValue(match.kind, match.value, match.value, source=match.source, basis=basis)


def _sealed_value(sealed: SealedPrice | None) -> ItemValue:
    """Versiegeltes Produkt: Wert aus dem Cardmarket-Preisführer (falls verknüpft)."""
    if sealed is None:
        return NO_VALUE
    return ItemValue(
        "external", sealed.value, sealed.value, source="cardmarket", basis=sealed.basis
    )


def value_item(
    item: CollectionItem,
    prices: Mapping[uuid.UUID, CardPrices],
    sealed: Mapping[uuid.UUID, SealedPrice] | None = None,
) -> ItemValue:
    """Bewertung inklusive Menge und Veränderung seit dem Hinzufügen."""
    single = unit_value(
        item,
        prices.get(item.card_id) if item.card_id else None,
        (sealed or {}).get(item.product_id) if item.product_id else None,
    )
    if single.unit_value is None:
        return single
    total = (single.unit_value * item.quantity).quantize(CENT)
    change = (
        ((single.unit_value - item.value_at_add) * item.quantity).quantize(CENT)
        if item.value_at_add is not None
        else None
    )
    return ItemValue(
        kind=single.kind,
        unit_value=single.unit_value,
        total_value=total,
        source=single.source,
        basis=single.basis,
        change=change,
    )


def _graded_value(company: str, grade: str | None, prices: CardPrices) -> ItemValue:
    """Median der gespeicherten eBay-Verkäufe mit gleicher Grading-Firma und Note."""
    variant = graded_variant(company, grade)
    offer = next((o for o in prices.offers if o.source == EBAY_SOLD and o.variant == variant), None)
    median = offer.metrics.get("median") if offer is not None else None
    if offer is None or median is None:
        return NO_VALUE
    count = offer.metrics.get("count")
    basis = f"Median aus {int(count)} eBay-Verkäufen" if count is not None else None
    return ItemValue("external", median, median, source=EBAY_SOLD, basis=basis)
