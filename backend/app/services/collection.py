"""Sammlung: Ordner, Positionen, Bewertung, Kennzahlen, Verlauf, Export, Merkliste.

**Mandantentrennung:** Jede Methode bekommt den Eigentümer (``owner``) und filtert *jede*
Abfrage nach ``user_id``. Fremde Objekte sind „nicht gefunden“ (404). Admins sehen fremde
Sammlungen ausschließlich lesend über dieselben Lese-Methoden (Audit im Router).
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Card,
    CardSet,
    CollectionEvent,
    CollectionEventType,
    CollectionItem,
    Folder,
    FolderSnapshot,
    GradingCompany,
    PortfolioSnapshot,
    Product,
    User,
    WishlistItem,
)
from app.providers.pricing import CONDITIONS
from app.services.errors import ConflictError, InvalidInputError, NotFoundError
from app.services.movers import Movers, price_movers
from app.services.pricing import CardPrices, PriceService
from app.services.sealed import sealed_prices
from app.services.valuation import CENT, ItemKind, ItemValue, item_kind, unit_value, value_item

DEFAULT_FOLDER_NAME = "Sammlung"
NOT_NULLABLE = ("folder_id", "variant", "condition", "quantity", "grade")
VARIANTS = ("normal", "reverse")
SortKey = Literal[
    "added_desc", "added_asc", "value_desc", "profit_desc", "profit_asc", "name", "set_number"
]
ZERO = Decimal("0.00")


# ------------------------------------------------------------------ Eingaben


@dataclass
class ItemInput:
    """Neue Position (Karte oder Produkt)."""

    folder_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant: str = "normal"
    condition: str | None = None
    quantity: int = 1
    purchase_price: Decimal | None = None
    purchase_date: date | None = None
    custom_price: Decimal | None = None
    note: str | None = None
    grading_company: GradingCompany | None = None
    grade: str | None = None


@dataclass
class ItemFilter:
    folder_id: uuid.UUID | None = None
    kind: ItemKind | None = None
    set_id: uuid.UUID | None = None
    language: str | None = None
    query: str | None = None
    condition: str | None = None
    """Nur Rohkarten in diesem Zustand (NM, EX, …)."""
    min_value: Decimal | None = None
    """Gesamtwert der Position mindestens … (Positionen ohne Wert fallen dann heraus)."""
    max_value: Decimal | None = None
    with_purchase: bool | None = None
    """``True`` nur mit Kaufpreis, ``False`` nur ohne."""

    def matches_value(self, value: ItemValue) -> bool:
        """Filter, die erst nach der Bewertung greifen (Wertspanne)."""
        if self.min_value is None and self.max_value is None:
            return True
        if value.total_value is None:
            return False
        if self.min_value is not None and value.total_value < self.min_value:
            return False
        return self.max_value is None or value.total_value <= self.max_value


# --------------------------------------------------------------- Ergebnisse


@dataclass(frozen=True)
class ValuedItem:
    item: CollectionItem
    value: ItemValue

    @property
    def kind(self) -> ItemKind:
        return item_kind(self.item)


@dataclass
class KindTotals:
    value: Decimal = ZERO
    positions: int = 0
    items: int = 0


@dataclass
class CollectionSummary:
    total_value: Decimal = ZERO
    estimated_value: Decimal = ZERO
    change_since_added: Decimal = ZERO
    positions: int = 0
    items: int = 0
    cards: int = 0
    sets: int = 0
    unvalued_positions: int = 0
    by_kind: dict[str, KindTotals] = field(
        default_factory=lambda: {
            "raw": KindTotals(),
            "graded": KindTotals(),
            "sealed": KindTotals(),
        }
    )
    top_item: ValuedItem | None = None
    biggest_gain: ValuedItem | None = None
    biggest_loss: ValuedItem | None = None
    invested: Decimal = ZERO
    """Summe aller Kaufpreise (Kaufpreis je Stück × Menge)."""
    profit_cost: Decimal = ZERO
    """Kaufpreise der Positionen, die auch einen Wert haben (Basis für Gewinn in %)."""
    profit: Decimal = ZERO
    """Wert minus Kaufpreis – nur Positionen mit Kaufpreis und Wert."""
    profit_positions: int = 0
    best_profit: ValuedItem | None = None
    worst_profit: ValuedItem | None = None


@dataclass(frozen=True)
class OwnedEntry:
    """Bestand einer Karte je Ordner und Fassung (Rohkarte bzw. Slab)."""

    card_id: uuid.UUID
    folder_id: uuid.UUID
    folder_name: str
    variant: str
    grading_company: str | None
    grade: str | None
    quantity: int


@dataclass(frozen=True)
class FolderSummary:
    folder: Folder
    summary: CollectionSummary


@dataclass(frozen=True)
class SetOverview:
    card_set: CardSet
    positions: int
    value: Decimal
    owned_cards: int
    """Verschiedene Kartennummern dieses Sets in der Sammlung."""


@dataclass(frozen=True)
class HistoryEntry:
    day: date
    total_value: Decimal
    estimated_value: Decimal
    is_live: bool = False


@dataclass(frozen=True)
class EventMarker:
    day: date
    delta_quantity: int


# ------------------------------------------------------------------- Service


class CollectionService:
    """Alle Operationen auf der Sammlung *eines* Nutzers. Commit macht der Aufrufer."""

    def __init__(
        self,
        session: AsyncSession,
        owner: User,
        prices: PriceService,
        *,
        clock: type[datetime] = datetime,
    ) -> None:
        self._session = session
        self._owner = owner
        self._prices = prices
        self._clock = clock

    def _now(self) -> datetime:
        return self._clock.now(UTC)

    # ------------------------------------------------------------- Ordner

    async def list_folders(self) -> list[Folder]:
        """Ordner des Nutzers; legt beim ersten Aufruf den Standardordner an."""
        folders = list(
            (
                await self._session.scalars(
                    select(Folder)
                    .where(Folder.user_id == self._owner.id)
                    .order_by(Folder.sort_order, Folder.created_at)
                )
            ).all()
        )
        if not folders:
            folder = Folder(user_id=self._owner.id, name=DEFAULT_FOLDER_NAME, sort_order=0)
            self._session.add(folder)
            await self._session.flush()
            folders = [folder]
        return folders

    async def _own_folder(self, folder_id: uuid.UUID) -> Folder:
        folder = await self._session.scalar(
            select(Folder).where(Folder.id == folder_id, Folder.user_id == self._owner.id)
        )
        if folder is None:
            raise NotFoundError("Ordner nicht gefunden.")
        return folder

    async def create_folder(self, name: str) -> Folder:
        folders = await self.list_folders()
        if any(f.name.casefold() == name.casefold() for f in folders):
            raise ConflictError("Es gibt bereits einen Ordner mit diesem Namen.")
        folder = Folder(user_id=self._owner.id, name=name, sort_order=len(folders))
        self._session.add(folder)
        await self._session.flush()
        return folder

    async def update_folder(
        self,
        folder_id: uuid.UUID,
        *,
        name: str | None = None,
        sort_order: int | None = None,
        shared: bool | None = None,
    ) -> Folder:
        folder = await self._own_folder(folder_id)
        if shared is not None:
            folder.shared = shared
        if name is not None and name != folder.name:
            clash = await self._session.scalar(
                select(Folder.id).where(
                    Folder.user_id == self._owner.id,
                    func.lower(Folder.name) == name.casefold(),
                    Folder.id != folder.id,
                )
            )
            if clash:
                raise ConflictError("Es gibt bereits einen Ordner mit diesem Namen.")
            folder.name = name
        if sort_order is not None:
            folder.sort_order = sort_order
        return folder

    async def delete_folder(self, folder_id: uuid.UUID, *, move_to: uuid.UUID | None) -> None:
        """Löscht einen Ordner. Enthält er Positionen, müssen sie in ``move_to`` umziehen."""
        folder = await self._own_folder(folder_id)
        if len(await self.list_folders()) <= 1:
            raise InvalidInputError("Der letzte Ordner kann nicht gelöscht werden.")
        has_items = await self._session.scalar(
            select(func.count()).where(CollectionItem.folder_id == folder.id)
        )
        if has_items:
            if move_to is None:
                raise InvalidInputError(
                    "Der Ordner enthält Karten – bitte Zielordner angeben.", code="folder_not_empty"
                )
            target = await self._own_folder(move_to)
            if target.id == folder.id:
                raise InvalidInputError("Zielordner muss ein anderer Ordner sein.")
            for item in (
                await self._session.scalars(
                    select(CollectionItem).where(CollectionItem.folder_id == folder.id)
                )
            ).all():
                item.folder_id = target.id
            await self._session.flush()
        await self._session.delete(folder)

    # ---------------------------------------------------------- Positionen

    async def _validate(self, data: ItemInput) -> tuple[Card | None, Product | None]:
        if (data.card_id is None) == (data.product_id is None):
            raise InvalidInputError("Genau eine Karte oder ein Produkt angeben.")
        if data.variant not in VARIANTS:
            raise InvalidInputError(f"Variante muss eine von {', '.join(VARIANTS)} sein.")
        if data.condition is not None and data.condition not in CONDITIONS:
            raise InvalidInputError("Unbekannter Zustand.")
        if data.quantity < 1:
            raise InvalidInputError("Menge muss mindestens 1 sein.")
        if data.product_id is not None and (data.grading_company or data.grade):
            raise InvalidInputError("Nur Karten können gegradet sein.")
        if bool(data.grading_company) != bool(data.grade):
            raise InvalidInputError("Für gegradete Karten Firma und Note angeben.")
        card = await self._session.get(Card, data.card_id) if data.card_id else None
        product = await self._session.get(Product, data.product_id) if data.product_id else None
        if data.card_id and card is None:
            raise NotFoundError("Karte nicht gefunden.")
        if data.product_id and product is None:
            raise NotFoundError("Produkt nicht gefunden.")
        return card, product

    async def _current_unit_value(self, item: CollectionItem) -> ItemValue:
        prices = (
            (await self._prices.prices_for_cards([item.card_id], self._owner)).get(item.card_id)
            if item.card_id
            else None
        )
        sealed = (
            (await sealed_prices(self._session, [item.product_id])).get(item.product_id)
            if item.product_id
            else None
        )
        return unit_value(item, prices, sealed)

    def _event(
        self,
        item: CollectionItem,
        event_type: CollectionEventType,
        delta: int,
        unit: Decimal | None,
    ) -> None:
        self._session.add(
            CollectionEvent(
                user_id=self._owner.id,
                item_id=item.id,
                event_type=event_type,
                delta_quantity=delta,
                unit_value=unit,
            )
        )

    async def add_item(self, data: ItemInput) -> CollectionItem:
        """Neue Position. Holt bei Karten vorher aktuelle Preise (für den Startwert)."""
        card, _product = await self._validate(data)
        folder = (
            await self._own_folder(data.folder_id)
            if data.folder_id
            else (await self.list_folders())[0]
        )
        if card is not None and data.grading_company is None:
            await self._prices.refresh(card)
        item = CollectionItem(
            id=uuid.uuid4(),
            user_id=self._owner.id,
            folder_id=folder.id,
            card_id=data.card_id,
            product_id=data.product_id,
            variant=data.variant,
            condition=(data.condition or "NM")
            if data.card_id and not data.grading_company
            else None,
            quantity=data.quantity,
            purchase_price=data.purchase_price,
            purchase_date=data.purchase_date,
            custom_price=data.custom_price,
            note=(data.note or "").strip() or None,
            grading_company=data.grading_company,
            grade=data.grade,
        )
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item, ["card", "product", "folder"])
        start = await self._current_unit_value(item)
        item.value_at_add = start.unit_value
        self._event(item, CollectionEventType.ADDED, item.quantity, start.unit_value)
        await self._session.flush()
        return item

    async def get_item(self, item_id: uuid.UUID) -> CollectionItem:
        item = await self._session.scalar(
            select(CollectionItem).where(
                CollectionItem.id == item_id, CollectionItem.user_id == self._owner.id
            )
        )
        if item is None:
            raise NotFoundError("Position nicht gefunden.")
        return item

    async def update_item(self, item_id: uuid.UUID, changes: dict[str, object]) -> CollectionItem:
        """Ändert eine Position. ``changes`` enthält nur die gesetzten Felder."""
        item = await self.get_item(item_id)
        _validate_changes(item, changes)
        if isinstance(folder_id := changes.get("folder_id"), uuid.UUID):  # geprüft oben
            item.folder_id = (await self._own_folder(folder_id)).id
        old_quantity = item.quantity
        kind_changed = _switch_kind(item, changes)
        for name in ("variant", "condition", "quantity", "purchase_price", "purchase_date",
                     "custom_price", "note", "grade"):  # fmt: skip
            if name in changes:
                setattr(item, name, changes[name])
        if item.note is not None:
            item.note = item.note.strip() or None
        if kind_changed:
            # Rohkarte ↔ Slab: neuer Ausgangswert, sonst wäre die „Veränderung“ sinnlos.
            await self._session.flush()
            item.value_at_add = (await self._current_unit_value(item)).unit_value
        if item.quantity != old_quantity:
            current = await self._current_unit_value(item)
            self._event(
                item,
                CollectionEventType.QUANTITY_CHANGED,
                item.quantity - old_quantity,
                current.unit_value,
            )
        await self._session.flush()
        return item

    async def delete_item(self, item_id: uuid.UUID) -> None:
        item = await self.get_item(item_id)
        current = await self._current_unit_value(item)
        self._event(item, CollectionEventType.REMOVED, -item.quantity, current.unit_value)
        await self._session.flush()
        await self._session.delete(item)

    async def _own_items(self, item_ids: Sequence[uuid.UUID]) -> list[CollectionItem]:
        """Eigene Positionen in der Reihenfolge der IDs – fremde/unbekannte → 404."""
        found = {
            item.id: item
            for item in (
                await self._session.scalars(
                    select(CollectionItem).where(
                        CollectionItem.id.in_(item_ids),
                        CollectionItem.user_id == self._owner.id,
                    )
                )
            )
            .unique()
            .all()
        }
        if len(found) != len(set(item_ids)):
            raise NotFoundError("Position nicht gefunden.")
        return [found[i] for i in dict.fromkeys(item_ids)]

    async def move_items(self, item_ids: Sequence[uuid.UUID], folder_id: uuid.UUID) -> int:
        """Verschiebt Positionen in einen Ordner (Wert und Verlauf bleiben)."""
        folder = await self._own_folder(folder_id)
        items = await self._own_items(item_ids)
        for item in items:
            item.folder_id = folder.id
        await self._session.flush()
        return len(items)

    async def copy_items(
        self, item_ids: Sequence[uuid.UUID], folder_id: uuid.UUID
    ) -> list[CollectionItem]:
        """Kopiert Positionen in einen Ordner – zählt wie neu hinzugefügt (Startwert = heute)."""
        folder = await self._own_folder(folder_id)
        copies = []
        for original in await self._own_items(item_ids):
            item = CollectionItem(
                id=uuid.uuid4(),
                user_id=self._owner.id,
                folder_id=folder.id,
                card_id=original.card_id,
                product_id=original.product_id,
                variant=original.variant,
                condition=original.condition,
                quantity=original.quantity,
                purchase_price=original.purchase_price,
                purchase_date=original.purchase_date,
                custom_price=original.custom_price,
                note=original.note,
                grading_company=original.grading_company,
                grade=original.grade,
            )
            self._session.add(item)
            await self._session.flush()
            await self._session.refresh(item, ["card", "product", "folder"])
            start = await self._current_unit_value(item)
            item.value_at_add = start.unit_value
            self._event(item, CollectionEventType.ADDED, item.quantity, start.unit_value)
            copies.append(item)
        await self._session.flush()
        return copies

    async def delete_items(self, item_ids: Sequence[uuid.UUID]) -> int:
        items = await self._own_items(item_ids)
        for item in items:
            await self.delete_item(item.id)
        return len(items)

    # ------------------------------------------------------------ Bewertung

    def _filtered(self, item_filter: ItemFilter) -> Select[CollectionItem]:
        statement = (
            select(CollectionItem)
            .outerjoin(Card, CollectionItem.card_id == Card.id)
            .outerjoin(Product, CollectionItem.product_id == Product.id)
            .where(CollectionItem.user_id == self._owner.id)
        )
        if item_filter.folder_id is not None:
            statement = statement.where(CollectionItem.folder_id == item_filter.folder_id)
        if item_filter.kind == "sealed":
            statement = statement.where(CollectionItem.product_id.is_not(None))
        elif item_filter.kind == "graded":
            statement = statement.where(CollectionItem.grading_company.is_not(None))
        elif item_filter.kind == "raw":
            statement = statement.where(
                CollectionItem.card_id.is_not(None), CollectionItem.grading_company.is_(None)
            )
        if item_filter.set_id is not None:
            statement = statement.where(
                or_(Card.set_id == item_filter.set_id, Product.set_id == item_filter.set_id)
            )
        if item_filter.language is not None:
            statement = statement.where(
                or_(Card.language == item_filter.language, Product.language == item_filter.language)
            )
        if item_filter.condition is not None:
            statement = statement.where(
                CollectionItem.condition == item_filter.condition,
                CollectionItem.grading_company.is_(None),
                CollectionItem.card_id.is_not(None),
            )
        if item_filter.with_purchase is not None:
            statement = statement.where(
                CollectionItem.purchase_price.is_not(None)
                if item_filter.with_purchase
                else CollectionItem.purchase_price.is_(None)
            )
        if item_filter.query:
            pattern = f"%{item_filter.query.strip().casefold()}%"
            statement = statement.where(
                or_(
                    func.lower(Card.name).like(pattern),
                    func.lower(Product.name).like(pattern),
                    func.lower(CollectionItem.note).like(pattern),
                )
            )
        return statement

    async def valued_items(self, item_filter: ItemFilter | None = None) -> list[ValuedItem]:
        item_filter = item_filter or ItemFilter()
        items = list((await self._session.scalars(self._filtered(item_filter))).unique().all())
        prices = await self._prices.prices_for_cards(
            [i.card_id for i in items if i.card_id is not None], self._owner
        )
        sealed = await sealed_prices(
            self._session, [i.product_id for i in items if i.product_id is not None]
        )
        valued = [ValuedItem(item=i, value=value_item(i, prices, sealed)) for i in items]
        return [v for v in valued if item_filter.matches_value(v.value)]

    async def valued_item(self, item_id: uuid.UUID) -> ValuedItem:
        """Eine eigene Position samt Bewertung."""
        item = await self.get_item(item_id)
        prices = await self._prices.prices_for_cards(
            [item.card_id] if item.card_id else [], self._owner
        )
        sealed = await sealed_prices(self._session, [item.product_id] if item.product_id else [])
        return ValuedItem(item=item, value=value_item(item, prices, sealed))

    async def list_items(
        self,
        item_filter: ItemFilter,
        *,
        sort: SortKey = "added_desc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ValuedItem], int]:
        """Positionen mit Bewertung; Sortierung auch nach Wert. Gibt (Seite, Gesamtzahl) zurück."""
        valued = await self.valued_items(item_filter)

        def name_of(v: ValuedItem) -> str:
            return (
                v.item.card.name if v.item.card else v.item.product.name if v.item.product else ""
            ).casefold()

        sorters = {
            "added_desc": (lambda v: v.item.created_at, True),
            "added_asc": (lambda v: v.item.created_at, False),
            "value_desc": (lambda v: v.value.total_value or Decimal(-1), True),
            # Ohne Kaufpreis ans Ende – in beiden Richtungen.
            "profit_desc": (lambda v: (v.value.profit is not None, v.value.profit or ZERO), True),
            "profit_asc": (
                lambda v: (v.value.profit is None, v.value.profit or ZERO),
                False,
            ),
            "name": (name_of, False),
            "set_number": (
                lambda v: (
                    v.item.card.card_set.name if v.item.card else "",
                    v.item.card.number_norm.zfill(6) if v.item.card else "",
                ),
                False,
            ),
        }
        key, reverse = sorters[sort]
        valued.sort(key=key, reverse=reverse)
        return valued[offset : offset + limit], len(valued)

    async def owned_cards(self, card_ids: Sequence[uuid.UUID]) -> list[OwnedEntry]:
        """Wie oft und in welchem Ordner liegen diese Karten (für Suche und Kartenseite)?"""
        if not card_ids:
            return []
        rows = await self._session.execute(
            select(
                CollectionItem.card_id,
                Folder.id,
                Folder.name,
                CollectionItem.variant,
                CollectionItem.grading_company,
                CollectionItem.grade,
                func.sum(CollectionItem.quantity),
            )
            .join(Folder, Folder.id == CollectionItem.folder_id)
            .where(
                CollectionItem.user_id == self._owner.id,
                CollectionItem.card_id.in_(list(dict.fromkeys(card_ids))),
            )
            .group_by(
                CollectionItem.card_id,
                Folder.id,
                Folder.name,
                Folder.sort_order,
                CollectionItem.variant,
                CollectionItem.grading_company,
                CollectionItem.grade,
            )
            .order_by(CollectionItem.card_id, Folder.sort_order, Folder.name)
        )
        return [
            OwnedEntry(
                card_id=card_id,
                folder_id=folder_id,
                folder_name=folder_name,
                variant=variant,
                grading_company=company.value if company else None,
                grade=grade,
                quantity=int(quantity),
            )
            for card_id, folder_id, folder_name, variant, company, grade, quantity in rows
            if card_id is not None  # durch den Filter garantiert; für den Typprüfer
        ]

    async def price_movers(self, *, days: int = 7, limit: int = 5) -> Movers:
        """Gewinner und Verlierer der eigenen Rohkarten (Cardmarket-Trend) im Zeitraum."""
        return await price_movers(
            self._session, self._owner.id, now=self._now(), days=days, limit=limit
        )

    async def summary(self, folder_id: uuid.UUID | None = None) -> CollectionSummary:
        """Kennzahlen für Übersicht und Dashboard (optional nur eines Ordners)."""
        if folder_id is not None:
            await self._own_folder(folder_id)
        return summarize(await self.valued_items(ItemFilter(folder_id=folder_id)))

    async def folder_summaries(self) -> list[FolderSummary]:
        """Jeder Ordner als eigenes Portfolio: Wert, Kaufpreise, Gewinn."""
        folders = await self.list_folders()
        grouped: dict[uuid.UUID, list[ValuedItem]] = {f.id: [] for f in folders}
        for entry in await self.valued_items():
            grouped.setdefault(entry.item.folder_id, []).append(entry)
        return [FolderSummary(folder=f, summary=summarize(grouped[f.id])) for f in folders]

    async def sets_overview(self) -> list[SetOverview]:
        """Gruppierung nach Set mit Fortschritt („1 von 216 Karten“)."""
        grouped: dict[uuid.UUID, list[ValuedItem]] = {}
        for entry in await self.valued_items(ItemFilter()):
            if entry.item.card is not None:
                grouped.setdefault(entry.item.card.set_id, []).append(entry)
        overview = [
            SetOverview(
                card_set=entries[0].item.card.card_set,  # type: ignore[union-attr]
                positions=len(entries),
                value=sum((e.value.total_value or ZERO for e in entries), ZERO),
                owned_cards=len({e.item.card.number_norm for e in entries if e.item.card}),
            )
            for entries in grouped.values()
        ]
        overview.sort(key=lambda o: (-o.value, o.card_set.name))
        return overview

    # ------------------------------------------------------------- Verlauf

    async def take_snapshot(self, day: date | None = None) -> PortfolioSnapshot:
        """Speichert den Tageswert – gesamt und je Ordner (überschreibt denselben Tag)."""
        day = day or self._now().date()
        valued = await self.valued_items()
        summary = summarize(valued)
        await self._snapshot_folders(valued, day)
        values = {
            "user_id": self._owner.id,
            "day": day,
            "total_value": summary.total_value,
            "raw_value": summary.by_kind["raw"].value,
            "graded_value": summary.by_kind["graded"].value,
            "sealed_value": summary.by_kind["sealed"].value,
            "estimated_value": summary.estimated_value,
            "item_count": summary.items,
            "position_count": summary.positions,
        }
        statement = insert(PortfolioSnapshot).values(values)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[PortfolioSnapshot.user_id, PortfolioSnapshot.day],
                set_={k: v for k, v in values.items() if k not in ("user_id", "day")},
            )
        )
        snapshot = await self._session.get(PortfolioSnapshot, (self._owner.id, values["day"]))
        assert snapshot is not None  # noqa: S101 – gerade geschrieben
        await self._session.refresh(snapshot)
        return snapshot

    async def _snapshot_folders(self, valued: Sequence[ValuedItem], day: date) -> None:
        grouped: dict[uuid.UUID, list[ValuedItem]] = {f.id: [] for f in await self.list_folders()}
        for entry in valued:
            grouped.setdefault(entry.item.folder_id, []).append(entry)
        for folder_id, entries in grouped.items():
            summary = summarize(entries)
            values = {
                "folder_id": folder_id,
                "day": day,
                "total_value": summary.total_value,
                "estimated_value": summary.estimated_value,
                "invested": summary.invested,
                "item_count": summary.items,
            }
            await self._session.execute(
                insert(FolderSnapshot)
                .values(values)
                .on_conflict_do_update(
                    index_elements=[FolderSnapshot.folder_id, FolderSnapshot.day],
                    set_={k: v for k, v in values.items() if k not in ("folder_id", "day")},
                )
            )

    async def history(
        self, days: int = 90, folder_id: uuid.UUID | None = None
    ) -> tuple[list[HistoryEntry], list[EventMarker]]:
        """Tageswerte plus heutiger Live-Wert und Bestandsänderungen als Markierungen.

        Mit ``folder_id`` die Kurve eines Ordners – ohne Markierungen, weil verschobene
        Positionen ihre Ereignisse nicht eindeutig einem Ordner zuordnen.
        """
        today = self._now().date()
        since = today - timedelta(days=days)
        if folder_id is not None:
            await self._own_folder(folder_id)
            folder_rows = (
                await self._session.scalars(
                    select(FolderSnapshot)
                    .where(FolderSnapshot.folder_id == folder_id, FolderSnapshot.day >= since)
                    .order_by(FolderSnapshot.day)
                )
            ).all()
            live = await self.summary(folder_id)
            return [
                *(
                    HistoryEntry(r.day, r.total_value, r.estimated_value)
                    for r in folder_rows
                    if r.day != today
                ),
                HistoryEntry(today, live.total_value, live.estimated_value, is_live=True),
            ], []
        snapshots = (
            await self._session.scalars(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.user_id == self._owner.id, PortfolioSnapshot.day >= since)
                .order_by(PortfolioSnapshot.day)
            )
        ).all()
        entries = [
            HistoryEntry(s.day, s.total_value, s.estimated_value)
            for s in snapshots
            if s.day != today
        ]
        live = await self.summary()
        entries.append(HistoryEntry(today, live.total_value, live.estimated_value, is_live=True))

        day_col = func.date(func.timezone("UTC", CollectionEvent.created_at))
        rows = await self._session.execute(
            select(day_col, func.sum(CollectionEvent.delta_quantity))
            .where(
                CollectionEvent.user_id == self._owner.id,
                CollectionEvent.created_at >= datetime.combine(since, datetime.min.time(), UTC),
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        markers = [EventMarker(day=row[0], delta_quantity=int(row[1])) for row in rows]
        return entries, markers

    # -------------------------------------------------------------- Export

    async def export_csv(self) -> str:
        """Alle Positionen als CSV (Semikolon, Dezimalkomma – passt zu deutschem Excel)."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(
            [
                "Ordner", "Art", "Name", "Set", "Nummer", "Sprache", "Variante", "Zustand",
                "Grading", "Note", "Menge", "Kaufpreis (Stück)", "Kaufdatum", "Wert (Stück)",
                "Wert (gesamt)", "Gewinn (gesamt)", "Wertart", "Notiz", "Hinzugefügt",
            ]
        )  # fmt: skip
        for entry in await self.valued_items():
            writer.writerow([_safe_cell(cell) for cell in _export_row(entry)])
        return buffer.getvalue()

    # ----------------------------------------------------------- Merkliste

    async def wishlist(self) -> tuple[list[WishlistItem], dict[uuid.UUID, CardPrices]]:
        entries = list(
            (
                await self._session.scalars(
                    select(WishlistItem)
                    .where(WishlistItem.user_id == self._owner.id)
                    .order_by(WishlistItem.created_at.desc())
                )
            )
            .unique()
            .all()
        )
        prices = await self._prices.prices_for_cards(
            [e.card_id for e in entries if e.card_id is not None], self._owner
        )
        return entries, prices

    async def add_to_wishlist(
        self, *, card_id: uuid.UUID | None, product_id: uuid.UUID | None
    ) -> WishlistItem:
        if (card_id is None) == (product_id is None):
            raise InvalidInputError("Genau eine Karte oder ein Produkt angeben.")
        if card_id and await self._session.get(Card, card_id) is None:
            raise NotFoundError("Karte nicht gefunden.")
        if product_id and await self._session.get(Product, product_id) is None:
            raise NotFoundError("Produkt nicht gefunden.")
        existing = await self._session.scalar(
            select(WishlistItem).where(
                WishlistItem.user_id == self._owner.id,
                WishlistItem.card_id == card_id
                if card_id
                else WishlistItem.product_id == product_id,
            )
        )
        if existing is not None:
            return existing  # bereits gemerkt – kein Fehler
        entry = WishlistItem(user_id=self._owner.id, card_id=card_id, product_id=product_id)
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry, ["card", "product"])
        return entry

    async def remove_from_wishlist(self, entry_id: uuid.UUID) -> None:
        result = await self._session.execute(
            delete(WishlistItem)
            .where(WishlistItem.id == entry_id, WishlistItem.user_id == self._owner.id)
            .returning(WishlistItem.id)
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Eintrag nicht gefunden.")


KIND_LABELS: dict[str, str] = {"raw": "Karte", "graded": "Gegradet", "sealed": "Versiegelt"}
VALUE_KIND_LABELS: dict[str, str] = {
    "manual": "Eigener Preis",
    "external": "Belegt",
    "estimated": "Schätzung",
    "none": "Kein Wert",
}


def _export_row(entry: ValuedItem) -> list[object]:
    item, value = entry.item, entry.value
    card, product = item.card, item.product
    if card is not None:
        name, set_name, number, language = card.name, card.card_set.name, card.number, card.language
    elif product is not None:
        name, number, language = product.name, "", product.language
        set_name = product.card_set.name if product.card_set else ""
    else:  # durch Check-Constraint ausgeschlossen
        name = set_name = number = language = ""
    return [
        item.folder.name,
        KIND_LABELS[entry.kind],
        name,
        set_name,
        number,
        language,
        item.variant if card else "",
        item.condition or "",
        item.grading_company.value if item.grading_company else "",
        item.grade or "",
        item.quantity,
        _decimal_de(item.purchase_price),
        item.purchase_date.isoformat() if item.purchase_date else "",
        _decimal_de(value.unit_value),
        _decimal_de(value.total_value),
        _decimal_de(value.profit),
        VALUE_KIND_LABELS[value.kind],
        item.note or "",
        item.created_at.date().isoformat(),
    ]


def _switch_kind(item: CollectionItem, changes: dict[str, object]) -> bool:
    """Rohkarte ↔ Slab umstellen (``grading_company`` gesetzt bzw. ``null``).

    Slab: Firma setzen, Zustand entfällt. Rohkarte: Firma und Note entfallen, Zustand NM
    (sofern nicht gleichzeitig ein anderer angegeben ist). Gibt zurück, ob sich die Art geändert
    hat.
    """
    if "grading_company" not in changes:
        return False
    company = changes["grading_company"]
    was_graded = item.grading_company is not None
    if company is None:
        item.grading_company = None
        item.grade = None
        item.condition = item.condition or "NM"
    else:
        item.grading_company = GradingCompany(str(company))
        item.condition = None
    return was_graded != (company is not None)


def _target_kind(item: CollectionItem, changes: dict[str, object]) -> str:
    """Art der Position nach der Änderung (Rohkarte ↔ Slab über ``grading_company``)."""
    if "grading_company" not in changes:
        return item_kind(item)
    if item.card_id is None:
        raise InvalidInputError("Nur Karten können gegradet sein.")
    company = changes["grading_company"]
    if company is None:
        return "raw"
    if company not in set(GradingCompany):
        raise InvalidInputError("Unbekannte Grading-Firma.")
    return "graded"


def _validate_changes(item: CollectionItem, changes: dict[str, object]) -> None:
    """Fachliche Prüfung einer Änderung, bevor irgendetwas gesetzt wird."""
    for name in NOT_NULLABLE:
        if name in changes and changes[name] is None:
            raise InvalidInputError(f"Feld „{name}“ darf nicht leer sein.")
    if "folder_id" in changes and not isinstance(changes["folder_id"], uuid.UUID):
        raise InvalidInputError("Ordner angeben.")
    if "variant" in changes and changes["variant"] not in VARIANTS:
        raise InvalidInputError(f"Variante muss eine von {', '.join(VARIANTS)} sein.")
    kind = _target_kind(item, changes)
    if kind == "graded" and item.grade is None and not changes.get("grade"):
        raise InvalidInputError("Für einen Slab bitte die Note angeben.")
    if "condition" in changes:
        if kind != "raw":
            raise InvalidInputError("Zustand gibt es nur bei Rohkarten.")
        if changes["condition"] not in CONDITIONS:
            raise InvalidInputError("Unbekannter Zustand.")
    if "grade" in changes and kind != "graded":
        raise InvalidInputError("Eine Note gibt es nur bei gegradeten Karten.")
    quantity = changes.get("quantity", item.quantity)
    if not isinstance(quantity, int) or quantity < 1:
        raise InvalidInputError("Menge muss mindestens 1 sein.")


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: object) -> object:
    """Schutz vor CSV-Injection: Text, der mit einem Formelzeichen beginnt, wird von Excel
    sonst als Formel ausgeführt (Namen eigener Karten/Produkte stammen von anderen Nutzern)."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _decimal_de(value: Decimal | None) -> str:
    return "" if value is None else f"{value.quantize(CENT)}".replace(".", ",")


async def users_with_items(session: AsyncSession) -> Sequence[User]:
    """Nutzer mit mindestens einer Position (für die täglichen Tageswerte)."""
    result = await session.scalars(
        select(User).where(
            User.is_active,
            select(CollectionItem.id).where(CollectionItem.user_id == User.id).exists(),
        )
    )
    return result.all()


def _better(entry: ValuedItem, current: ValuedItem | None, metric: str, sign: int) -> bool:
    """Ist ``entry`` beim Kennwert ``metric`` (change/profit) größer (sign=1) bzw. kleiner?"""
    value = getattr(entry.value, metric)
    if value is None or value * sign <= 0:
        return False
    return current is None or value * sign > (getattr(current.value, metric) or ZERO) * sign


def summarize(valued: Sequence[ValuedItem]) -> CollectionSummary:
    """Kennzahlen aus bewerteten Positionen (ganze Sammlung oder ein Ordner)."""
    summary = CollectionSummary()
    set_ids: set[uuid.UUID] = set()
    for entry in valued:
        item, value = entry.item, entry.value
        totals = summary.by_kind[entry.kind]
        totals.positions += 1
        totals.items += item.quantity
        summary.positions += 1
        summary.items += item.quantity
        if item.card is not None:
            summary.cards += item.quantity
            set_ids.add(item.card.set_id)
        if value.cost is not None:
            summary.invested += value.cost
        if value.total_value is None:
            summary.unvalued_positions += 1
            continue
        totals.value += value.total_value
        summary.total_value += value.total_value
        if value.kind == "estimated":
            summary.estimated_value += value.total_value
        if value.change is not None:
            summary.change_since_added += value.change
        if value.profit is not None and value.cost is not None:
            summary.profit += value.profit
            summary.profit_cost += value.cost
            summary.profit_positions += 1
        if summary.top_item is None or (value.unit_value or ZERO) > (
            summary.top_item.value.unit_value or ZERO
        ):
            summary.top_item = entry
        if _better(entry, summary.biggest_gain, "change", 1):
            summary.biggest_gain = entry
        if _better(entry, summary.biggest_loss, "change", -1):
            summary.biggest_loss = entry
        if _better(entry, summary.best_profit, "profit", 1):
            summary.best_profit = entry
        if _better(entry, summary.worst_profit, "profit", -1):
            summary.worst_profit = entry
    summary.sets = len(set_ids)
    return summary
