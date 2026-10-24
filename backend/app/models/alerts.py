"""Preisalarme und Push-Abos (Web-Push der PWA).

* :class:`PushSubscription` – ein Gerät (Browser/Home-Bildschirm-App) eines Nutzers, das
  Benachrichtigungen erlaubt hat. Endpunkt und Schlüssel stammen vom Browser.
* :class:`PriceAlert` – Zielpreis für eine Karte (Variante + Zustand) oder ein versiegeltes
  Produkt. Er löst **einmal** aus und ist danach inaktiv, bis der Nutzer ihn wieder scharf
  stellt – so kommt bei einem Preis knapp am Ziel nicht täglich dieselbe Nachricht.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.catalog import Card
    from app.models.collection import Product


class AlertDirection(enum.StrEnum):
    ABOVE = "above"  # Preis steigt auf/über das Ziel
    BELOW = "below"  # Preis fällt auf/unter das Ziel


class PushSubscription(UuidPrimaryKeyMixin, Base):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriceAlert(UuidPrimaryKeyMixin, Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        CheckConstraint("(card_id IS NULL) <> (product_id IS NULL)", name="card_xor_product"),
        CheckConstraint("target > 0", name="target_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    variant: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    condition: Mapped[str] = mapped_column(String(4), nullable=False, default="NM")
    direction: Mapped[AlertDirection] = mapped_column(
        Enum(
            AlertDirection,
            native_enum=False,
            length=8,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    target: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    card: Mapped[Card | None] = relationship(lazy="joined")
    product: Mapped[Product | None] = relationship(lazy="joined")
