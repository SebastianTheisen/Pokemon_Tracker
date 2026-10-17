"""Persönliche Einstellungen je Nutzer."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
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
    default_language: Mapped[str | None] = mapped_column(String(8))
