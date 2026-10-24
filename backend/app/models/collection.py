"""Sammlung: Ordner, Positionen, Ereignisse, Tageswerte, Merkliste, versiegelte Produkte.

Jede Zeile mit ``user_id`` gehört genau einem Nutzer. Zugriffe laufen ausschließlich über
``app.services.collection``, das ``user_id`` immer mitfiltert (Mandantentrennung).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.catalog import Card, CardSet


def _enum(cls: type[enum.StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, length=24, values_callable=lambda e: [m.value for m in e])


class ProductKind(enum.StrEnum):
    """Arten versiegelter Produkte."""

    BOOSTER = "booster"
    BOOSTER_BUNDLE = "booster_bundle"
    ELITE_TRAINER_BOX = "elite_trainer_box"
    DISPLAY = "display"
    TIN = "tin"
    COLLECTION_BOX = "collection_box"
    BLISTER = "blister"
    CASE = "case"
    OTHER = "other"


class GradingCompany(enum.StrEnum):
    PSA = "PSA"
    BGS = "BGS"  # Beckett
    CGC = "CGC"
    SGC = "SGC"
    TAG = "TAG"
    ACE = "ACE"
    OTHER = "OTHER"


class CollectionEventType(enum.StrEnum):
    ADDED = "added"
    QUANTITY_CHANGED = "quantity_changed"
    REMOVED = "removed"


class Product(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Versiegeltes Produkt (Booster, Display, Box …). Von Nutzern angelegt, für alle sichtbar."""

    __tablename__ = "products"

    kind: Mapped[ProductKind] = mapped_column(_enum(ProductKind), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("card_sets.id", ondelete="SET NULL"), index=True
    )
    image_url: Mapped[str | None] = mapped_column(String(500))
    # Cardmarket-Produkt (``idProduct``) → Wert aus dem offiziellen Preisführer.
    cardmarket_product_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    card_set: Mapped[CardSet | None] = relationship(lazy="joined")


class Folder(UuidPrimaryKeyMixin, Base):
    """Ordner der Sammlung, z. B. „Sammlung“, „Sammlung 2“."""

    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shared: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    """Showcase: für alle angemeldeten Freunde sichtbar (ohne Kaufpreise und Notizen)."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CollectionItem(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Position: Karte *oder* Produkt, mit Menge, Zustand, Kauf- und Eigenpreis.

    Art der Position: versiegelt (``product_id``), gegradet (``grading_company``) oder Rohkarte.
    Preise sind Stückpreise in EUR.
    """

    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint("(card_id IS NULL) <> (product_id IS NULL)", name="card_xor_product"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint(
            "grading_company IS NULL OR card_id IS NOT NULL", name="grading_only_cards"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("folders.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cards.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    variant: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    condition: Mapped[str | None] = mapped_column(String(2))
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    custom_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(500))
    grading_company: Mapped[GradingCompany | None] = mapped_column(_enum(GradingCompany))
    grade: Mapped[str | None] = mapped_column(String(8))
    # Stückwert beim Hinzufügen – Grundlage für „Veränderung seit dem Hinzufügen“.
    value_at_add: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    card: Mapped[Card | None] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
    folder: Mapped[Folder] = relationship(lazy="joined")


class CollectionEvent(UuidPrimaryKeyMixin, Base):
    """Bestandsänderung (für die markierten Punkte in der Wertkurve)."""

    __tablename__ = "collection_events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_items.id", ondelete="SET NULL")
    )
    event_type: Mapped[CollectionEventType] = mapped_column(
        _enum(CollectionEventType), nullable=False
    )
    delta_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class PortfolioSnapshot(Base):
    """Tageswert der Sammlung eines Nutzers (Grundlage der Wertkurve)."""

    __tablename__ = "portfolio_snapshots"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    raw_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    graded_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sealed_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estimated_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)


class FolderSnapshot(Base):
    """Tageswert eines Ordners (Wertkurve je Ordner/Portfolio)."""

    __tablename__ = "folder_snapshots"

    folder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estimated_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    invested: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


class WishlistItem(UuidPrimaryKeyMixin, Base):
    """Eintrag der (einen) Merkliste eines Nutzers."""

    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_wishlist_items_user_card"),
        UniqueConstraint("user_id", "product_id", name="uq_wishlist_items_user_product"),
        CheckConstraint("(card_id IS NULL) <> (product_id IS NULL)", name="card_xor_product"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped[Card | None] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
