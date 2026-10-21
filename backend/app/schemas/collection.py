"""Schemas für Sammlung, Merkliste, Dashboard, Produkte und eigene Karten.

Geldbeträge sind Dezimal-Strings in EUR (z. B. ``"12.50"``), Stückpreise wenn nicht anders
angegeben.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints

from app.core.config import CatalogLanguage
from app.models import GradingCompany, ProductKind
from app.providers.pricing import Condition
from app.schemas.catalog import CardOut, SetOut, SetSummary
from app.services.collection import (
    CollectionSummary,
    EventMarker,
    HistoryEntry,
    KindTotals,
    SetOverview,
    ValuedItem,
)
from app.services.movers import Mover, Movers
from app.services.valuation import ItemValue

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
FolderName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Note = Annotated[str, StringConstraints(max_length=500)]
# Note, z. B. „10“, „9.5“ oder „10 BL“ (Black Label, z. B. Beckett/CGC).
Grade = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{1,2}(\.\d)?( BL)?$")]
Variant = Literal["normal", "reverse"]


# ---------------------------------------------------------------------- Ordner


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int
    created_at: datetime


class FolderCreate(BaseModel):
    name: FolderName


class FolderUpdate(BaseModel):
    name: FolderName | None = None
    sort_order: Annotated[int, Field(ge=0, le=1000)] | None = None


# --------------------------------------------------------------------- Produkte


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ProductKind
    language: str
    name: str
    image_url: str | None
    card_set: SetSummary | None
    cardmarket_product_id: int | None = None


class ProductCreate(BaseModel):
    kind: ProductKind
    language: CatalogLanguage
    name: Name
    set_id: uuid.UUID | None = None
    image_url: AnyHttpUrl | None = None


class ProductUpdate(BaseModel):
    kind: ProductKind | None = None
    name: Name | None = None
    set_id: uuid.UUID | None = None
    image_url: AnyHttpUrl | None = None


class CardCreate(BaseModel):
    """Fehlende Karte anlegen – Set per ID wählen oder per Namen neu anlegen."""

    name: Name
    number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    language: CatalogLanguage
    set_id: uuid.UUID | None = None
    set_name: Name | None = None
    image_url: AnyHttpUrl | None = None


class CardUpdate(BaseModel):
    name: Name | None = None
    number: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)] | None
    ) = None
    image_url: AnyHttpUrl | None = None


# ------------------------------------------------------------------ Positionen


class ItemCreate(BaseModel):
    folder_id: uuid.UUID | None = Field(default=None, description="Standard: erster Ordner.")
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant: Variant = "normal"
    condition: Condition | None = Field(default=None, description="Standard bei Karten: NM.")
    quantity: Annotated[int, Field(ge=1, le=9999)] = 1
    purchase_price: Money | None = None
    purchase_date: date | None = None
    custom_price: Money | None = None
    note: Note | None = None
    grading_company: GradingCompany | None = None
    grade: Grade | None = None


class ItemUpdate(BaseModel):
    """Nur gesetzte Felder werden geändert; ``null`` löscht z. B. den Eigenpreis."""

    folder_id: uuid.UUID | None = None
    variant: Variant | None = None
    condition: Condition | None = None
    quantity: Annotated[int, Field(ge=1, le=9999)] | None = None
    purchase_price: Money | None = None
    purchase_date: date | None = None
    custom_price: Money | None = None
    note: Note | None = None
    grade: Grade | None = None
    grading_company: GradingCompany | None = Field(
        default=None,
        description="Rohkarte ↔ Slab umstellen: Firma setzen bzw. ``null`` (dann Zustand NM).",
    )


class ValueOut(BaseModel):
    kind: Literal["manual", "external", "estimated", "none"] = Field(
        description=(
            "manual = dein Preis, external = belegt, estimated = Schätzung, none = kein Wert"
        )
    )
    unit_value: Decimal | None
    total_value: Decimal | None
    source: str | None
    basis: str | None
    change: Decimal | None = Field(description="Veränderung seit dem Hinzufügen (gesamt).")

    @classmethod
    def build(cls, value: ItemValue) -> ValueOut:
        return cls(**value.__dict__)


class ItemOut(BaseModel):
    id: uuid.UUID
    folder_id: uuid.UUID
    kind: Literal["raw", "graded", "sealed"]
    card: CardOut | None
    product: ProductOut | None
    variant: str
    condition: str | None
    quantity: int
    purchase_price: Decimal | None
    purchase_date: date | None
    custom_price: Decimal | None
    note: str | None
    grading_company: GradingCompany | None
    grade: str | None
    value_at_add: Decimal | None
    value: ValueOut
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, valued: ValuedItem) -> ItemOut:
        item = valued.item
        return cls(
            id=item.id,
            folder_id=item.folder_id,
            kind=valued.kind,
            card=CardOut.model_validate(item.card) if item.card else None,
            product=ProductOut.model_validate(item.product) if item.product else None,
            variant=item.variant,
            condition=item.condition,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            purchase_date=item.purchase_date,
            custom_price=item.custom_price,
            note=item.note,
            grading_company=item.grading_company,
            grade=item.grade,
            value_at_add=item.value_at_add,
            value=ValueOut.build(valued.value),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int


# ------------------------------------------------------------------ Kennzahlen


class KindTotalsOut(BaseModel):
    value: Decimal
    positions: int
    items: int

    @classmethod
    def build(cls, totals: KindTotals) -> KindTotalsOut:
        return cls(**totals.__dict__)


class SummaryOut(BaseModel):
    total_value: Decimal
    estimated_value: Decimal = Field(description="Anteil des Gesamtwerts, der geschätzt ist.")
    change_since_added: Decimal = Field(description="Preisentwicklung – Zukäufe zählen nicht mit.")
    positions: int
    items: int
    cards: int
    sets: int
    unvalued_positions: int
    raw: KindTotalsOut
    graded: KindTotalsOut
    sealed: KindTotalsOut
    top_item: ItemOut | None
    biggest_gain: ItemOut | None
    biggest_loss: ItemOut | None

    @classmethod
    def build(cls, summary: CollectionSummary) -> SummaryOut:
        def item(entry: ValuedItem | None) -> ItemOut | None:
            return ItemOut.build(entry) if entry else None

        return cls(
            total_value=summary.total_value,
            estimated_value=summary.estimated_value,
            change_since_added=summary.change_since_added,
            positions=summary.positions,
            items=summary.items,
            cards=summary.cards,
            sets=summary.sets,
            unvalued_positions=summary.unvalued_positions,
            raw=KindTotalsOut.build(summary.by_kind["raw"]),
            graded=KindTotalsOut.build(summary.by_kind["graded"]),
            sealed=KindTotalsOut.build(summary.by_kind["sealed"]),
            top_item=item(summary.top_item),
            biggest_gain=item(summary.biggest_gain),
            biggest_loss=item(summary.biggest_loss),
        )


class SetOverviewOut(BaseModel):
    card_set: SetOut
    positions: int
    value: Decimal
    owned_cards: int

    @classmethod
    def build(cls, overview: SetOverview) -> SetOverviewOut:
        return cls(
            card_set=SetOut.model_validate(overview.card_set),
            positions=overview.positions,
            value=overview.value,
            owned_cards=overview.owned_cards,
        )


class HistoryPointOut(BaseModel):
    date: date
    total_value: Decimal
    estimated_value: Decimal
    is_live: bool

    @classmethod
    def build(cls, entry: HistoryEntry) -> HistoryPointOut:
        return cls(
            date=entry.day,
            total_value=entry.total_value,
            estimated_value=entry.estimated_value,
            is_live=entry.is_live,
        )


class MarkerOut(BaseModel):
    date: date
    delta_quantity: int

    @classmethod
    def build(cls, marker: EventMarker) -> MarkerOut:
        return cls(date=marker.day, delta_quantity=marker.delta_quantity)


class CollectionHistoryOut(BaseModel):
    points: list[HistoryPointOut]
    markers: list[MarkerOut] = Field(description="Tage mit Bestandsänderung (Sprung ≠ Gewinn).")


# ------------------------------------------------------------------- Merkliste


class WishlistAdd(BaseModel):
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None


class WishlistEntryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    card: CardOut | None
    product: ProductOut | None
    nm_value: Decimal | None = Field(description="Near-Mint-Wert (normal), falls belegt.")
    nm_value_kind: Literal["external", "estimated"] | None


class SealedOfferOut(BaseModel):
    """Versiegeltes Produkt aus dem Cardmarket-Katalog mit Preis (Euro, Dezimal-String)."""

    cardmarket_product_id: int
    name: str
    category: str | None
    kind: ProductKind
    trend: Decimal | None
    low: Decimal | None
    value: Decimal | None = Field(description="Median aus Trend, Ø 7 und Ø 30 Tagen")
    url: str
    image_url: str | None = Field(default=None, description="Bild aus dem TCGplayer-Katalog")


class ProductFromCardmarket(BaseModel):
    cardmarket_product_id: int = Field(gt=0)
    language: CatalogLanguage


class MoverOut(BaseModel):
    """Eine Karte, deren Cardmarket-Trend sich im Zeitraum deutlich bewegt hat."""

    card: CardOut
    variant: str
    quantity: int
    before: Decimal = Field(description="Trend je Stück zu Beginn des Zeitraums")
    now: Decimal = Field(description="Trend je Stück jetzt")
    change: Decimal = Field(description="Veränderung des Gesamtwerts (alle Exemplare)")
    change_pct: Decimal
    since: datetime


class MoversOut(BaseModel):
    days: int
    gainers: list[MoverOut]
    losers: list[MoverOut]

    @classmethod
    def build(cls, movers: Movers) -> MoversOut:
        def out(mover: Mover) -> MoverOut:
            return MoverOut(
                card=CardOut.model_validate(mover.card),
                variant=mover.variant,
                quantity=mover.quantity,
                before=mover.before,
                now=mover.now,
                change=mover.change,
                change_pct=mover.change_pct,
                since=mover.since,
            )

        return cls(
            days=movers.days,
            gainers=[out(m) for m in movers.gainers],
            losers=[out(m) for m in movers.losers],
        )
