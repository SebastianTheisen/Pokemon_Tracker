"""Persönliche Einstellungen je Nutzer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserSettings(TimestampMixin, Base):
    """Einstellungen; fehlende Werte bedeuten „Standard verwenden“."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Zustand → Faktor relativ zu Near Mint, z. B. {"EX": 0.85}. Nur Abweichungen vom Standard.
    condition_factors: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Kartensprache → Faktor auf den Cardmarket-Preis, z. B. {"de": 0.85}. Cardmarket führt
    # eine westliche Karte als *ein* Produkt für alle Sprachen; der Faktor bildet ab, dass
    # z. B. deutsche Karten günstiger gehandelt werden. Nur Abweichungen von 1,00.
    language_factors: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    default_language: Mapped[str | None] = mapped_column(String(8))
    weekly_summary: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    """Sonntags eine Mitteilung „Deine Woche“ (nur mit eingeschalteten Mitteilungen)."""
    # Karte, für die der Nutzer zuletzt „Preis holen“ geöffnet hat: Das Lesezeichen kennt
    # die Karte nicht mehr, wenn man auf Cardmarket/eBay weiterklickt (Sprungmarke weg).
    price_target_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL")
    )
    price_target_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
