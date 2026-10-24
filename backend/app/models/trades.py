"""Gespeicherte Tausche (Tausch-Rechner).

Ein Tausch ist eine **Momentaufnahme**: welche Karten auf welcher Seite lagen und was sie
damals wert waren. Die Sammlung wird dabei nicht verändert – das macht man danach selbst
(z. B. per Mehrfachauswahl). Später lässt sich vergleichen: damals vs. heute.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UuidPrimaryKeyMixin


class Trade(UuidPrimaryKeyMixin, Base):
    __tablename__ = "trades"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    partner: Mapped[str | None] = mapped_column(String(80))
    """Mit wem (freier Text, z. B. Name eines Freundes)."""
    note: Mapped[str | None] = mapped_column(String(500))
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    """Zeilen: side (give/get), card_id/product_id, Fassung, Zustand, Slab, Menge, Stückwert."""
    give_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    get_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
