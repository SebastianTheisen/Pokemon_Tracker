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
from app.models import PriceChartingDetail
from app.providers.pricing import Condition
from app.services.cardmarket_catalog import CardmarketChoice, ChoiceResult
from app.services.price_health import SourceStatus
from app.services.pricecharting_details import latest_sales
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
    cardmarket_link: str | None = Field(
        default=None, description="Korrigierte Cardmarket-Seite (statt der TCGdex-Zuordnung)."
    )

    @classmethod
    def build(cls, prices: CardPrices) -> CardPricesOut:
        return cls(
            card_id=prices.card_id,
            status="ok" if prices.has_prices else "no_data",
            last_checked_at=prices.last_checked_at,
            cardmarket_link=prices.cardmarket_link,
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
    remember_page: bool = Field(
        default=False,
        description="Beim Speichern diese Produktseite künftig für die Karte verwenden "
        "(korrigiert eine falsche Cardmarket-Zuordnung von TCGdex).",
    )


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


class EbaySoldRowIn(BaseModel):
    """Ein vom Lesezeichen ausgelesener eBay-Verkauf (Rohtexte)."""

    title: str = Field(max_length=300)
    price: str = Field(max_length=80)
    sold: str = Field(default="", max_length=120, description="z. B. „Verkauft 12. Okt 2026“")
    url: str = Field(default="", max_length=600)


class EbaySoldIn(BaseModel):
    page_url: str = Field(max_length=2000)
    rows: list[EbaySoldRowIn] = Field(max_length=120)
    selected: list[int] | None = Field(
        default=None, description="Gewählte Zeilen; ohne Angabe gilt der Vorschlag."
    )
    save: bool = False


class EbaySaleOut(BaseModel):
    index: int
    title: str
    price: Decimal | None
    sold_on: date | None
    group: str = Field(description="„raw“ oder z. B. „PSA 10“")
    url: str
    issues: list[str]
    suggested: bool


class EbayGroupOut(BaseModel):
    group: str
    median: Decimal
    low: Decimal
    high: Decimal
    count: int


class EbaySoldOut(BaseModel):
    card_id: uuid.UUID
    page_url: str
    sales: list[EbaySaleOut]
    groups: list[EbayGroupOut]
    warnings: list[str]
    saved: int


class PriceTargetIn(BaseModel):
    card_id: uuid.UUID


class PriceTargetOut(BaseModel):
    card_id: uuid.UUID | None = Field(
        description="Zuletzt zum Preisholen geöffnete Karte (höchstens 2 Stunden alt)."
    )


class CardmarketOptionOut(BaseModel):
    """Dieselbe Karte in einer Cardmarket-Ausgabe (Sprachfassung)."""

    product_id: int
    expansion_id: int
    expansion_label: str | None
    expansion_size: int | None
    name: str
    trend: Decimal | None
    low: Decimal | None
    url: str
    selected: bool
    from_tcgdex: bool


class CardmarketChoiceOut(BaseModel):
    """Cardmarket-Produkt einer Karte und die Alternativen zur Auswahl."""

    card_id: uuid.UUID
    product_id: int | None
    expansion_id: int | None
    reason: Literal["tcgdex", "set", "card", "unmapped", "none"] = Field(
        description=(
            "tcgdex: wie von TCGdex gemeldet · set: über die Ausgabe des Sets umgehängt · "
            "card: für diese Karte gewählt · unmapped: in der Ausgabe nicht gefunden · "
            "none: kein Produkt bekannt"
        )
    )
    set_source: str | None = Field(description="Ausgabe des Sets von: tcgdex, builtin, user")
    uncertain: bool = Field(description="Es gibt Sprachfassungen; Ausgabe nur von TCGdex.")
    catalog_ready: bool
    url: str | None
    options: list[CardmarketOptionOut]
    set_changed: bool | None = Field(
        default=None, description="Nur nach einer Auswahl: galt sie für das ganze Set?"
    )
    cards_affected: int | None = None

    @classmethod
    def build(
        cls, choice: CardmarketChoice, result: ChoiceResult | None = None
    ) -> CardmarketChoiceOut:
        return cls(
            card_id=choice.card_id,
            product_id=choice.product_id,
            expansion_id=choice.expansion_id,
            reason=choice.reason,
            set_source=choice.set_source,
            uncertain=choice.uncertain,
            catalog_ready=choice.catalog_ready,
            url=choice.url,
            options=[CardmarketOptionOut(**option.__dict__) for option in choice.options],
            set_changed=result.set_changed if result else None,
            cards_affected=result.cards_affected if result else None,
        )


class CardmarketChoiceIn(BaseModel):
    product_id: int = Field(gt=0, description="Gewähltes Cardmarket-Produkt (``idProduct``).")


class CardmarketExpansionIn(BaseModel):
    label: str | None = Field(
        default=None, max_length=100, description="z. B. „Japanisch“; leer = entfernen"
    )


class CardmarketExpansionOut(BaseModel):
    expansion_id: int
    label: str | None
    product_count: int
    twin_ids: list[int]


class EbayFetchIn(BaseModel):
    """Verkäufe von ebay.de über Apify holen (kostet Guthaben, außer gemerkt)."""

    grading: str | None = Field(
        default=None,
        max_length=20,
        pattern=r"^(PSA|BGS|CGC|SGC|TAG|ACE) \d{1,2}(\.\d)?( BL)?$",
        description="Slab, z. B. „PSA 10“; leer = Rohkarte (gegradete werden ausgeschlossen)",
    )
    force: bool = Field(default=False, description="Gemerkte Suche ignorieren und neu abrufen")


class EbayFetchOut(BaseModel):
    """Rohzeilen wie vom Lesezeichen – Vorschau/Speichern über ``POST …/ebay-sold``."""

    card_id: uuid.UUID
    query: str
    page_url: str
    rows: list[EbaySoldRowIn]
    fetched_at: datetime
    cached: bool
    cost_usd: Decimal | None
    used_usd: float | None
    budget_usd: float | None


class ApifyStatusOut(BaseModel):
    configured: bool
    used_usd: float | None
    limit_usd: float | None
    budget_usd: float | None
    remaining_usd: float | None
    cycle_end: datetime | None


class SaleOut(BaseModel):
    grade: str
    date: str | None
    title: str | None
    price_usd: float
    source: str | None
    url: str | None


class PriceChartingDetailsOut(BaseModel):
    """US-Markt laut PriceCharting: POP-Report, Verkäufe je Note, letzte Verkäufe."""

    available: bool
    fetched_at: datetime | None = None
    product_url: str | None = None
    population: dict[str, dict[str, int]] = Field(default_factory=dict)
    sales_volume: dict[str, int] = Field(default_factory=dict)
    recent_sales: list[SaleOut] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)

    @classmethod
    def build(cls, detail: PriceChartingDetail | None) -> PriceChartingDetailsOut:
        if detail is None:
            return cls(available=False)
        population = {
            str(company): {str(grade): int(count) for grade, count in grades.items()}
            for company, grades in (detail.population or {}).items()
            if isinstance(grades, dict)
        }
        return cls(
            available=True,
            fetched_at=detail.fetched_at,
            product_url=detail.product_url,
            population=population,
            sales_volume={
                str(label): int(count)
                for label, count in (detail.sales_volume or {}).items()
                if isinstance(count, int)
            },
            recent_sales=[SaleOut(**sale.__dict__) for sale in latest_sales(detail)],
            images=list(detail.images or []),
        )
