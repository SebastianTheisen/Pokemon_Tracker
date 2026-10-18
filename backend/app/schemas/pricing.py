"""Schemas für Preise, Preisverlauf und Einstellungen.

Geldbeträge werden als Dezimal-**String** ausgegeben (z. B. ``"1805.90"``), damit keine
Rundungsfehler durch Gleitkommazahlen entstehen.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.config import CatalogLanguage
from app.providers.pricing import Condition
from app.services.price_health import SourceStatus
from app.services.pricing import CardPrices, ConditionPrice, Offer, PriceHistory

Factor = Annotated[Decimal, Field(gt=0, le=3, max_digits=4, decimal_places=2)]


class OfferOut(BaseModel):
    source: str
    variant: str
    condition: str | None
    currency: str
    kind: Literal["verified", "external"]
    updated_at: datetime
    url: str | None
    metrics: dict[str, Decimal]

    @classmethod
    def build(cls, offer: Offer) -> OfferOut:
        return cls(**offer.__dict__)


class ConditionPriceOut(BaseModel):
    variant: str
    condition: str
    value: Decimal
    currency: str
    kind: Literal["estimated", "external"] = Field(
        description="„estimated“ = Schätzung (NM-Referenz × Faktor), „external“ = belegt."
    )
    source: str
    updated_at: datetime
    url: str | None
    basis_metric: str | None = Field(description="z. B. „median(trend, avg7, avg30)“.")
    basis_value: Decimal | None
    factor: Decimal | None = Field(description="Zustandsfaktor.")
    language_factor: Decimal | None = Field(
        default=None, description="Sprachfaktor der Karte (1,00 = keiner)."
    )

    @classmethod
    def build(cls, price: ConditionPrice) -> ConditionPriceOut:
        return cls(**price.__dict__)


class CardPricesOut(BaseModel):
    card_id: uuid.UUID
    status: Literal["ok", "no_data"]
    last_checked_at: datetime | None
    offers: list[OfferOut]
    conditions: list[ConditionPriceOut]

    @classmethod
    def build(cls, prices: CardPrices) -> CardPricesOut:
        return cls(
            card_id=prices.card_id,
            status="ok" if prices.has_prices else "no_data",
            last_checked_at=prices.last_checked_at,
            offers=[OfferOut.build(o) for o in prices.offers],
            conditions=[ConditionPriceOut.build(c) for c in prices.conditions],
        )


class HistoryPointOut(BaseModel):
    date: date
    value: Decimal


class PriceHistoryOut(BaseModel):
    source: str
    variant: str
    metric: str
    currency: str | None
    points: list[HistoryPointOut]
    lowest: Decimal | None = Field(description="Tiefster belegter Wert seit Beobachtungsbeginn.")
    highest: Decimal | None = Field(description="Höchster belegter Wert seit Beobachtungsbeginn.")
    observed_since: datetime | None

    @classmethod
    def build(cls, history: PriceHistory) -> PriceHistoryOut:
        return cls(
            source=history.source,
            variant=history.variant,
            metric=history.metric,
            currency=history.currency,
            points=[HistoryPointOut(date=p.day, value=p.value) for p in history.points],
            lowest=history.lowest,
            highest=history.highest,
            observed_since=history.observed_since,
        )


class UserSettingsOut(BaseModel):
    condition_factors: dict[str, Decimal] = Field(description="Wirksame Faktoren (inkl. Standard).")
    custom_condition_factors: list[str] = Field(description="Zustände mit eigenem Faktor.")
    language_factors: dict[str, Decimal] = Field(
        description="Faktor je Kartensprache auf den Cardmarket-Preis (Standard 1,00)."
    )
    custom_language_factors: list[str] = Field(description="Sprachen mit eigenem Faktor.")
    default_language: str | None


class UserSettingsUpdate(BaseModel):
    condition_factors: dict[Condition, Factor] | None = None
    reset_condition_factors: bool = False
    language_factors: dict[CatalogLanguage, Factor] | None = None
    reset_language_factors: bool = False
    default_language: CatalogLanguage | None = None


class PriceSourceOut(BaseModel):
    name: str
    kind: Literal["verified", "external"]
    paused: bool
    consecutive_failures: int
    paused_until: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    last_success_at: datetime | None

    @classmethod
    def build(
        cls, status: SourceStatus, kind: Literal["verified", "external"], paused: bool
    ) -> PriceSourceOut:
        return cls(kind=kind, paused=paused, **status.__dict__)


class CardmarketOfferRowIn(BaseModel):
    """Ein vom Lesezeichen ausgelesenes Angebot (Rohtexte der Seite)."""

    condition: str = Field(max_length=8, description="z. B. „NM“")
    price: str = Field(max_length=40, description="z. B. „1.234,56 €“")
    labels: list[Annotated[str, Field(max_length=80)]] = Field(
        default_factory=list,
        max_length=12,
        description="Beschriftungen der Symbole: Sprache, Reverse Holo, signiert …",
    )


class CardmarketOffersIn(BaseModel):
    page_url: str = Field(max_length=2000, description="Ausgelesene Cardmarket-Seite.")
    rows: list[CardmarketOfferRowIn] = Field(max_length=200)
    save: bool = Field(default=False, description="false = nur Vorschau.")


class CardmarketConditionOut(BaseModel):
    variant: str
    condition: str
    low: Decimal = Field(description="Günstigstes Angebot (Zustand oder besser).")
    low3: Decimal = Field(description="Durchschnitt der drei günstigsten.")
    offers: int


class CardmarketOffersOut(BaseModel):
    card_id: uuid.UUID
    card_language: str
    page_url: str
    accepted: int
    skipped: int
    prices: list[CardmarketConditionOut]
    warnings: list[str]
    saved: int
