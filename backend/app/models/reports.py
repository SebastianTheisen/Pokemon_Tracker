"""Meldungen „Das fehlt“: Nutzer melden fehlende Karten/Produkte oder falsche Daten an Admins."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.models.user import User


class ReportKind(enum.StrEnum):
    CARD = "card"  # Karte fehlt
    SEALED = "sealed"  # versiegeltes Produkt fehlt
    WRONG = "wrong"  # Daten falsch (Bild, Preis, Name …)
    OTHER = "other"


class MissingReport(UuidPrimaryKeyMixin, Base):
    __tablename__ = "missing_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[ReportKind] = mapped_column(
        Enum(
            ReportKind, native_enum=False, length=12, values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[str | None] = mapped_column(String(200))
    """Woher die Meldung kam, z. B. die Suchanfrage oder die Karten-ID."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")
