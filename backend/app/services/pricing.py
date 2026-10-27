"""Preislogik: Abruf aus den Quellen, Historie, Anzeige mit Zustandsschätzung.

Regeln (Plan 5.3):

* **Kein Beleg, kein Preis.** Angezeigt werden nur Werte, die eine Quelle mit Datum (und
  wenn möglich Link) geliefert hat.
* **Schätzungen sind markiert.** Zustandspreise = NM-Basis × Zustandsfaktor × Sprachfaktor
  des Nutzers; NM-Basis ist der Median aus Cardmarket-Trend, Ø 7 und Ø 30 Tagen (Ersatz:
  Durchschnitt). Der Sprachfaktor (Standard 1,00) gilt für die Sprache der Karte, weil
  Cardmarket westliche Karten aller Sprachen als ein Produkt führt.
  Liefert eine externe Quelle einen echten Zustandspreis, hat dieser Vorrang.
* **Quellen sind isoliert.** Zeitlimit je Abruf; Fehler einer Quelle stören weder andere
  Quellen noch die Anzeige; nach Fehlern in Folge pausiert die Quelle (``SourceHealth``).
"""

from __future__ import annotations

import asyncio
import dataclasses
import statistics
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy import exists, func, select, union
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    Card,
    CardPriceLink,
    CmPrice,
    CollectionItem,
    Game,
    PriceAlert,
    PriceCheck,
    PricePoint,
    User,
    WishlistItem,
)
from app.providers.pricing import (
    CONDITIONS,
    CardRef,
    PriceKind,
    PriceNotAvailableError,
    PriceProvider,
    PriceQuote,
)
from app.providers.pricing.pricecharting import (
    PRICECHARTING,
    RAW_METRIC,
    RAW_VARIANT,
)
from app.providers.pricing.tcgdex_prices import CARDMARKET, TCGPLAYER
from app.services.card_names import translate_card_name
from app.services.cardmarket_catalog import (
    correct_cardmarket_quotes,
    product_url,
    resolve_product,
)
from app.services.price_health import SourceHealth
from app.services.pricecharting_details import store_details
from app.services.user_settings import (
    effective_factors,
    effective_language_factors,
    get_user_settings,
)

log = structlog.get_logger(__name__)

VERIFIED_SOURCES = frozenset({CARDMARKET, TCGPLAYER, PRICECHARTING})
# NM-Basis = Median dieser Werte (Nutzerentscheidung 17.10.2026): robust gegen Ausreißer
# wie einen Trend unter dem günstigsten Angebot. Ersatz, wenn keiner vorhanden ist: ``avg``.
NM_MEDIAN_METRICS = ("trend", "avg7", "avg30")
NM_FALLBACK_METRIC = "avg"
CENT = Decimal("0.01")

Clock = Callable[[], datetime]
FetchOutcome = Literal[
    "fetched", "fresh", "retry_later", "paused", "failed", "not_available", "not_needed"
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ----------------------------------------------------------------- Ergebnisse


@dataclass(frozen=True)
class Offer:
    """Alle aktuellen Werte einer Quelle für eine Variante (und ggf. einen Zustand)."""

    source: str
    variant: str
    condition: str | None
    currency: str
    kind: Literal["verified", "external"]
    updated_at: datetime
    url: str | None
    metrics: dict[str, Decimal]


@dataclass(frozen=True)
class ConditionPrice:
    """Preis je Zustand – geschätzt (Faktor) oder von einer externen Quelle belegt."""

    variant: str
    condition: str
    value: Decimal
    currency: str
    kind: Literal["estimated", "external"]
    source: str
    updated_at: datetime
    url: str | None
    basis_metric: str | None = None
    basis_value: Decimal | None = None
    factor: Decimal | None = None
    language_factor: Decimal | None = None


@dataclass(frozen=True)
class CardPrices:
    card_id: uuid.UUID
    last_checked_at: datetime | None
    offers: list[Offer]
    conditions: list[ConditionPrice]
    cardmarket_link: str | None = None
    """Von Nutzern korrigierte Cardmarket-Seite (dann ohne Cardmarket-Werte von TCGdex)."""

    @property
    def has_prices(self) -> bool:
        return bool(self.offers)


@dataclass(frozen=True)
class HistoryPoint:
    day: date
    value: Decimal


@dataclass(frozen=True)
class PriceHistory:
    source: str
    variant: str
    metric: str
    currency: str | None
    points: list[HistoryPoint]
    lowest: Decimal | None
    highest: Decimal | None
    observed_since: datetime | None


@dataclass
class RefreshReport:
    outcomes: dict[str, FetchOutcome] = field(default_factory=dict)
    quotes_stored: int = 0


class GuideOnlyProvider:
    """Quelle für Spiele ohne eigene Preisquelle (One Piece): Sie kennt keine Karte – dadurch
    greifen die Werte des Cardmarket-Preisführers für das verknüpfte Produkt."""

    name = "cardmarket-guide"
    kind: PriceKind = "verified"

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        raise PriceNotAvailableError(f"{card.game}: nur Cardmarket-Preisführer")


GUIDE_ONLY = GuideOnlyProvider()


def card_ref(card: Card) -> CardRef:
    return CardRef(
        card_id=card.id,
        external_id=card.external_id,
        language=card.language,
        name=card.name,
        number=card.number,
        set_name=card.card_set.name,
        game=card.card_set.game,
    )


# --------------------------------------------------------------------- Service


class PriceService:
    """Preise abrufen, speichern und für die Anzeige aufbereiten. Commit macht der Aufrufer."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        providers: Sequence[PriceProvider],
        health: SourceHealth,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session = session
        self._settings = settings
        self._providers = providers
        self._health = health
        self._now = clock

    @property
    def providers(self) -> Sequence[PriceProvider]:
        return self._providers

    @property
    def health(self) -> SourceHealth:
        return self._health

    # ------------------------------------------------------------- Abruf

    async def refresh(
        self, card: Card, *, force: bool = False, viewed: bool = False
    ) -> RefreshReport:
        """Holt Preise, wenn sie veraltet sind (oder ``force``). ``viewed`` merkt die Karte
        für die tägliche Aktualisierung vor."""
        report = RefreshReport()
        now = self._now()
        # Die Quellen (TCGdex, PriceCharting, Plug-ins) kennen nur Pokémon; andere Spiele
        # bekommen ihre Werte allein aus dem Cardmarket-Preisführer.
        providers = self._providers if card.card_set.game == Game.POKEMON.value else [GUIDE_ONLY]
        for provider in providers:
            if getattr(provider, "fallback_only", False) and not await self._needs_fallback(card):
                report.outcomes[provider.name] = "not_needed"  # Cardmarket hat einen Preis
                continue
            check = await self._session.get(PriceCheck, (card.id, provider.name))
            outcome = self._decide(provider, check, now=now, force=force)
            ok = check.ok if check else False
            message = check.message if check else None
            checked_at = check.checked_at if check else now

            if outcome == "fetched":
                outcome, ok, message, stored = await self._fetch(provider, card)
                report.quotes_stored += stored
                checked_at = now
            elif outcome == "paused" and check is None:
                message = "Quelle pausiert"

            report.outcomes[provider.name] = outcome
            if check is not None or outcome != "fresh" or viewed:
                await self._upsert_check(
                    card, provider.name, checked_at=checked_at, ok=ok, message=message,
                    viewed_at=now if viewed else None,
                )  # fmt: skip
        return report

    def _decide(
        self, provider: PriceProvider, check: PriceCheck | None, *, now: datetime, force: bool
    ) -> FetchOutcome:
        if self._health.is_paused(provider.name):
            return "paused"
        # Quellen mit eigener Gültigkeit (bezahlte Abrufe) holen auch bei ``force`` nicht neu.
        own_age: int | None = getattr(provider, "max_age_hours", None)
        if check is None or (force and own_age is None):
            return "fetched"
        age = now - check.checked_at
        max_age = own_age or self._settings.price_max_age_hours
        if check.ok and age < timedelta(hours=max_age):
            return "fresh"
        if not check.ok and age < timedelta(minutes=self._settings.price_failure_retry_minutes):
            return "retry_later"
        return "fetched"

    async def _fetch(
        self, provider: PriceProvider, card: Card
    ) -> tuple[FetchOutcome, bool, str | None, int]:
        """Ruft eine Quelle mit Zeitlimit ab und speichert neue Werte."""
        try:
            reference = (
                await self._context_ref(card)
                if getattr(provider, "needs_context", False)
                else card_ref(card)
            )
            quotes = await asyncio.wait_for(
                provider.fetch(reference),
                timeout=getattr(provider, "timeout_seconds", None)
                or self._settings.price_provider_timeout_seconds,
            )
        except PriceNotAvailableError:
            self._health.record_success(provider.name)
            if provider.kind == "external":
                return "not_available", True, "Quelle kennt die Karte nicht", 0
            # Unbekannt bei TCGdex – ein verknüpftes Cardmarket-Produkt hat trotzdem Preise.
            quotes = await correct_cardmarket_quotes(self._session, card, card_ref(card), [])
            if not quotes:
                return "not_available", True, "Quelle kennt die Karte nicht", 0
            return "fetched", True, None, await self._store(card, quotes)
        except Exception as exc:  # Quellen (auch Plug-ins) dürfen nichts stören
            error = f"{type(exc).__name__}: {exc}"[:300]
            self._health.record_failure(provider.name, error)
            log.warning(
                "pricing.fetch_failed", source=provider.name, card=str(card.id), error=error
            )
            return "failed", False, error, 0

        self._health.record_success(provider.name)
        if provider.kind == "external":
            # Externe Quellen dürfen keine eingebauten Quellen „vortäuschen“.
            quotes = [dataclasses.replace(q, source=provider.name) for q in quotes]
        else:
            # TCGdex verknüpft manche Sets mit der falschen Sprachfassung bei Cardmarket.
            quotes = await correct_cardmarket_quotes(self._session, card, card_ref(card), quotes)
        stored = await self._store(card, quotes)
        take_details = getattr(provider, "take_details", None)
        if callable(take_details) and (details := take_details(card.id)) is not None:
            await store_details(self._session, card.id, details, fetched_at=self._now())
        return "fetched", True, None if quotes else "keine Preise", stored

    async def _needs_fallback(self, card: Card) -> bool:
        """Ergänzende Quelle nötig? Ja ohne Cardmarket-Preis (oder mit korrigiertem
        Cardmarket-Link, dessen Werte fehlen) und für Karten, die jemand als Slab besitzt."""
        has_cardmarket = await self._session.scalar(
            select(exists().where(PricePoint.card_id == card.id, PricePoint.source == CARDMARKET))
        )
        corrected = await self._session.scalar(
            select(exists().where(CardPriceLink.card_id == card.id))
        )
        if not has_cardmarket or corrected:
            return True
        return await self._is_graded(card)

    async def _is_graded(self, card: Card) -> bool:
        graded = await self._session.scalar(
            select(
                exists().where(
                    CollectionItem.card_id == card.id, CollectionItem.grading_company.is_not(None)
                )
            )
        )
        return bool(graded)

    async def _context_ref(self, card: Card) -> CardRef:
        """Karte mit englischem Namen und Set (für englisch suchende Quellen)."""
        name: str | None = card.name if card.language == "en" else None
        set_name: str | None = card.card_set.name if card.language == "en" else None
        if name is None and card.external_id:
            english = await self._session.scalar(
                select(Card).where(Card.external_id == card.external_id, Card.language == "en")
            )
            if english is not None:
                name, set_name = english.name, english.card_set.name
        if name is None:
            name = translate_card_name(card.name, card.language, target="en")
        # Bekannte Produktseite (Set-Import Korea/China oder frühere Suche) → kein Suchen.
        product_url = await self._session.scalar(
            select(PricePoint.source_url)
            .where(
                PricePoint.card_id == card.id,
                PricePoint.source == PRICECHARTING,
                PricePoint.source_url.like("%/game/%"),
            )
            .order_by(PricePoint.source_updated_at.desc())
            .limit(1)
        )
        return dataclasses.replace(
            card_ref(card),
            english_name=name,
            english_set_name=set_name,
            release_date=card.card_set.release_date,
            graded=await self._is_graded(card),
            pricecharting_url=product_url,
        )

    async def _store(self, card: Card, quotes: Sequence[PriceQuote]) -> int:
        if not quotes:
            return 0
        rows = [
            {
                "card_id": card.id,
                "source": q.source[:64],
                "variant": q.variant[:32],
                "metric": q.metric[:32],
                "condition": q.condition if q.condition in CONDITIONS else None,
                "value": q.value.quantize(CENT),
                "currency": q.currency[:3].upper(),
                "source_updated_at": q.source_updated_at,
                "source_url": (q.source_url or "")[:500] or None,
            }
            for q in quotes
        ]
        result = await self._session.execute(
            insert(PricePoint)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_price_points_identity")
            .returning(PricePoint.id)
        )
        return len(result.all())

    async def _upsert_check(
        self,
        card: Card,
        source: str,
        *,
        checked_at: datetime,
        ok: bool,
        message: str | None,
        viewed_at: datetime | None,
    ) -> None:
        values = {
            "card_id": card.id,
            "source": source,
            "checked_at": checked_at,
            "ok": ok,
            "message": message,
            "last_viewed_at": viewed_at,
        }
        update = {"checked_at": checked_at, "ok": ok, "message": message}
        if viewed_at is not None:
            update["last_viewed_at"] = viewed_at
        statement = insert(PriceCheck).values(values)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[PriceCheck.card_id, PriceCheck.source], set_=update
            )
        )
        # Die Identity-Map soll den frischen Stand liefern, nicht den alten.
        if (cached := await self._session.get(PriceCheck, (card.id, source))) is not None:
            await self._session.refresh(cached)

    # ------------------------------------------------------------- Anzeige

    async def preview_prices(
        self, cards: Sequence[Card], user: User | None
    ) -> dict[uuid.UUID, tuple[Decimal, bool]]:
        """Near-Mint-Preis je Karte für Trefferlisten: gespeicherter Zustandspreis (Normal, NM),
        sonst Basis aus dem Cardmarket-Preisführer (als Näherung markiert). Ruft keine Quelle ab.

        Rückgabe: Karten-ID → (Wert, ``True`` = Näherung bzw. Schätzung).
        """
        stored = await self.prices_for_cards([card.id for card in cards], user)
        result: dict[uuid.UUID, tuple[Decimal, bool]] = {}
        missing: list[tuple[Card, int]] = []
        for card in cards:
            nm = next(
                (
                    c
                    for c in stored[card.id].conditions
                    if c.variant == "normal" and c.condition == "NM"
                ),
                None,
            )
            if nm is not None:
                result[card.id] = (nm.value, nm.kind == "estimated")
            elif (product := (await resolve_product(self._session, card)).product_id) is not None:
                missing.append((card, product))
        if missing:
            guide = {
                row.id_product: row.metrics
                for row in await self._session.scalars(
                    select(CmPrice).where(CmPrice.id_product.in_([p for _, p in missing]))
                )
            }
            for card, product in missing:
                metrics = guide.get(product)
                numbers = {
                    key: Decimal(str(value))
                    for key, value in (metrics or {}).items()
                    if isinstance(value, int | float) and value > 0
                }
                if (basis := nm_basis(numbers)) is not None:
                    result[card.id] = (basis[1].quantize(CENT), True)
        return result

    async def get_prices(self, card: Card, user: User | None) -> CardPrices:
        """Aktuelle Preise je Quelle/Variante und Zustandspreise (Faktoren des Nutzers,
        ohne Nutzer die Standardfaktoren)."""
        prices = (await self.prices_for_cards([card.id], user))[card.id]
        if prices.cardmarket_link is None and not any(
            o.source == CARDMARKET for o in prices.offers
        ):
            # Umgehängtes Produkt ohne Werte im Preisführer: wenigstens richtig verlinken.
            resolution = await resolve_product(self._session, card)
            if resolution.corrected and resolution.product_id is not None:
                prices = dataclasses.replace(
                    prices, cardmarket_link=product_url(resolution.product_id)
                )
        return prices

    async def prices_for_cards(
        self, card_ids: Sequence[uuid.UUID], user: User | None
    ) -> dict[uuid.UUID, CardPrices]:
        """Wie ``get_prices``, aber für viele Karten mit wenigen Abfragen (Sammlungswert).

        Liest nur gespeicherte Preise – ruft keine Quelle ab.
        """
        ids = list(dict.fromkeys(card_ids))
        if not ids:
            return {}
        latest = (
            await self._session.scalars(
                select(PricePoint)
                .where(PricePoint.card_id.in_(ids))
                .ext(
                    distinct_on(
                        PricePoint.card_id,
                        PricePoint.source,
                        PricePoint.variant,
                        PricePoint.metric,
                        PricePoint.condition,
                    )
                )
                .order_by(
                    PricePoint.card_id,
                    PricePoint.source,
                    PricePoint.variant,
                    PricePoint.metric,
                    PricePoint.condition,
                    PricePoint.source_updated_at.desc(),
                )
            )
        ).all()
        per_card: dict[uuid.UUID, list[PricePoint]] = {card_id: [] for card_id in ids}
        for point in latest:
            per_card[point.card_id].append(point)

        user_settings = await get_user_settings(self._session, user) if user else None
        factors = effective_factors(user_settings)
        language_factors = effective_language_factors(user_settings)
        language_rows = await self._session.execute(
            select(Card.id, Card.language).where(Card.id.in_(ids))
        )
        languages = {row.id: row.language for row in language_rows}
        checked_rows = await self._session.execute(
            select(PriceCheck.card_id, func.max(PriceCheck.checked_at))
            .where(PriceCheck.card_id.in_(ids), PriceCheck.ok.is_(True))
            .group_by(PriceCheck.card_id)
        )
        checked: dict[uuid.UUID, datetime] = {row[0]: row[1] for row in checked_rows}
        link_rows = await self._session.execute(
            select(CardPriceLink.card_id, CardPriceLink.cardmarket_url).where(
                CardPriceLink.card_id.in_(ids)
            )
        )
        links = {row.card_id: row.cardmarket_url for row in link_rows}
        result: dict[uuid.UUID, CardPrices] = {}
        for card_id, points in per_card.items():
            offers = _group_offers(points)
            if card_id in links:
                # TCGdex hat hier das falsche Cardmarket-Produkt – dessen Werte nicht nutzen.
                offers = [o for o in offers if o.source != CARDMARKET]
            result[card_id] = CardPrices(
                card_id=card_id,
                last_checked_at=checked.get(card_id),
                cardmarket_link=links.get(card_id),
                offers=offers,
                conditions=_condition_prices(
                    offers,
                    factors,
                    language_factors.get(languages.get(card_id, ""), Decimal("1.00")),
                ),
            )
        return result

    async def get_history(
        self,
        card: Card,
        *,
        source: str = CARDMARKET,
        variant: str = "normal",
        metric: str = "trend",
        days: int = 365,
    ) -> PriceHistory:
        """Verlauf eines Werts (ein Punkt je Tag) plus Tiefst-/Höchstwert seit Beobachtung."""
        series = (
            PricePoint.card_id == card.id,
            PricePoint.source == source,
            PricePoint.variant == variant,
            PricePoint.metric == metric,
            PricePoint.condition.is_(None),
        )
        since = self._now() - timedelta(days=days)
        rows = (
            await self._session.execute(
                select(PricePoint.source_updated_at, PricePoint.value, PricePoint.currency)
                .where(*series, PricePoint.source_updated_at >= since)
                .order_by(PricePoint.source_updated_at)
            )
        ).all()
        per_day: dict[date, Decimal] = {}
        for updated_at, value, _currency in rows:
            per_day[updated_at.date()] = value  # letzter Wert des Tages gewinnt
        stats = (
            await self._session.execute(
                select(
                    func.min(PricePoint.value),
                    func.max(PricePoint.value),
                    func.min(PricePoint.source_updated_at),
                ).where(*series)
            )
        ).one()
        return PriceHistory(
            source=source,
            variant=variant,
            metric=metric,
            currency=rows[-1][2] if rows else None,
            points=[HistoryPoint(day, value) for day, value in per_day.items()],
            lowest=stats[0],
            highest=stats[1],
            observed_since=stats[2],
        )


# ------------------------------------------------------------------ Aufbereitung


def _group_offers(points: Sequence[PricePoint]) -> list[Offer]:
    grouped: dict[tuple[str, str, str | None], list[PricePoint]] = {}
    for point in points:
        grouped.setdefault((point.source, point.variant, point.condition), []).append(point)
    offers = [
        Offer(
            source=source,
            variant=variant,
            condition=condition,
            currency=group[0].currency,
            kind="verified" if source in VERIFIED_SOURCES else "external",
            updated_at=max(p.source_updated_at for p in group),
            url=next((p.source_url for p in group if p.source_url), None),
            metrics={p.metric: p.value for p in group},
        )
        for (source, variant, condition), group in grouped.items()
    ]
    source_order = {CARDMARKET: 0, TCGPLAYER: 1}
    variant_order = {"normal": 0, "reverse": 1, "holo": 2}
    offers.sort(
        key=lambda o: (
            source_order.get(o.source, 2),
            o.source,
            variant_order.get(o.variant, 9),
            o.variant,
            CONDITIONS.index(o.condition) if o.condition in CONDITIONS else -1,
        )
    )
    return offers


def nm_basis(metrics: dict[str, Decimal]) -> tuple[str, Decimal] | None:
    """Near-Mint-Basis: Median aus Trend, Ø 7 und Ø 30 Tagen (soweit vorhanden).

    Beispiel Glurak Grundset: Trend 58,10 · Ø7 423,40 · Ø30 765,81 → 423,40 statt 58,10.
    Gibt (Beschreibung, Wert) zurück, z. B. ``("median(trend, avg7, avg30)", 423.40)``.
    """
    used = [m for m in NM_MEDIAN_METRICS if m in metrics]
    if not used:
        if NM_FALLBACK_METRIC in metrics:
            return NM_FALLBACK_METRIC, metrics[NM_FALLBACK_METRIC]
        return None
    if len(used) == 1:
        return used[0], metrics[used[0]]
    value = Decimal(statistics.median(metrics[m] for m in used)).quantize(CENT)
    return f"median({', '.join(used)})", value


def _basis(reference: Offer) -> tuple[str, Decimal] | None:
    """NM-Basis einer Referenz: Cardmarket-Median bzw. umgerechneter US-Preis."""
    if reference.source == PRICECHARTING:
        return "US-Preis PriceCharting (umgerechnet)", reference.metrics[RAW_METRIC]
    return nm_basis(reference.metrics)


def _condition_prices(
    offers: Sequence[Offer], factors: dict[str, Decimal], language_factor: Decimal
) -> list[ConditionPrice]:
    """Zustandspreise je Variante: externer Beleg vor Schätzung.

    Geschätzt wird nur für Varianten mit Cardmarket-Referenz; belegte Zustandspreise einer
    externen Quelle (z. B. ausgelesene Cardmarket-Angebote) zählen auch ohne Referenz.
    """
    result: list[ConditionPrice] = []
    references = {o.variant: o for o in offers if o.source == CARDMARKET and o.condition is None}
    # Ohne Cardmarket: US-Preis von PriceCharting (umgerechnet) als Basis der Schätzung.
    for offer in offers:
        if (
            offer.source == PRICECHARTING
            and offer.variant == RAW_VARIANT
            and RAW_METRIC in offer.metrics
            and RAW_VARIANT not in references
        ):
            references[RAW_VARIANT] = offer
    external_variants = [o.variant for o in offers if o.kind == "external" and o.condition]
    variants = list(dict.fromkeys([*references, *external_variants]))
    for variant in variants:
        reference = references.get(variant)
        basis = _basis(reference) if reference is not None else None
        for condition in CONDITIONS:
            external = [
                o
                for o in offers
                if o.kind == "external"
                and o.variant == variant
                and o.condition == condition
                and (reference is None or o.currency == reference.currency)
                and o.metrics
            ]
            if external:
                best = min(external, key=lambda o: min(o.metrics.values()))
                result.append(
                    ConditionPrice(
                        variant=variant,
                        condition=condition,
                        value=min(best.metrics.values()),
                        currency=best.currency,
                        kind="external",
                        source=best.source,
                        updated_at=best.updated_at,
                        url=best.url,
                    )
                )
            elif reference is not None and basis is not None:
                basis_label, basis_value = basis
                factor = factors[condition]
                result.append(
                    ConditionPrice(
                        variant=variant,
                        condition=condition,
                        value=(basis_value * factor * language_factor).quantize(CENT),
                        currency=reference.currency,
                        kind="estimated",
                        source=reference.source,
                        updated_at=reference.updated_at,
                        url=reference.url,
                        basis_metric=basis_label,
                        basis_value=basis_value,
                        factor=factor,
                        language_factor=language_factor,
                    )
                )
    return result


# ------------------------------------------------------------- Tägliche Runde


async def tracked_card_ids(
    session: AsyncSession, settings: Settings, now: datetime
) -> list[uuid.UUID]:
    """Karten für die tägliche Aktualisierung: Karten aus Sammlungen (auch Slabs – deren
    Notenpreise kommen von PriceCharting, das seine eigene Gültigkeit hat), Karten auf
    Merklisten, Karten mit aktivem Preisalarm und in den letzten
    ``price_tracking_view_days`` Tagen angesehene Karten."""
    since = now - timedelta(days=settings.price_tracking_view_days)
    viewed = select(PriceCheck.card_id).where(PriceCheck.last_viewed_at >= since)
    collected = select(CollectionItem.card_id).where(CollectionItem.card_id.is_not(None))
    wished = select(WishlistItem.card_id).where(WishlistItem.card_id.is_not(None))
    alerted = select(PriceAlert.card_id).where(PriceAlert.card_id.is_not(None), PriceAlert.active)
    result = await session.scalars(union(viewed, collected, wished, alerted))
    return sorted(card_id for card_id in result.all() if card_id is not None)
