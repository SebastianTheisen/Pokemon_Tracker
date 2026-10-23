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

**Japanische Vintage-Sets** (1996–2006, :data:`JP_VINTAGE`): Die offizielle Datenbank beginnt
erst 2006, und TCGdex führt diese Sets mit fehlerhaften Namen („奇妙な“, „ノクトウル“) und
ohne Bilder (Spike ``docs/phase5/jp_vintage.md``). Sie kommen deshalb ebenfalls von
PriceCharting – Set-Name und Erscheinungsdatum vom TCGdex-Set, Kartennamen japanisch über die
Pokédex-Nummer („Charizard #6“ → „リザードン“). Die TCGdex-Fassung wird danach entfernt;
Karten, die jemand in der Sammlung hat, bleiben (und werden gemeldet). Der Katalog-Abgleich
überspringt ersetzte Sets (:func:`replaced_tcgdex_sets`).
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
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import (
    Card,
    CardSet,
    CardSource,
    CollectionItem,
    ImageSource,
    PriceCheck,
    PricePoint,
)
from app.providers.apify import ApifyClient, ApifyError
from app.providers.fx import EcbRates
from app.providers.pricing.pricecharting import (
    GRADED_VARIANT,
    PRICECHARTING,
    RAW_METRIC,
    RAW_VARIANT,
)
from app.services.card_names import species_id_by_name, species_name
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

# PriceCharting-Slug → TCGdex-Set, das er ersetzt (``None``: neues Set ohne Gegenstück).
JP_VINTAGE: dict[str, str | None] = {
    "pokemon-japanese-expansion-pack": "PMCG1",
    "pokemon-japanese-jungle": "PMCG2",
    "pokemon-japanese-mystery-of-the-fossils": "PMCG3",
    "pokemon-japanese-rocket-gang": "PMCG4",
    "pokemon-japanese-leaders%27-stadium": "PMCG5",
    "pokemon-japanese-challenge-from-the-darkness": "PMCG6",
    "pokemon-japanese-gold-silver-new-world": "neo1",
    "pokemon-japanese-crossing-the-ruins": "neo2",
    "pokemon-japanese-awakening-legends": "neo3",
    "pokemon-japanese-darkness-and-to-light": "neo4",
    "pokemon-japanese-vs": "VS1",
    "pokemon-japanese-web": "web1",
    "pokemon-japanese-expedition-expansion-pack": "E1",
    "pokemon-japanese-the-town-on-no-map": "E2",
    "pokemon-japanese-wind-from-the-sea": "E3",
    "pokemon-japanese-split-earth": "E4",
    "pokemon-japanese-mysterious-mountains": "E5",
    # Nicht in der Übersicht von PriceCharting – Schreibweise vermutet, fehlt sie, bleibt
    # das TCGdex-Set (der Bericht nennt sie).
    "pokemon-japanese-flight-of-legends": "PCG1",
    "pokemon-japanese-clash-of-the-blue-sky": "PCG2",
    "pokemon-japanese-rocket-gang-strikes-back": "PCG3",
    "pokemon-japanese-golden-sky-silvery-ocean": "PCG4",
    "pokemon-japanese-mirage-forest": "PCG5",
    "pokemon-japanese-holon-research": "PCG6",
    "pokemon-japanese-holon-phantom": "PCG7",
    "pokemon-japanese-miracle-crystal": "PCG8",
    "pokemon-japanese-offense-and-defense-of-the-furthest-ends": "PCG9",
    # Vintage-Sondersets ohne Gegenstück bei TCGdex
    "pokemon-japanese-vending": None,
    "pokemon-japanese-southern-islands": None,
    "pokemon-japanese-neo-premium-file": None,
    "pokemon-japanese-yamabuki-city-gym": None,
    "pokemon-japanese-2002-mcdonald%27s": None,
    "pokemon-japanese-player%27s-club": None,
    "pokemon-japanese-cd-promo": None,
}
# Englische Namenszusätze alter Karten → japanisch („Dark Charizard“ → „わるいリザードン“).
_JP_PREFIXES = (
    ("Dark ", "わるい"),
    ("Light ", "やさしい"),
    ("Shining ", "ひかる"),
    ("Rocket's ", "ロケット団の"),
    ("Brock's ", "タケシの"),
    ("Misty's ", "カスミの"),
    ("Lt. Surge's ", "マチスの"),
    ("Erika's ", "エリカの"),
    ("Koga's ", "キョウの"),
    ("Sabrina's ", "ナツメの"),
    ("Blaine's ", "カツラの"),
    ("Giovanni's ", "サカキの"),
)
_BRACKET = re.compile(r"\s*(\[[^\]]*\])\s*$")

ApifyFactory = Callable[[], ApifyClient]


@dataclass(frozen=True)
class Console:
    slug: str
    language: str

    @property
    def url(self) -> str:
        return CONSOLE_URL + self.slug


@dataclass
class Replacement:
    """Ersetztes TCGdex-Set: entfernte und (wegen Sammlungen) behaltene Karten."""

    slug: str
    tcgdex_id: str
    removed: int = 0
    kept: int = 0
    set_removed: bool = False


@dataclass
class CatalogReport:
    consoles: list[Console] = field(default_factory=list)
    sets: int = 0
    cards: int = 0
    priced: int = 0
    skipped_products: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # Slugs ohne Ergebnis
    replacements: list[Replacement] = field(default_factory=list)


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


def japanese_name(name: str) -> str:
    """„Charizard [No Rarity]“ → „リザードン [No Rarity]“, „Dark Charizard“ → „わるいリザードン“.

    Nur Pokémon-Namen (über die Pokédex-Daten); Trainer und Energien bleiben englisch.
    """
    bracket = _BRACKET.search(name)
    base = name[: bracket.start()] if bracket else name
    prefix = ""
    for english, local in _JP_PREFIXES:
        if base.startswith(english):
            base, prefix = base.removeprefix(english), local
            break
    species_id = species_id_by_name(base)
    local_name = species_name(species_id, "ja") if species_id else None
    if local_name is None:
        return name
    return f"{prefix}{local_name}" + (f" {bracket.group(1)}" if bracket else "")


def replaced_tcgdex_sets() -> frozenset[str]:
    """TCGdex-Sets (Japanisch), die durch PriceCharting-Sets ersetzt werden."""
    return frozenset(set_id for set_id in JP_VINTAGE.values() if set_id)


async def replaced_by_pricecharting(session: AsyncSession, language: str, set_id: str) -> bool:
    """Wurde dieses TCGdex-Set schon durch ein PriceCharting-Set ersetzt (Abgleich überspringen)?"""
    if language != "ja" or set_id not in replaced_tcgdex_sets():
        return False
    slugs = [f"pc-{slug}" for slug, tcgdex_id in JP_VINTAGE.items() if tcgdex_id == set_id]
    found = await session.scalar(
        select(func.count()).where(CardSet.external_id.in_(slugs), CardSet.language == "ja")
    )
    return bool(found)


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
        await self._import(report)
        return report

    async def run_vintage(
        self, *, dry_run: bool = False, limit: int | None = None
    ) -> CatalogReport:
        """Japanische Vintage-Sets (:data:`JP_VINTAGE`) importieren und TCGdex-Fassung ersetzen.

        Probelauf: nichts abrufen, nur je TCGdex-Set zählen, was entfernt bzw. behalten würde.
        """
        report = CatalogReport(consoles=[Console(slug, "ja") for slug in JP_VINTAGE][:limit])
        if dry_run:
            async with self._factory() as session:
                for console in report.consoles:
                    tcgdex_id = JP_VINTAGE[console.slug]
                    if tcgdex_id:
                        report.replacements.append(
                            await _replace_tcgdex_set(
                                session, console.slug, tcgdex_id, dry_run=True
                            )
                        )
            return report
        await self._import(report)
        return report

    async def _import(self, report: CatalogReport) -> None:
        per_euro = (await self._rates.rate("USD")).per_euro
        for start in range(0, len(report.consoles), BATCH):
            batch = report.consoles[start : start + BATCH]
            try:
                collections = await self._fetch(batch, report)
            except ApifyError as exc:
                report.errors.append(f"Apify: {exc}")
                break  # z. B. Budget – nicht weiter versuchen
            languages_by_slug = {console.slug: console.language for console in batch}
            returned: set[str] = set()
            for collection in collections:
                slug = str(collection.get("collectionUrl") or "").rstrip("/").rpartition("/")[2]
                slug = slug.lower()
                language = languages_by_slug.get(slug)
                products = collection.get("products") or []
                if language is None or not products:
                    continue
                returned.add(slug)
                async with self._factory() as session:
                    tcgdex_id = JP_VINTAGE.get(slug) if language == "ja" else None
                    await self._store(
                        session,
                        slug=slug,
                        language=language,
                        collection=collection,
                        per_euro=per_euro,
                        report=report,
                        tcgdex_set=await _tcgdex_set(session, tcgdex_id),
                    )
                    if tcgdex_id:
                        report.replacements.append(
                            await _replace_tcgdex_set(session, slug, tcgdex_id, dry_run=False)
                        )
                    await session.commit()
            report.missing += [c.slug for c in batch if c.slug not in returned]
        log.info(
            "pricecharting_catalog.done",
            consoles=len(report.consoles),
            sets=report.sets,
            cards=report.cards,
            missing=len(report.missing),
            cost=report.cost_usd,
        )

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
        tcgdex_set: CardSet | None = None,
    ) -> None:
        """``tcgdex_set``: das ersetzte TCGdex-Set (liefert Name, Serie, Erscheinungsdatum)."""
        products = [p for p in collection.get("products") or [] if isinstance(p, dict)]
        set_values: dict[str, Any] = {
            "external_id": f"pc-{slug}"[:64],
            "language": language,
            "name": set_name(collection)[:200] or slug,
            "series_name": "PriceCharting",
            "card_count_total": int(collection.get("productCount") or len(products)),
            "synced_at": func.now(),
        }
        if tcgdex_set is not None:
            set_values |= {
                "name": tcgdex_set.name,
                "series_name": tcgdex_set.series_name or "PriceCharting",
                "release_date": tcgdex_set.release_date,
            }
        set_stmt = insert(CardSet).values(set_values)
        set_id = await session.scalar(
            set_stmt.on_conflict_do_update(
                index_elements=[CardSet.external_id, CardSet.language],
                set_={
                    key: set_stmt.excluded[key]
                    for key in (
                        "name",
                        "series_name",
                        "release_date",
                        "card_count_total",
                        "synced_at",
                    )
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
            if language == "ja":
                name = japanese_name(name)
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


async def _tcgdex_set(session: AsyncSession, external_id: str | None) -> CardSet | None:
    if external_id is None:
        return None
    return await session.scalar(
        select(CardSet).where(CardSet.external_id == external_id, CardSet.language == "ja")
    )


async def _replace_tcgdex_set(
    session: AsyncSession, slug: str, external_id: str, *, dry_run: bool
) -> Replacement:
    """Karten des TCGdex-Sets entfernen – außer solchen in Sammlungen; leeres Set löschen."""
    result = Replacement(slug=slug, tcgdex_id=external_id)
    tcgdex = select(CardSet.id).where(CardSet.external_id == external_id, CardSet.language == "ja")
    cards = Card.set_id.in_(tcgdex)
    in_collection = exists().where(CollectionItem.card_id == Card.id)
    result.kept = int(await session.scalar(select(func.count()).where(cards, in_collection)) or 0)
    result.removed = int(
        await session.scalar(select(func.count()).where(cards, ~in_collection)) or 0
    )
    if dry_run:
        return result
    await session.execute(delete(Card).where(cards, ~in_collection))
    if not result.kept:
        deleted = await session.execute(
            delete(CardSet).where(CardSet.id.in_(tcgdex)).returning(CardSet.id)
        )
        result.set_removed = bool(deleted.all())
    return result


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
    for item in report.replacements:
        verb = "würde entfernen" if dry_run else "entfernt"
        kept = f", behalten (in Sammlungen): {item.kept}" if item.kept else ""
        lines.append(f"  TCGdex {item.tcgdex_id}: {verb} {item.removed} Karten{kept}")
    if report.missing:
        lines.append(
            "Bei PriceCharting nicht gefunden (TCGdex-Set bleibt): " + ", ".join(report.missing)
        )
    lines += [f"  ! {error}" for error in report.errors]
    return "\n".join(lines)
