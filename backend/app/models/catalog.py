"""Katalog: Sets und Karten in allen Sprachen.

Eine Karte existiert je Sprache als eigene Zeile. Internationale Sets teilen sich die
TCGdex-ID über Sprachen hinweg (``swsh7-215`` ist auf Deutsch und Englisch dieselbe Karte);
darüber findet die Suche z. B. mit dem englischen Namen auch die deutsche Karte.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class CardSource(enum.StrEnum):
    """Herkunft eines Katalogeintrags."""

    TCGDEX = "tcgdex"
    USER = "user"
    OFFICIAL = "official"  # aus einer offiziellen Kartendatenbank (z. B. japanische Promos)
    POKEWIKI = "pokewiki"  # deutsche Setliste aus dem PokéWiki (Promos, Sondersets)
    PRICECHARTING = "pricecharting"  # Setliste von PriceCharting (Korea, China)


class ImageSource(enum.StrEnum):
    """Herkunft eines Kartenbilds, wenn es nicht von TCGdex selbst stammt (Spalte leer)."""

    FALLBACK = "fallback"  # Bild einer anderen Sprachfassung derselben Karte
    POKEMONTCG = "pokemontcg"  # Datensatz von pokemontcg.io (englische Bilder)
    POKEMON_COM = "pokemon.com"  # offizielle Bilder DE/EN
    POKEMON_CARD_JP = "pokemon-card.com"  # offizielle japanische Kartendatenbank
    POKEMON_CARD_TW = "asia.pokemon-card.com/tw"  # offizielle Datenbank Taiwan


class CardSet(UuidPrimaryKeyMixin, Base):
    """Ein Set in einer Sprache."""

    __tablename__ = "card_sets"
    __table_args__ = (UniqueConstraint("external_id", "language"),)

    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    series_name: Mapped[str | None] = mapped_column(String(200))
    release_date: Mapped[date | None] = mapped_column(Date)
    card_count_official: Mapped[int | None] = mapped_column(Integer)
    card_count_total: Mapped[int | None] = mapped_column(Integer)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    symbol_url: Mapped[str | None] = mapped_column(String(500))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Cardmarket-Ausgabe des Sets (``idExpansion``) und woher sie stammt
    # (:class:`app.models.cardmarket.ExpansionLinkSource`).
    cardmarket_expansion_id: Mapped[int | None] = mapped_column(Integer)
    cardmarket_expansion_source: Mapped[str | None] = mapped_column(String(16))
    cardmarket_expansion_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Letzte Nachfrage bei TCGdex nach der Ausgabe (Sets ohne Cardmarket-ID nicht täglich).
    cardmarket_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Card(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Karte in einer Sprache – aus TCGdex importiert oder von Nutzern angelegt."""

    __tablename__ = "cards"
    __table_args__ = (
        # Eindeutig nur für importierte Karten; selbst angelegte haben keine externe ID.
        Index(
            "uq_cards_external_id_language",
            "external_id",
            "language",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "ix_cards_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index("ix_cards_number_norm", "number_norm"),
    )

    external_id: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("card_sets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    number_norm: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    # Sprache des Bildes, wenn es von einer anderen Sprachfassung derselben Karte stammt
    # (z. B. englisches Bild für eine deutsche Karte, deren Bild bei TCGdex fehlt).
    image_language: Mapped[str | None] = mapped_column(String(8))
    # Herkunft des Bildes (:class:`ImageSource`); leer = von TCGdex.
    image_source: Mapped[str | None] = mapped_column(String(32))
    rarity: Mapped[str | None] = mapped_column(String(100))
    # Cardmarket-Produkt laut TCGdex (kann in der falschen Ausgabe liegen) und – falls ein
    # Nutzer innerhalb der Ausgabe ein anderes Produkt gewählt hat – dieses.
    cardmarket_product_id: Mapped[int | None] = mapped_column(Integer)
    cardmarket_product_override: Mapped[int | None] = mapped_column(Integer)
    # Kartendetails aus TCGdex (Hintergrund-Abgleich, :mod:`app.services.card_details`):
    # welche Varianten es gibt ({"normal": true, "reverse": true, "holo": false, …}),
    # Illustrator und Zeitpunkt des letzten Abgleichs.
    variants: Mapped[dict[str, bool] | None] = mapped_column(JSONB)
    illustrator: Mapped[str | None] = mapped_column(String(120))
    details_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[CardSource] = mapped_column(
        Enum(
            CardSource,
            native_enum=False,
            length=16,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=CardSource.TCGDEX,
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    card_set: Mapped[CardSet] = relationship(lazy="joined")
