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
    FolderSummary,
    HistoryEntry,
    KindTotals,
    SetOverview,
    ValuedItem,
)
from app.services.movers import Mover, Movers
from app.services.set_progress import SetCounts, SetProgress
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
    shared: bool = Field(default=False, description="Für Freunde sichtbar (Showcase)")
    created_at: datetime


class FolderCreate(BaseModel):
    name: FolderName


class FolderUpdate(BaseModel):
    name: FolderName | None = None
    sort_order: Annotated[int, Field(ge=0, le=1000)] | None = None
    shared: bool | None = None


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


class ItemsBulk(BaseModel):
    """Mehrfachauswahl: verschieben, kopieren oder entfernen."""

    item_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=200)]
    action: Literal["move", "copy", "delete"]
    folder_id: uuid.UUID | None = Field(
        default=None, description="Zielordner – nötig für move und copy."
    )


class ItemsBulkResult(BaseModel):
    count: int


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
    cost: Decimal | None = Field(default=None, description="Kaufpreis × Menge.")
    profit: Decimal | None = Field(
        default=None, description="Wert minus Kaufpreis (gesamt); nur mit Kaufpreis und Wert."
    )

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
    trend_7d_pct: Decimal | None = Field(
        default=None,
        description="Veränderung des Cardmarket-Trends in 7 Tagen (Rohkarte, normal); sonst null",
    )

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


def public_item(valued: ValuedItem) -> ItemOut:
    """Position für Freunde: ohne Kaufpreis/-datum, Eigenpreis, Notiz, Gewinn, Startwert."""
    out = ItemOut.build(valued)
    value = out.value.model_copy(update={"change": None, "cost": None, "profit": None})
    return out.model_copy(
        update={
            "purchase_price": None,
            "purchase_date": None,
            "custom_price": None,
            "note": None,
            "value_at_add": None,
            "value": value,
        }
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


def profit_percent(summary: CollectionSummary) -> Decimal | None:
    """Gewinn in % der Kaufpreise (nur Positionen mit Kaufpreis und Wert)."""
    if not summary.profit_cost:
        return None
    return (summary.profit / summary.profit_cost * 100).quantize(Decimal("0.1"))


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
    invested: Decimal = Field(description="Summe aller Kaufpreise.")
    profit: Decimal = Field(description="Wert minus Kaufpreis der Positionen mit beidem.")
    profit_cost: Decimal = Field(description="Kaufpreise dieser Positionen (Basis für %).")
    profit_percent: Decimal | None = Field(description="Gewinn in % (eine Nachkommastelle).")
    profit_positions: int
    best_profit: ItemOut | None
    worst_profit: ItemOut | None
    by_game: dict[str, Decimal] = Field(
        default_factory=dict, description="Wert je Spiel (nur ohne Spiel- und Ordnerfilter)."
    )

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
            invested=summary.invested,
            profit=summary.profit,
            profit_cost=summary.profit_cost,
            profit_percent=profit_percent(summary),
            profit_positions=summary.profit_positions,
            best_profit=item(summary.best_profit),
            worst_profit=item(summary.worst_profit),
            by_game=summary.by_game,
        )


class FolderSummaryOut(BaseModel):
    """Ein Ordner als Portfolio."""

    folder: FolderOut
    total_value: Decimal
    positions: int
    items: int
    invested: Decimal
    profit: Decimal
    profit_cost: Decimal
    profit_percent: Decimal | None
    profit_positions: int

    @classmethod
    def build(cls, entry: FolderSummary) -> FolderSummaryOut:
        summary = entry.summary
        return cls(
            folder=FolderOut.model_validate(entry.folder),
            total_value=summary.total_value,
            positions=summary.positions,
            items=summary.items,
            invested=summary.invested,
            profit=summary.profit,
            profit_cost=summary.profit_cost,
            profit_percent=profit_percent(summary),
            profit_positions=summary.profit_positions,
        )


class SetOverviewOut(BaseModel):
    card_set: SetOut
    positions: int
    value: Decimal
    owned_cards: int
    cards_total: int | None = Field(default=None, description="Karten des Sets im Katalog")
    master_total: int | None = Field(default=None, description="Plätze inkl. Reverse Holo")
    master_owned: int | None = None

    @classmethod
    def build(cls, overview: SetOverview, counts: SetCounts | None = None) -> SetOverviewOut:
        return cls(
            card_set=SetOut.model_validate(overview.card_set),
            positions=overview.positions,
            value=overview.value,
            owned_cards=overview.owned_cards,
            cards_total=counts.cards_total if counts else None,
            master_total=counts.master_total if counts else None,
            master_owned=counts.master_owned if counts else None,
        )


class CardProgressOut(BaseModel):
    card: CardOut
    owned_normal: int
    owned_reverse: int
    reverse: bool = Field(description="Gibt es die Karte als Reverse Holo?")
    on_wishlist: bool
    nm_value: Decimal | None
    reverse_value: Decimal | None


class SetProgressOut(BaseModel):
    card_set: SetOut
    cards_total: int
    cards_owned: int
    master_total: int
    master_owned: int
    missing_set_value: Decimal = Field(description="Fehlende Karten (eine Fassung), NM-Preise")
    missing_value: Decimal = Field(description="Fehlende Master-Plätze, NM-Preise")
    cards: list[CardProgressOut]

    @classmethod
    def build(cls, progress: SetProgress) -> SetProgressOut:
        return cls(
            card_set=SetOut.model_validate(progress.card_set),
            cards_total=progress.cards_total,
            cards_owned=progress.cards_owned,
            master_total=progress.master_total,
            master_owned=progress.master_owned,
            missing_set_value=progress.missing_set_value,
            missing_value=progress.missing_value,
            cards=[
                CardProgressOut(
                    card=CardOut.model_validate(c.card),
                    owned_normal=c.owned_normal,
                    owned_reverse=c.owned_reverse,
                    reverse=c.reverse,
                    on_wishlist=c.on_wishlist,
                    nm_value=c.nm_value,
                    reverse_value=c.reverse_value,
                )
                for c in progress.cards
            ],
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


class WishlistBulkAdd(BaseModel):
    card_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=500)]


class WishlistEntryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    card: CardOut | None
    product: ProductOut | None
    nm_value: Decimal | None = Field(
        description="Near-Mint-Wert (normal) bzw. Preis des versiegelten Produkts, falls belegt."
    )
    nm_value_kind: Literal["external", "estimated"] | None
    change: Decimal | None = Field(
        default=None, description="Veränderung des Stückpreises (Cardmarket-Trend) im Zeitraum"
    )
    change_pct: Decimal | None = None
    change_days: int = 7


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
    expansion_id: int | None = Field(default=None, description="Cardmarket-Ausgabe (Set)")
    set_name: str | None = Field(
        default=None, description="Name des Sets (deutsch, sonst englisch)"
    )


class SealedSetOut(BaseModel):
    """Set mit versiegelten Produkten (zum Durchblättern)."""

    expansion_id: int
    name: str
    release_date: date | None
    logo_url: str | None
    products: int
    image_url: str | None


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
