"""Verkaufte eBay.de-Artikel auf Knopfdruck über Apify – mit Kostenbremse und Zwischenspeicher.

Ablauf (Spike ``docs/phase5/apify_runs_e.md``):

1. Suchbegriff aus der Karte: deutscher Name (bei asiatischen Karten übersetzt), Nummer
   „183/165“ und Sprache („japanese“). Rohkarte: gegradete Verkäufe ausschließen
   (PSA, BGS, CGC …); Slab: Firma und Note anhängen („PSA 10“).
2. Gleiche Suche innerhalb von ``apify_ebay_cache_hours`` → gemerktes Ergebnis, kostenlos.
3. Kostenbremse: Würde der Monatsverbrauch mit diesem Lauf das Budget
   (``apify_monthly_budget_usd``, höchstens das Apify-Limit) überschreiten → kein Lauf.
4. Lauf des Dienstes ``apify_ebay_actor`` (nur **ebay.de**, 90 Tage) mit Kostendeckel.
5. Die Treffer werden zu denselben Rohzeilen wie beim Lesezeichen – Vorschau, Auswahl und
   Speichern laufen danach unverändert über :mod:`app.services.ebay_sold`.

Die Eingabe ist auf ``epicscrapers/ebay-sold-listings-api`` zugeschnitten; die Auswertung
der Treffer versteht auch die Felder anderer Dienste (z. B. ``caffein.dev``).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Card, EbayFetch
from app.providers.apify import ApifyClient, ApifyError, ApifyUsage
from app.services.audit import record_audit
from app.services.card_names import translate_card_name
from app.services.ebay_sold import MAX_ROWS, SoldRow
from app.services.errors import ConflictError, InvalidInputError, UpstreamError

log = structlog.get_logger(__name__)

EBAY_SITE = "ebay.de"
SOLD_WITHIN_DAYS = 90
# Bei Rohkarten gegradete Verkäufe gar nicht erst holen (spart Guthaben, bessere Treffer).
GRADED_WORDS = ("PSA", "BGS", "CGC", "SGC", "TAG", "Beckett")
LANGUAGE_WORDS = {"ja": "japanese", "ko": "korean", "zh-tw": "chinese", "zh-cn": "chinese"}
CENT = Decimal("0.01")

Clock = Callable[[], datetime]
# Doppelt getippt → nur ein bezahlter Lauf je Suche gleichzeitig (ein Prozess „api“).
_locks: dict[str, asyncio.Lock] = {}


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class EbaySearch:
    """Suche auf ebay.de: Begriffe und ausgeschlossene Wörter."""

    keywords: str
    exclude: tuple[str, ...] = ()

    @property
    def query(self) -> str:
        """Wie man es bei eBay eintippen würde (``-PSA`` schließt aus)."""
        return " ".join([self.keywords, *(f"-{word}" for word in self.exclude)])

    @property
    def page_url(self) -> str:
        """Dieselbe Suche zum Nachsehen im Browser (nur verkaufte Artikel)."""
        params = {"_nkw": self.query, "LH_Sold": "1", "LH_Complete": "1"}
        return f"https://www.{EBAY_SITE}/sch/i.html?{urlencode(params)}"


_VARIANT_SUFFIX = re.compile(r"\s*\((?:Parallel|Reprint)\)$")


def build_search(card: Card, grading: str | None) -> EbaySearch:
    """Suchbegriff für eine Karte, z. B. „Glurak ex 183/165“ oder „… PSA 10“."""
    if card.card_set.game == "pokemon":
        translated = translate_card_name(card.name, card.language)
    else:
        translated = card.name_en  # Angebote japanischer One-Piece-Karten: englischer Titel
    # „(Parallel)“ steht in keinem Angebotstitel.
    name = _VARIANT_SUFFIX.sub("", translated or card.name)
    number = card.number.strip()
    official = card.card_set.card_count_official
    if number.isdigit() and official:
        number = f"{number}/{official:0{len(number)}d}"  # Titel schreiben meist „183/165“
    parts = [name, number]
    if language := LANGUAGE_WORDS.get(card.language):
        parts.append(language)
    if grading:
        parts.append(grading.replace(" BL", " Black Label"))
        return EbaySearch(" ".join(parts))
    return EbaySearch(" ".join(parts), GRADED_WORDS)


def _price_text(value: object, currency: object) -> str:
    """Preis wie auf der eBay-Seite („25,51 €“), damit die Auswertung gleich bleibt."""
    try:
        amount = Decimal(str(value).replace(",", ".")).quantize(CENT)
    except ArithmeticError:
        return ""
    code = str(currency or "EUR").upper()
    if code == "EUR":
        return f"{amount:.2f} €".replace(".", ",")
    return f"{amount:.2f} {code}"


def _sold_text(item: dict[str, Any]) -> str:
    text = item.get("soldDateText")
    if isinstance(text, str) and text.strip():
        return text.strip()
    for key in ("soldAt", "endedAt", "soldDate", "sold_date"):
        value = item.get(key)
        if isinstance(value, str) and len(value) >= 10:  # noqa: PLR2004 – „2026-10-18…“
            try:
                return date.fromisoformat(value[:10]).strftime("%d.%m.%Y")
            except ValueError:
                continue
    return ""


def rows_from_items(items: Sequence[dict[str, Any]]) -> list[SoldRow]:
    """Treffer eines Apify-Dienstes → Rohzeilen wie vom Lesezeichen."""
    rows: list[SoldRow] = []
    for item in items:
        title = item.get("title")
        price = next(
            (item[key] for key in ("soldPrice", "price", "totalPrice") if item.get(key)), None
        )
        if not isinstance(title, str) or price is None:
            continue
        currency = item.get("currency") or item.get("soldCurrency") or "EUR"
        rows.append(
            SoldRow(
                title=title.strip()[:300],
                price=_price_text(price, currency),
                sold=_sold_text(item),
                url=str(item.get("url") or "")[:600],
            )
        )
    return rows[:MAX_ROWS]


@dataclass(frozen=True)
class ApifyStatus:
    configured: bool
    used_usd: float | None = None
    limit_usd: float | None = None
    budget_usd: float | None = None
    cycle_end: datetime | None = None

    @property
    def remaining_usd(self) -> float | None:
        if self.used_usd is None or self.budget_usd is None:
            return None
        return max(self.budget_usd - self.used_usd, 0.0)


@dataclass(frozen=True)
class EbayFetchResult:
    search: EbaySearch
    rows: list[SoldRow]
    fetched_at: datetime
    cost_usd: Decimal | None
    cached: bool
    status: ApifyStatus


class EbayAutoService:
    """Verkäufe von ebay.de über Apify holen. Speichert den Abruf (commit) sofort."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        client: ApifyClient | None,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._session = session
        self._settings = settings
        self._client = client
        self._now = clock

    def _budget(self, usage: ApifyUsage) -> float:
        budget = self._settings.apify_monthly_budget_usd
        return min(budget, usage.limit_usd) if usage.limit_usd > 0 else budget

    async def status(self) -> ApifyStatus:
        if self._client is None:
            return ApifyStatus(configured=False)
        try:
            usage = await self._client.usage()
        except ApifyError as exc:
            raise UpstreamError(str(exc)) from exc
        return ApifyStatus(
            configured=True,
            used_usd=usage.used_usd,
            limit_usd=usage.limit_usd,
            budget_usd=self._budget(usage),
            cycle_end=usage.cycle_end,
        )

    async def _cached(self, card: Card, search: EbaySearch) -> EbayFetch | None:
        since = self._now() - timedelta(hours=self._settings.apify_ebay_cache_hours)
        return await self._session.scalar(
            select(EbayFetch)
            .where(
                EbayFetch.card_id == card.id,
                EbayFetch.query == search.query,
                EbayFetch.fetched_at >= since,
            )
            .order_by(EbayFetch.fetched_at.desc())
            .limit(1)
        )

    async def fetch(
        self, card: Card, *, grading: str | None, user_id: uuid.UUID, force: bool = False
    ) -> EbayFetchResult:
        if self._client is None:
            raise InvalidInputError(
                "eBay-Abruf ist nicht eingerichtet (PT_APIFY_TOKEN fehlt) – Lesezeichen nutzen."
            )
        search = build_search(card, grading)
        lock = _locks.setdefault(f"{card.id}|{search.query}", asyncio.Lock())
        async with lock:
            cached = None if force else await self._cached(card, search)
            if cached is not None:
                return EbayFetchResult(
                    search=search,
                    rows=[SoldRow(**row) for row in cached.rows],
                    fetched_at=cached.fetched_at,
                    cost_usd=cached.cost_usd,
                    cached=True,
                    status=ApifyStatus(configured=True),
                )
            status = await self.status()
            used, budget = status.used_usd or 0.0, status.budget_usd or 0.0
            if used + self._settings.apify_max_charge_usd > budget:
                raise ConflictError(
                    f"Monatsbudget für eBay-Abrufe erreicht ({used:.2f} $ von "
                    f"{budget:.2f} $) – bis zum Monatswechsel bitte das Lesezeichen "
                    "nutzen.",
                    code="budget_exhausted",
                )
            try:
                run = await self._client.run_actor(
                    self._settings.apify_ebay_actor,
                    {
                        "keywords": [search.keywords],
                        "excludeKeywords": list(search.exclude),
                        "site": EBAY_SITE,
                        "maxItems": self._settings.apify_ebay_max_items,
                        "days": SOLD_WITHIN_DAYS,
                    },
                    max_charge_usd=self._settings.apify_max_charge_usd,
                    timeout_seconds=self._settings.apify_run_timeout_seconds,
                    max_items=self._settings.apify_ebay_max_items,
                )
            except ApifyError as exc:
                log.warning("ebay_auto.failed", card=str(card.id), error=str(exc))
                raise UpstreamError(f"eBay-Abruf fehlgeschlagen: {exc}") from exc
            rows = rows_from_items(run.items)
            cost = (
                Decimal(str(run.cost_usd)).quantize(Decimal("0.00001"))
                if run.cost_usd is not None
                else None
            )
            fetched = EbayFetch(
                card_id=card.id,
                query=search.query[:300],
                page_url=search.page_url[:500],
                rows=[asdict(row) for row in rows],
                cost_usd=cost,
                requested_by_id=user_id,
                fetched_at=self._now(),
            )
            self._session.add(fetched)
            record_audit(
                self._session,
                action="apify.ebay_fetch",
                actor_id=user_id,
                details={
                    "card_id": str(card.id),
                    "query": search.query,
                    "rows": len(rows),
                    "run_id": run.run_id,
                    "cost_usd": str(cost) if cost is not None else None,
                },
            )
            # Sofort festschreiben: Ein zweiter Tipp soll den bezahlten Abruf wiederfinden.
            await self._session.commit()
            log.info("ebay_auto.fetched", card=str(card.id), rows=len(rows), cost=str(cost))
            return EbayFetchResult(
                search=search,
                rows=rows,
                fetched_at=fetched.fetched_at,
                cost_usd=cost,
                cached=False,
                status=status,
            )
