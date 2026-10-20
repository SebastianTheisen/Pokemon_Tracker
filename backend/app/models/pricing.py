"""Preise: Historie aller abgerufenen Preiswerte und Abruf-Status je Karte und Quelle.

Jeder Abruf erzeugt neue Zeilen (nie überschreiben) – daraus entstehen Preisverlauf sowie
Tiefst- und Höchstpreis. Doppelte Werte (gleicher Stand der Quelle) werden verworfen.
Geschätzte Zustandspreise werden *nicht* gespeichert, sondern bei der Anzeige berechnet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UuidPrimaryKeyMixin


class PricePoint(UuidPrimaryKeyMixin, Base):
    """Ein Preiswert einer Quelle, z. B. Cardmarket-Trend für die Normal-Variante."""

    __tablename__ = "price_points"
    __table_args__ = (
        UniqueConstraint(
            "card_id",
            "source",
            "variant",
            "metric",
            "condition",
            "source_updated_at",
            name="uq_price_points_identity",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_price_points_card_history", "card_id", "source", "variant", "metric"),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(8))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PriceCheck(Base):
    """Letzter Abrufversuch je Karte und Quelle (Frische, Fehler, „angesehen“)."""

    __tablename__ = "price_checks"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ok: Mapped[bool] = mapped_column(nullable=False)
    message: Mapped[str | None] = mapped_column(String(300))
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CardPriceLink(Base):
    """Von Nutzern korrigierte Cardmarket-Seite einer Karte.

    TCGdex ordnet manchen Karten das falsche Cardmarket-Produkt zu (z. B. japanische
    „30th CELEBRATION“-Karten der vereinfacht-chinesischen Ausgabe). Liest ein Nutzer die
    Angebote einer Produktseite per Lesezeichen aus, gilt diese Seite künftig für die Karte –
    für alle Nutzer. Die Cardmarket-Werte von TCGdex werden dann nicht mehr verwendet.
    """

    __tablename__ = "card_price_links"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    cardmarket_url: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
