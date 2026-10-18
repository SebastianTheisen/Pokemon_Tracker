"""Bildquellen außerhalb von TCGdex: offizielle Kartendatenbanken und Prüfprotokoll.

* ``official_cards`` – jede Karte aus einer offiziellen Datenbank (Japan, Taiwan) mit
  Setcode, Nummer und Bildadresse. Die Detailseite wird nur einmal abgerufen; spätere Läufe
  laden nur neue Karten. Die Zuordnung zur Katalogkarte (``card_id``) wird bei jedem Lauf
  neu geprüft, damit auch später importierte Katalogkarten ihr Bild bekommen.
* ``image_probes`` – Ergebnis der Prüfung, ob es unter einer erratenen Adresse ein Bild gibt
  (pokemon.com). Fehlschläge werden erst nach einiger Zeit erneut geprüft.
* ``image_import_runs`` – Protokoll der Importläufe (für Status und Wochenrhythmus).

Bilder werden nicht kopiert: gespeichert wird nur die Adresse, die App lädt das Bild direkt
vom offiziellen Server.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UuidPrimaryKeyMixin


class OfficialCard(UuidPrimaryKeyMixin, Base):
    """Eine Karte aus einer offiziellen Kartendatenbank."""

    __tablename__ = "official_cards"
    __table_args__ = (
        UniqueConstraint("source", "official_id"),
        Index("ix_official_cards_card_id", "card_id"),
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    official_id: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    set_code: Mapped[str | None] = mapped_column(String(32))
    # Wie auf der Karte gedruckt, z. B. „001/103“ oder „132/M-P“; leer bis zur Detailseite.
    number: Mapped[str | None] = mapped_column(String(32))
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cards.id", ondelete="SET NULL"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImageProbe(Base):
    """Wurde für eine Karte unter der Adresse einer Quelle ein Bild gefunden?"""

    __tablename__ = "image_probes"

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImageImportRun(UuidPrimaryKeyMixin, Base):
    """Ein Lauf des Bild-Imports."""

    __tablename__ = "image_import_runs"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
