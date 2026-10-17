"""Scanner: Protokoll aller Scans und eigene Referenzbilder je Nutzer.

Fotos werden nicht gespeichert. ``scan_log`` enthält nur die erkannten Merkmale (Nummer,
Namenskandidaten, Sprache), das Ergebnis und ob der Nutzer es bestätigt hat – Grundlage
für Rate-Limit, Qualitätsmessung und das Speichern von Referenzbildern. Alte Einträge
löscht der Worker (``PT_SCAN_LOG_RETENTION_DAYS``).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UuidPrimaryKeyMixin
from app.models.catalog import Card


class ScanMode(enum.StrEnum):
    """Wie wurde gescannt?"""

    SINGLE = "single"
    BATCH = "batch"
    BINDER = "binder"


class ScanLog(UuidPrimaryKeyMixin, Base):
    """Ein gescanntes Bild (bei Binderseiten: eine Zelle)."""

    __tablename__ = "scan_log"
    __table_args__ = (Index("ix_scan_log_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    mode: Mapped[ScanMode] = mapped_column(
        Enum(
            ScanMode, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    best_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    confident: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detected: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    confirmed_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cards.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CardReferenceImage(UuidPrimaryKeyMixin, Base):
    """Eigenes Referenzbild eines Nutzers für eine Karte (wirkt nur bei seinen Scans).

    Bild und Merkmale liegen als Dateien auf dem Scanner-Volume
    (:class:`app.scanner.storage.ReferenceStore`), hier stehen nur die Metadaten.
    """

    __tablename__ = "card_reference_images"
    __table_args__ = (Index("ix_card_reference_images_user_card", "user_id", "card_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scan_log.id", ondelete="SET NULL")
    )
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="crop", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    card: Mapped[Card] = relationship(lazy="joined")
