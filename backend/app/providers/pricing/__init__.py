"""Preisquellen: gemeinsame Schnittstelle (``PriceProvider``) und Datentypen.

Eine Preisquelle liefert für eine Karte belegte Preiswerte (``PriceQuote``). Jeder Wert
trägt Quelle, Datum und – wenn möglich – einen Beleglink. **Kein Beleg, kein Preis:**
eine Quelle darf keine Werte erfinden oder schätzen; Schätzungen macht ausschließlich
der Kern (``app.services.pricing``) und kennzeichnet sie als solche.

Eigene Quellen (Plug-ins) implementieren dieses Protokoll und werden über
``PT_EXTRA_PRICE_PROVIDERS`` eingebunden (siehe ``app.providers.pricing.plugins``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

PriceKind = Literal["verified", "external"]

# Zustände nach Cardmarket-Skala (Mint … Poor).
Condition = Literal["MT", "NM", "EX", "GD", "LP", "PL", "PO"]
CONDITIONS: tuple[Condition, ...] = ("MT", "NM", "EX", "GD", "LP", "PL", "PO")


@dataclass(frozen=True)
class CardRef:
    """Was eine Preisquelle über die Karte wissen darf."""

    card_id: uuid.UUID
    external_id: str | None
    language: str
    name: str
    number: str
    set_name: str
    # Nur für Quellen mit ``needs_context`` (z. B. PriceCharting, sucht englisch):
    english_name: str | None = None
    english_set_name: str | None = None
    release_date: date | None = None
    graded: bool = False  # liegt bei jemandem als Slab in der Sammlung
    pricecharting_url: str | None = None  # bekannte PriceCharting-Produktseite


@dataclass(frozen=True)
class PriceQuote:
    """Ein belegter Preiswert.

    ``metric`` z. B. ``trend``, ``low``, ``avg30``; ``variant`` z. B. ``normal``,
    ``reverse``, ``holo``; ``condition`` nur, wenn die Quelle zustandsgenaue Preise liefert.
    """

    source: str
    variant: str
    metric: str
    value: Decimal
    currency: str
    source_updated_at: datetime
    source_url: str | None
    condition: str | None = None


class PriceNotAvailableError(Exception):
    """Die Quelle kennt die Karte nicht (kein Fehler der Quelle – zählt nicht als Ausfall)."""


@runtime_checkable
class PriceProvider(Protocol):
    """Schnittstelle jeder Preisquelle."""

    name: str
    """Eindeutiger, stabiler Name (Schlüssel für Abruf-Status), z. B. ``tcgdex``."""

    kind: PriceKind
    """``verified`` (eingebaute Quelle) oder ``external`` (Plug-in)."""

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        """Aktuelle Preise. Leere Liste = keine Preise; Ausnahme = Quelle gestört."""
        ...
