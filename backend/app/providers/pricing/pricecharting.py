"""Preise von PriceCharting (US-Markt, eBay-Verkäufe) – Ergänzung, wo Cardmarket fehlt.

Spike ``docs/phase5/apify_runs_i.md``: PriceCharting kennt englische, japanische,
koreanische und chinesische Karten (keine deutschen) mit Preisen für ungegradet und
Grade 7, 8, 9, 9.5 sowie PSA 10 – in US-Dollar. Abgerufen über den Apify-Dienst
``gio21/pricecharting-scraper`` (Suche, ~0,005 $ je Treffer).

* Gesucht wird englisch: Name + Nummer (+ „Japanese“/„Korean“/„Chinese“).
* Ein Treffer zählt nur, wenn Nummer, Sprache und Name passen; bei mehreren entscheidet
  der Set-Name bzw. das Erscheinungsdatum. Zweideutig → kein Preis (lieber keiner als ein
  falscher).
* Umgerechnet mit dem EZB-Tageskurs, gespeichert in Euro. Die Anzeige kennzeichnet die Werte
  als umgerechneten US-Preis.
* Abgerufen wird nur bei Bedarf (``fallback_only``: kein Cardmarket-Preis oder Slab in einer
  Sammlung) und höchstens alle ``pricecharting_max_age_days`` Tage. Das Apify-Monatsbudget
  behält eine Reserve für eBay-Abrufe.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

import structlog

from app.core.config import Settings
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.providers.pricing import CardRef, PriceKind, PriceNotAvailableError, PriceQuote
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

PRICECHARTING = "pricecharting"
RAW_VARIANT = "normal"
GRADED_VARIANT = "graded"
RAW_METRIC = "ungraded"
GRADE_METRICS = ("grade_7", "grade_8", "grade_9", "grade_9_5", "psa_10")
LANGUAGE_MARKERS = {"ja": "japanese", "ko": "korean", "zh-tw": "chinese", "zh-cn": "chinese"}
_FOREIGN = ("japanese", "korean", "chinese", "german", "french", "italian", "spanish")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"pokemon", "the", "and", "of", *LANGUAGE_MARKERS.values()})
DATE_WINDOW_DAYS = 120
SEARCH_URL = "https://www.pricecharting.com/search-products?type=prices&q="

AsyncClientFactory = Callable[[], ApifyClient]


class ApifyBudgetError(Exception):
    """Monatsbudget (abzüglich Reserve für eBay) erreicht – später erneut versuchen."""


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if word not in _STOP}


def _usd(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def _release(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%B %d, %Y").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def search_query(card: CardRef) -> str | None:
    """Suchbegriff wie auf PriceCharting: englischer Name, Nummer, Sprachzusatz."""
    if not card.english_name:
        return None
    number = normalize_number(card.number) or card.number
    marker = LANGUAGE_MARKERS.get(card.language, "")
    return " ".join(part for part in (card.english_name, number, marker.title()) if part)


@dataclass(frozen=True)
class Match:
    item: dict[str, Any]
    score: float


def _candidates(card: CardRef, items: Sequence[dict[str, Any]]) -> list[Match]:
    """Treffer mit passender Sprache, Nummer und Name, bewertet nach Set und Datum."""
    marker = LANGUAGE_MARKERS.get(card.language)
    number = normalize_number(card.number)
    name_words = _words(card.english_name or "")
    key_word = max(name_words, key=len, default="")
    set_words = _words(card.english_set_name or card.set_name)
    matches = []
    for item in items:
        console = str(item.get("console") or "").casefold()
        name = str(item.get("name") or "")
        if not console.startswith("pokemon") or item.get("category") not in (None, "trading-card"):
            continue
        if marker is not None and marker not in console:
            continue
        if marker is None and any(foreign in console for foreign in _FOREIGN):
            continue
        item_number = str(item.get("card_number") or "") or name.rpartition("#")[2]
        if normalize_number(item_number) != number:
            continue
        if key_word and key_word not in name.casefold():
            continue
        console_words = _words(console)
        overlap = len(set_words & console_words) / len(set_words | console_words or {""})
        released = _release(item.get("release_date"))
        near = (
            card.release_date is not None
            and released is not None
            and abs((released - card.release_date).days) <= DATE_WINDOW_DAYS
        )
        matches.append(Match(item, overlap + (0.5 if near else 0.0)))
    return sorted(matches, key=lambda match: match.score, reverse=True)


def choose(card: CardRef, items: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Der eindeutig beste Treffer oder ``None``."""
    matches = _candidates(card, items)
    if not matches:
        return None
    if len(matches) > 1 and matches[0].score == matches[1].score:
        return None  # zweideutig, z. B. gleiche Nummer in zwei Sets ohne Set-Hinweis
    return matches[0].item


def quotes_from_item(
    item: dict[str, Any], *, per_euro: Decimal, fetched_at: datetime
) -> list[PriceQuote]:
    """PriceCharting-Preise (USD) → Euro-Werte: ungegradet und je Note."""
    prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
    url = str(item.get("url") or "")
    source_url = url if "/game/" in url else None
    quotes = []
    for key in (RAW_METRIC, *GRADE_METRICS):
        entry = prices.get(key) if isinstance(prices, dict) else None
        amount = _usd(entry.get("price") if isinstance(entry, dict) else entry)
        if amount is None:
            continue
        quotes.append(
            PriceQuote(
                source=PRICECHARTING,
                variant=RAW_VARIANT if key == RAW_METRIC else GRADED_VARIANT,
                metric=key,
                value=amount / per_euro,
                currency="EUR",
                source_updated_at=fetched_at,
                source_url=source_url,
            )
        )
    return quotes


def detail_metric(label: str) -> str | None:
    """Spalte der Detailseite → Kennzahl: „Grade 9.5“ → ``grade_9_5``, „BGS 10 Black“ →
    ``bgs_10_black``, „CGC 10 Pristine“ → ``cgc_10_pristine``, „Ungraded“ → ``ungraded``."""
    key = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    if key == RAW_METRIC:
        return RAW_METRIC
    if re.fullmatch(r"grade_\d{1,2}(_5)?|(psa|bgs|cgc|sgc|tag|ace)_10(_black|_pristine)?", key):
        return key
    return None


def quotes_from_details(
    item: dict[str, Any], *, per_euro: Decimal, fetched_at: datetime
) -> list[PriceQuote]:
    """Alle Noten der Detailseite (``fullPrices``) in Euro: je Firma bei Note 10."""
    full = item.get("fullPrices")
    url = str(item.get("url") or "") or None
    quotes = []
    for label, value in full.items() if isinstance(full, dict) else ():
        metric = detail_metric(str(label))
        amount = _usd(value)
        if metric is None or amount is None:
            continue
        quotes.append(
            PriceQuote(
                source=PRICECHARTING,
                variant=RAW_VARIANT if metric == RAW_METRIC else GRADED_VARIANT,
                metric=metric,
                value=amount / per_euro,
                currency="EUR",
                source_updated_at=fetched_at,
                source_url=url,
            )
        )
    return quotes


class PriceChartingProvider:
    """Preisquelle PriceCharting über Apify (nur bei Bedarf, siehe Modulbeschreibung)."""

    name = PRICECHARTING
    kind: PriceKind = "verified"
    fallback_only = True
    needs_context = True
    timeout_seconds = 45.0  # Apify-Lauf: Start + Suche dauern meist 5–15 s

    def __init__(
        self,
        settings: Settings,
        rates: EcbRates,
        client_factory: AsyncClientFactory,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._rates = rates
        self._client_factory = client_factory
        self._now = clock
        self.max_age_hours = settings.pricecharting_max_age_days * 24
        # Zuletzt geholte Produktseite je Karte – der Preis-Service speichert sie.
        self._fetched_details: dict[uuid.UUID, dict[str, Any]] = {}

    def take_details(self, card_id: uuid.UUID) -> dict[str, Any] | None:
        """Details des letzten Abrufs dieser Karte (einmalig abholbar)."""
        return self._fetched_details.pop(card_id, None)

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        """Bekannte Produktseite → Details (günstig, exakt); sonst Suche, bei Slabs danach
        Details für die Preise je Grading-Firma."""
        rate = await self._rates.rate("USD")  # vor dem bezahlten Abruf prüfen
        url, searched, query = card.pricecharting_url, None, None
        async with self._client_factory() as client:
            await self._check_budget(client)
            if url is None:
                query = search_query(card)
                if query is None:
                    raise PriceNotAvailableError("kein englischer Kartenname")
                searched = await self._search(client, card, query)
                product_url = str(searched.get("url") or "")
                if not card.graded or "/game/" not in product_url:
                    return self._with_link(
                        quotes_from_item(searched, per_euro=rate.per_euro, fetched_at=self._now()),
                        query,
                    )
                url = product_url
            detail = await self._details(client, url)
        if detail is not None:
            self._fetched_details[card.card_id] = detail
            quotes = quotes_from_details(detail, per_euro=rate.per_euro, fetched_at=self._now())
            if quotes:
                return quotes
        if searched is not None and query is not None:  # Details leer → Suchergebnis reicht
            return self._with_link(
                quotes_from_item(searched, per_euro=rate.per_euro, fetched_at=self._now()), query
            )
        raise PriceNotAvailableError("Produktseite ohne Preise")

    async def _search(self, client: ApifyClient, card: CardRef, query: str) -> dict[str, Any]:
        run = await client.run_actor(
            self._settings.pricecharting_actor,
            {"searchQueries": [query], "maxItems": self._settings.pricecharting_max_items},
            max_charge_usd=self._settings.pricecharting_max_charge_usd,
            timeout_seconds=self._settings.apify_run_timeout_seconds,
            max_items=self._settings.pricecharting_max_items,
        )
        item = choose(card, run.items)
        log.info(
            "pricecharting.searched",
            card=str(card.card_id),
            query=query,
            results=len(run.items),
            matched=item is not None,
            cost=run.cost_usd,
        )
        if item is None:
            raise PriceNotAvailableError(f"kein eindeutiger Treffer für „{query}“")
        return item

    async def _details(self, client: ApifyClient, url: str) -> dict[str, Any] | None:
        run = await client.run_actor(
            self._settings.pricecharting_detail_actor,
            {"products": [url], "scrapeProductDetails": True, "maxItems": 1},
            max_charge_usd=self._settings.pricecharting_max_charge_usd,
            timeout_seconds=self._settings.apify_run_timeout_seconds,
            max_items=1,
        )
        log.info("pricecharting.details", url=url, results=len(run.items), cost=run.cost_usd)
        return run.items[0] if run.items else None

    @staticmethod
    def _with_link(quotes: list[PriceQuote], query: str) -> list[PriceQuote]:
        if not quotes:
            raise PriceNotAvailableError("Treffer ohne Preis")
        if quotes[0].source_url is None:  # Suche landete direkt auf dem Produkt
            link = SEARCH_URL + quote_plus(query)
            quotes = [dataclasses.replace(quote, source_url=link) for quote in quotes]
        return quotes

    async def _check_budget(self, client: ApifyClient) -> None:
        usage = await client.usage()
        budget = self._settings.apify_monthly_budget_usd
        if usage.limit_usd > 0:
            budget = min(budget, usage.limit_usd)
        spendable = budget - self._settings.pricecharting_reserve_usd
        if usage.used_usd + self._settings.pricecharting_max_charge_usd > spendable:
            raise ApifyBudgetError(
                f"Apify-Budget für PriceCharting erreicht ({usage.used_usd:.2f} $ von "
                f"{budget:.2f} $, Reserve {self._settings.pricecharting_reserve_usd:.2f} $)"
            )
