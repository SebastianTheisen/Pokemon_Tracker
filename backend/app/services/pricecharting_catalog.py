"""Koreanische und chinesische Karten samt Bild und Preis aus den PriceCharting-Sets.

Für Korea und Festland-China gibt es keine erreichbare offizielle Datenbank (Quellen-Messung:
pokemoncard.co.kr antwortet dem Server mit 410, pokemon.cn hat keine Kartensuche), und TCGdex
kennt dort kaum Karten. PriceCharting führt diese Sets vollständig. Der Apify-Dienst
``incognito_mode/pricecharting-collection-scraper`` liefert ein ganzes Set in einem Abruf
(Spike ``docs/phase5/apify_runs_j.md``: ~0,01 $ je Set) – jede Karte mit Name und Nummer
(„Captain Pikachu #709“), Bild in 1600 px und Preisen (ungegradet, Grade 9, PSA 10, USD).

* Set-Liste: Übersichtsseite der Pokémon-Sets bei PriceCharting, direkt abgerufen; Sets mit
  „Korean“ bzw. „Chinese“ im Namen.
* Je Set ein Katalog-Set (``pc-<slug>``, englischer Name), je Karte eine Karte
  (``pc-<Produkt-ID>``, englischer Name, Nummer, Bild) mit Herkunft ``pricecharting``.
  Produkte ohne Nummer (Displays, Booster) sind versiegelt und werden übersprungen.
* Preise kommen gleich mit (in Euro umgerechnet) und gelten wie ein PriceCharting-Abruf
  (kein zusätzlicher Einzelabruf je Karte).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Card, CardSet, CardSource, ImageSource, PriceCheck, PricePoint
from app.providers.apify import ApifyClient, ApifyError
from app.providers.fx import EcbRates
from app.providers.pricing.pricecharting import (
    GRADED_VARIANT,
    PRICECHARTING,
    RAW_METRIC,
    RAW_VARIANT,
)
from app.services.catalog_numbers import normalize_number

log = structlog.get_logger(__name__)

LANGUAGES = {"korean": "ko", "chinese": "zh-cn"}
CONSOLE_URL = "https://www.pricecharting.com/console/"
BATCH = 10
MAX_CHARGE_PER_BATCH = 0.2
_CONSOLE = re.compile(r"/console/(pokemon-(korean|chinese)-[a-z0-9&%._-]+)", re.I)
_PRODUCT = re.compile(r"^(?P<name>.+?)\s*#\s*(?P<number>[A-Za-z0-9-]+)\s*$")
CENT = Decimal("0.01")
CHEERIO_SCRAPER = "apify/cheerio-scraper"
# Die Übersicht zeigt nicht alle Sets – Set-Seiten verlinken weitere ihrer Sprache.
EXTRA_LIST_PAGES = (
    "pokemon-korean-promo",
    "pokemon-chinese-promo",
    "pokemon-korean-30th-celebration",
)
LINKS_PAGE_FUNCTION = """async function pageFunction(context) {
    const { $ } = context;
    return { links: $('a[href*="/console/pokemon-"]').map((i, a) => $(a).attr('href')).get() };
}"""

ApifyFactory = Callable[[], ApifyClient]


@dataclass(frozen=True)
class Console:
    slug: str
    language: str

    @property
    def url(self) -> str:
        return CONSOLE_URL + self.slug


@dataclass
class CatalogReport:
    consoles: list[Console] = field(default_factory=list)
    sets: int = 0
    cards: int = 0
    priced: int = 0
    skipped_products: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


def parse_consoles(html: str, languages: Sequence[str]) -> list[Console]:
    """Sets der gewünschten Sprachen aus der Übersichtsseite (Reihenfolge wie dort)."""
    found: dict[str, Console] = {}
    for slug, marker in _CONSOLE.findall(html):
        language = LANGUAGES[marker.lower()]
        if language in languages:
            found.setdefault(slug.lower(), Console(slug.lower(), language))
    return list(found.values())


def parse_product(product: dict[str, Any]) -> tuple[str, str] | None:
    """``("Captain Pikachu", "709")`` aus „Captain Pikachu #709“; ohne Nummer → ``None``."""
    match = _PRODUCT.match(str(product.get("productName") or "").strip())
    if match is None:
        return None
    return match.group("name").strip(), match.group("number")


def metric_name(label: str) -> str | None:
    """Spaltenname von PriceCharting → unsere Kennzahl (``Grade 9.5`` → ``grade_9_5``)."""
    key = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    if key == "ungraded":
        return RAW_METRIC
    if key.startswith(("grade_", "psa_10")):
        return key
    return None


def set_name(collection: dict[str, Any]) -> str:
    name = str(collection.get("collectionName") or "")
    return re.sub(r"^(prices for\s+)?pokemon\s+(korean|chinese)\s+", "", name, flags=re.I).strip()


class PriceChartingCatalog:
    """Import der PriceCharting-Sets (Korea, China) in den Katalog."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        rates: EcbRates,
        apify: ApifyFactory,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._factory = session_factory
        self._settings = settings
        self._rates = rates
        self._apify = apify
        self._transport = transport
        self._now = clock

    async def discover(self, languages: Sequence[str]) -> list[Console]:
        """Set-Liste: direkt abrufen; sperrt PriceCharting den Server (403), über Apify."""
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": self._settings.http_user_agent},
                timeout=60,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                response = await client.get(self._settings.pricecharting_category_url)
                response.raise_for_status()
            return parse_consoles(response.text, languages)
        except httpx.HTTPStatusError as exc:
            log.info("pricecharting_catalog.direct_blocked", status=exc.response.status_code)
        return parse_consoles(await self._links_via_apify(), languages)

    async def _links_via_apify(self) -> str:
        """Links der Übersichtsseite über den Apify-Standarddienst „Cheerio Scraper“."""
        async with self._apify() as client:
            run = await client.run_actor(
                CHEERIO_SCRAPER,
                {
                    "startUrls": [
                        {"url": self._settings.pricecharting_category_url},
                        *({"url": CONSOLE_URL + slug} for slug in EXTRA_LIST_PAGES),
                    ],
                    "pageFunction": LINKS_PAGE_FUNCTION,
                    "proxyConfiguration": {"useApifyProxy": True},
                    "maxRequestsPerCrawl": 1 + len(EXTRA_LIST_PAGES),
                },
                max_charge_usd=0.05,
                timeout_seconds=300,
                max_items=10,
            )
        links = [link for item in run.items for link in item.get("links") or []]
        if not links:
            raise ApifyError("Set-Liste über Apify leer")
        return "\n".join(str(link) for link in links)

    async def run(
        self,
        languages: Sequence[str] = ("ko", "zh-cn"),
        *,
        dry_run: bool = False,
        limit: int | None = None,
        extra: Sequence[str] = (),
    ) -> CatalogReport:
        """``extra``: zusätzliche Set-Slugs (z. B. ``pokemon-korean-electric-breaker``)."""
        report = CatalogReport()
        try:
            found = await self.discover(languages)
            known = {console.slug for console in found}
            found += [
                console
                for console in parse_consoles(
                    "\n".join(f"/console/{slug}" for slug in extra), languages
                )
                if console.slug not in known
            ]
            report.consoles = found[:limit]
        except (httpx.HTTPError, ApifyError) as exc:
            report.errors.append(f"Set-Liste: {type(exc).__name__}: {exc}")
            return report
        if dry_run or not report.consoles:
            return report
        per_euro = (await self._rates.rate("USD")).per_euro
        for start in range(0, len(report.consoles), BATCH):
            batch = report.consoles[start : start + BATCH]
            try:
                collections = await self._fetch(batch, report)
            except ApifyError as exc:
                report.errors.append(f"Apify: {exc}")
                break  # z. B. Budget – nicht weiter versuchen
            languages_by_slug = {console.slug: console.language for console in batch}
            for collection in collections:
                slug = str(collection.get("collectionUrl") or "").rstrip("/").rpartition("/")[2]
                language = languages_by_slug.get(slug.lower())
                if language is None:
                    continue
                async with self._factory() as session:
                    await self._store(
                        session,
                        slug=slug.lower(),
                        language=language,
                        collection=collection,
                        per_euro=per_euro,
                        report=report,
                    )
                    await session.commit()
        log.info(
            "pricecharting_catalog.done",
            consoles=len(report.consoles),
            sets=report.sets,
            cards=report.cards,
            cost=report.cost_usd,
        )
        return report

    async def _fetch(self, batch: Sequence[Console], report: CatalogReport) -> list[dict[str, Any]]:
        async with self._apify() as client:
            usage = await client.usage()
            budget = min(self._settings.apify_monthly_budget_usd, usage.limit_usd or 1e9)
            spendable = budget - self._settings.pricecharting_reserve_usd
            if usage.used_usd + MAX_CHARGE_PER_BATCH > spendable:
                raise ApifyError(
                    f"Budget erreicht ({usage.used_usd:.2f} $ von {budget:.2f} $, "
                    f"Reserve {self._settings.pricecharting_reserve_usd:.2f} $)"
                )
            run = await client.run_actor(
                self._settings.pricecharting_catalog_actor,
                {
                    "collections": [console.url for console in batch],
                    "includeProducts": True,
                    "maxItems": len(batch),
                },
                max_charge_usd=MAX_CHARGE_PER_BATCH,
                timeout_seconds=600,
                max_items=len(batch),
            )
        report.cost_usd += run.cost_usd or 0.0
        return run.items

    async def _store(
        self,
        session: AsyncSession,
        *,
        slug: str,
        language: str,
        collection: dict[str, Any],
        per_euro: Decimal,
        report: CatalogReport,
    ) -> None:
        products = [p for p in collection.get("products") or [] if isinstance(p, dict)]
        set_values = {
            "external_id": f"pc-{slug}"[:64],
            "language": language,
            "name": set_name(collection)[:200] or slug,
            "series_name": "PriceCharting",
            "card_count_total": int(collection.get("productCount") or len(products)),
            "synced_at": func.now(),
        }
        set_stmt = insert(CardSet).values(set_values)
        set_id = await session.scalar(
            set_stmt.on_conflict_do_update(
                index_elements=[CardSet.external_id, CardSet.language],
                set_={
                    key: set_stmt.excluded[key] for key in ("name", "card_count_total", "synced_at")
                },
            ).returning(CardSet.id)
        )
        report.sets += 1
        columns = collection.get("priceColumns") or {}
        now = self._now()
        for product in products:
            parsed = parse_product(product)
            if parsed is None or not product.get("productId"):
                report.skipped_products += 1  # versiegelt oder ohne Nummer
                continue
            name, number = parsed
            image = str(product.get("imageUrl") or "")[:500] or None
            card_stmt = insert(Card).values(
                external_id=f"pc-{product['productId']}",
                language=language,
                set_id=set_id,
                number=number[:32],
                number_norm=normalize_number(number),
                name=name[:200],
                image_url=image,
                image_source=ImageSource.PRICECHARTING if image else None,
                source=CardSource.PRICECHARTING,
            )
            card_id = await session.scalar(
                card_stmt.on_conflict_do_update(
                    index_elements=[Card.external_id, Card.language],
                    index_where=Card.external_id.is_not(None),
                    set_={
                        "name": card_stmt.excluded.name,
                        "number": card_stmt.excluded.number,
                        "number_norm": card_stmt.excluded.number_norm,
                        "image_url": func.coalesce(card_stmt.excluded.image_url, Card.image_url),
                        "updated_at": func.now(),
                    },
                ).returning(Card.id)
            )
            report.cards += 1
            if card_id is not None and await self._store_prices(
                session, card_id, product=product, columns=columns, per_euro=per_euro, now=now
            ):
                report.priced += 1

    async def _store_prices(
        self,
        session: AsyncSession,
        card_id: Any,
        *,
        product: dict[str, Any],
        columns: dict[str, Any],
        per_euro: Decimal,
        now: datetime,
    ) -> bool:
        prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
        rows = []
        for column, value in (prices or {}).items():
            metric = metric_name(str(columns.get(column) or ""))
            if metric is None or isinstance(value, bool) or not isinstance(value, int | float):
                continue
            if value <= 0:
                continue
            rows.append(
                {
                    "card_id": card_id,
                    "source": PRICECHARTING,
                    "variant": RAW_VARIANT if metric == RAW_METRIC else GRADED_VARIANT,
                    "metric": metric,
                    "value": (Decimal(str(value)) / per_euro).quantize(CENT),
                    "currency": "EUR",
                    "source_updated_at": now,
                    "source_url": str(product.get("url") or "")[:500] or None,
                }
            )
        if not rows:
            return False
        await session.execute(
            insert(PricePoint)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_price_points_identity")
        )
        # Wie ein Einzelabruf: PriceCharting gilt für diese Karte als frisch abgefragt.
        check = insert(PriceCheck).values(
            card_id=card_id, source=PRICECHARTING, checked_at=now, ok=True, message=None
        )
        await session.execute(
            check.on_conflict_do_update(
                index_elements=[PriceCheck.card_id, PriceCheck.source],
                set_={"checked_at": now, "ok": True, "message": None},
            )
        )
        return True


def render_report(report: CatalogReport, *, dry_run: bool) -> str:
    lines = [
        f"PriceCharting-Sets: {len(report.consoles)} gefunden "
        f"({', '.join(sorted({c.language for c in report.consoles})) or '–'})",
    ]
    lines += [f"  {console.language:<6} {console.slug}" for console in report.consoles[:200]]
    if not dry_run:
        lines.append(
            f"Importiert: {report.sets} Sets, {report.cards} Karten, davon mit Preis "
            f"{report.priced}; übersprungen (ohne Nummer): {report.skipped_products}; "
            f"Kosten {report.cost_usd:.3f} $"
        )
    lines += [f"  ! {error}" for error in report.errors]
    return "\n".join(lines)
