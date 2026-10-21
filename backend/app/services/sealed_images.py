"""Bilder für versiegelte Produkte aus dem TCGplayer-Katalog (tcgcsv.com, kostenlos).

Cardmarket liefert keine Bilder (Spike ``docs/phase5/sealed_images.md``). tcgcsv.com spiegelt
täglich den TCGplayer-Katalog – für Pokémon (Kategorie 3) und Pokémon Japan (85) mit Bild je
Produkt. Gespeichert wird nur die Bildadresse (Bild bleibt auf dem TCGplayer-Server); die
Bilder zeigen die englische bzw. japanische Verpackung.

Zuordnung über den Namen, aber unscharf – die Kataloge benennen anders:

* Wörter statt Text (Jaccard ≥ :data:`MIN_SIMILARITY`), Satzzeichen und Füllwörter weg,
* gleiche Bedeutung gleich schreiben: „Booster Box“ = „Display“, „Booster Pack“ = „Booster“,
  „Elite Trainer Box“ = „ETB“ …,
* die Produktart muss übereinstimmen (ein Display bekommt nie das Bild eines Boosters),
* asiatische Cardmarket-Ausgaben suchen zuerst im japanischen Katalog,
* knapp zweideutige Treffer werden verworfen (lieber kein Bild als ein falsches).
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import CardSet, CmImport, CmProduct, Product, ProductKind
from app.services.cardmarket_catalog import ASIAN_LANGUAGES, SINGLE_CATEGORY
from app.services.sealed import kind_for

log = structlog.get_logger(__name__)

CATEGORIES = {3: "en", 85: "ja"}  # Pokemon, Pokemon Japan
MIN_SIMILARITY = 0.75
MIN_LEAD = 0.05  # Vorsprung vor dem Zweitbesten, sonst zweideutig
CONCURRENCY = 4
_STOPWORDS = frozenset({"pokemon", "tcg", "the", "and", "of", "x", "en", "english"})
# Reihenfolge zählt (längere Begriffe zuerst).
_SYNONYMS = (
    ("elite trainer box", "etb"),
    ("booster display box", "display"),
    ("booster box", "display"),
    ("booster display", "display"),
    ("booster pack", "booster"),
    ("booster bundle", "bundle"),
    ("blister pack", "blister"),
    ("theme deck", "deck"),
    ("collection box", "collection"),
)


@dataclass(frozen=True)
class TcgProduct:
    product_id: int
    name: str
    image_url: str
    language: str


@dataclass
class ImageReport:
    tcg_products: int = 0
    sealed: int = 0
    matched: int = 0
    by_category: Counter[str] = field(default_factory=Counter)
    products_updated: int = 0


def tokens(name: str) -> frozenset[str]:
    """Vergleichsform eines Produktnamens als Wortmenge."""
    text = name.casefold().replace("é", "e").replace("&", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = f" {' '.join(text.split())} "
    for phrase, replacement in _SYNONYMS:
        text = text.replace(f" {phrase} ", f" {replacement} ")
    return frozenset(word for word in text.split() if word not in _STOPWORDS)


def _similarity(first: frozenset[str], second: frozenset[str]) -> float:
    return len(first & second) / len(first | second) if first and second else 0.0


class Matcher:
    """Index der TCGplayer-Produkte je Sprache (Wort → Produkte) für schnelle Suche."""

    def __init__(self, products: Iterable[TcgProduct]) -> None:
        self._entries: dict[str, list[tuple[TcgProduct, frozenset[str], ProductKind]]] = (
            defaultdict(list)
        )
        self._index: dict[tuple[str, str], list[int]] = defaultdict(list)
        for product in products:
            words = tokens(product.name)
            entries = self._entries[product.language]
            for word in words:
                self._index[(product.language, word)].append(len(entries))
            entries.append((product, words, kind_for(None, product.name)))

    def best(self, name: str, kind: ProductKind, languages: Sequence[str]) -> TcgProduct | None:
        """Bestes eindeutiges Produkt gleicher Art – Sprachen in Reihenfolge der Vorliebe."""
        words = tokens(name)
        for language in languages:
            entries = self._entries.get(language, [])
            candidates = {i for word in words for i in self._index.get((language, word), [])}
            scored = sorted(
                (
                    (_similarity(words, entries[i][1]), entries[i][0])
                    for i in candidates
                    if entries[i][2] == kind
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )
            if not scored or scored[0][0] < MIN_SIMILARITY:
                continue
            if len(scored) > 1 and scored[0][0] - scored[1][0] < MIN_LEAD:
                return None  # zweideutig
            return scored[0][1]
        return None


async def download_products(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> list[TcgProduct]:
    """Alle Produkte mit Bild aus den Pokémon-Kategorien (≈ 500 kleine Abrufe)."""
    base = settings.sealed_images_url.rstrip("/")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent},
        timeout=60,
        follow_redirects=True,
        transport=transport,
    ) as client:

        async def results(path: str) -> list[dict[str, Any]]:
            async with semaphore:
                response = await client.get(f"{base}{path}")
                response.raise_for_status()
                data = response.json()
            items = data.get("results", []) if isinstance(data, dict) else data
            return [item for item in items if isinstance(item, dict)]

        products: list[TcgProduct] = []
        for category, language in CATEGORIES.items():
            groups = await results(f"/{category}/groups")
            batches = await asyncio.gather(
                *(results(f"/{category}/{group['groupId']}/products") for group in groups),
                return_exceptions=True,
            )
            for batch in batches:
                if isinstance(batch, BaseException):
                    continue  # eine kaputte Gruppe stoppt den Rest nicht
                products.extend(
                    TcgProduct(
                        product_id=int(item["productId"]),
                        name=str(item.get("name") or ""),
                        image_url=str(item["imageUrl"]),
                        language=language,
                    )
                    for item in batch
                    if item.get("imageUrl") and item.get("productId") and _is_sealed(item)
                )
    return products


def _is_sealed(item: dict[str, Any]) -> bool:
    """Karten haben in ``extendedData`` eine Nummer – Versiegeltes nicht."""
    names = {str(entry.get("name")) for entry in item.get("extendedData") or []}
    return "Number" not in names


async def _asian_expansions(session: AsyncSession) -> set[int]:
    """Cardmarket-Ausgaben, die zu asiatischen Sets gehören (→ zuerst japanischer Katalog)."""
    rows = await session.execute(
        select(CardSet.cardmarket_expansion_id, CardSet.language).where(
            CardSet.cardmarket_expansion_id.is_not(None)
        )
    )
    languages: defaultdict[int, set[str]] = defaultdict(set)
    for expansion_id, language in rows:
        if expansion_id is not None:
            languages[expansion_id].add(language)
    return {e for e, langs in languages.items() if langs <= set(ASIAN_LANGUAGES)}


async def match_sealed_images(session: AsyncSession, products: Sequence[TcgProduct]) -> ImageReport:
    """Bilder den versiegelten Cardmarket-Produkten zuordnen. Commit macht der Aufrufer."""
    report = ImageReport(tcg_products=len(products))
    matcher = Matcher(products)
    asian = await _asian_expansions(session)
    sealed = (
        await session.scalars(
            select(CmProduct).where(
                CmProduct.id_category.is_not(None), CmProduct.id_category != SINGLE_CATEGORY
            )
        )
    ).all()
    report.sealed = len(sealed)
    for product in sealed:
        languages = ("ja", "en") if product.id_expansion in asian else ("en", "ja")
        hit = matcher.best(product.name, kind_for(product.category_name, product.name), languages)
        if hit is None:
            continue
        product.image_url = hit.image_url[:500]
        product.tcgplayer_product_id = hit.product_id
        report.matched += 1
        report.by_category[product.category_name or "?"] += 1
    await session.flush()
    # Eigene Produkte ohne Bild bekommen das Bild ihres Cardmarket-Produkts.
    result = await session.execute(
        update(Product)
        .where(
            Product.image_url.is_(None),
            Product.cardmarket_product_id == CmProduct.id_product,
            CmProduct.image_url.is_not(None),
        )
        .values(image_url=CmProduct.image_url)
        .execution_options(synchronize_session=False)
    )
    report.products_updated = int(getattr(result, "rowcount", 0) or 0)
    log.info(
        "sealed_images.matched",
        tcg=report.tcg_products,
        sealed=report.sealed,
        matched=report.matched,
        products=report.products_updated,
    )
    return report


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def last_image_run(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(CmImport.started_at)).where(CmImport.sealed_images.is_not(None))
    )


async def refresh_sealed_images(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    force: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Clock = _utc_now,
) -> ImageReport | None:
    """Bilder abgleichen, wenn fällig (alle ``sealed_images_interval_days`` Tage) oder ``force``.

    Läuft nach dem Katalog-Import; Fehler werden protokolliert und stören nichts.
    Gibt ``None`` zurück, wenn nichts zu tun war oder es scheiterte.
    """
    interval = settings.sealed_images_interval_days
    async with session_factory() as session:
        last = await last_image_run(session)
        latest_run = await session.scalar(
            select(CmImport.id).where(CmImport.error.is_(None)).order_by(CmImport.id.desc())
        )
    if latest_run is None:
        return None  # ohne Katalog nichts zuzuordnen
    due = force or (interval > 0 and (last is None or clock() - last >= timedelta(days=interval)))
    if not due:
        return None
    try:
        products = await download_products(settings, transport=transport)
        async with session_factory() as session:
            report = await match_sealed_images(session, products)
            await session.execute(
                update(CmImport)
                .where(CmImport.id == latest_run)
                .values(sealed_images=report.matched)
            )
            await session.commit()
    except Exception:  # Bilder sind Beiwerk – nie den Import oder Worker stören
        log.exception("sealed_images.failed")
        return None
    return report
