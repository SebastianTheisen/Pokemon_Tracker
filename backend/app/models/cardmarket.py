"""Offizieller Cardmarket-Katalog (Download-Dateien) und Verknüpfung mit unseren Sets.

Cardmarket stellt Produktkatalog und Preisführer für Pokémon täglich als JSON-Datei bereit
(``downloads.s3.cardmarket.com/productCatalog/…``, Spike ``docs/phase5/cardmarket_katalog.md``):

* ``cm_products`` – jede Einzelkarte mit ``idExpansion`` (Ausgabe, z. B. „30th Celebration
  japanisch“) und ``idMetacard`` (dieselbe Karte über alle Ausgaben und Sprachen hinweg).
  Namen enthalten weder Setkürzel noch Nummer.
* ``cm_prices`` – aktueller Stand des Preisführers je Produkt (Trend, Low, Ø 1/7/30 Tage,
  jeweils auch für Reverse Holo mit Suffix ``-holo``).
* ``cm_expansions`` – je Ausgabe Größe, erstes Datum und „Zwillinge“: Ausgaben mit fast
  denselben Karten, die zur selben Zeit erschienen sind (z. B. japanische und chinesische
  Fassung desselben Sets). Namen der Ausgaben stehen nicht im Download; Nutzer können eine
  Bezeichnung vergeben („Japanisch“).
* ``cm_imports`` – Protokoll der Importläufe.

TCGdex ordnet Sets geschlossen einer Ausgabe zu – manchmal der falschen Sprachfassung
(``ja/M6a`` → vereinfacht-chinesische Ausgabe). Deshalb merkt sich jedes Set seine Ausgabe
(``card_sets.cardmarket_expansion_id``); Karten werden über ``idMetacard`` in diese Ausgabe
umgehängt (siehe :mod:`app.services.cardmarket_catalog`).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExpansionLinkSource(enum.StrEnum):
    """Woher die Cardmarket-Ausgabe eines Sets stammt (Rangfolge: Nutzer > fest > TCGdex)."""

    TCGDEX = "tcgdex"  # aus der Cardmarket-ID, die TCGdex für eine Karte des Sets meldet
    BUILTIN = "builtin"  # fest hinterlegt (bekannte Fehler von TCGdex)
    USER = "user"  # von einem Nutzer in der App gewählt


class CmProduct(Base):
    """Eine Einzelkarte aus dem Cardmarket-Produktkatalog."""

    __tablename__ = "cm_products"

    id_product: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    id_expansion: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    id_metacard: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    date_added: Mapped[date | None] = mapped_column(Date)


class CmPrice(Base):
    """Aktueller Preisführer-Eintrag eines Produkts (Werte in Euro, ``0``/``null`` = keiner)."""

    __tablename__ = "cm_prices"

    id_product: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    metrics: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CmExpansion(Base):
    """Eine Cardmarket-Ausgabe mit Größe, Zwillingen und optionaler Bezeichnung."""

    __tablename__ = "cm_expansions"

    id_expansion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    product_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_added: Mapped[date | None] = mapped_column(Date)
    twin_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default=text("'{}'"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(100))
    label_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class CmImport(Base):
    """Ein Importlauf der Cardmarket-Downloads."""

    __tablename__ = "cm_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    prices: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    expansions: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    sets_linked: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    catalog_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guide_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
