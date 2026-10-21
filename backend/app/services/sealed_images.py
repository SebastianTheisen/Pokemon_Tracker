"""Bilder für versiegelte Produkte aus dem TCGplayer-Katalog (tcgcsv.com, kostenlos).

Cardmarket liefert keine Bilder (Spike ``docs/phase5/sealed_images.md``). tcgcsv.com spiegelt
täglich den TCGplayer-Katalog – für Pokémon (Kategorie 3) und Pokémon Japan (85) mit Bild je
Produkt. Gespeichert wird nur die Bildadresse (Bild bleibt auf dem TCGplayer-Server); die
Bilder zeigen die englische bzw. japanische Verpackung.

Zuordnung über den Namen, aber unscharf – die Kataloge benennen anders:

* Wörter statt Text, Satzzeichen und Füllwörter weg, Mehrzahl = Einzahl („Tins“ = „Tin“),
  Kürzel der Serien-Epochen („XY“, „BW“, „EX“ am Anfang …) zählen nicht – mal stehen sie da,
  mal nicht,
* gleiche Bedeutung gleich schreiben: „Booster Box“ = „Display“, „Booster Pack“ = „Booster“,
  „Elite Trainer Box“ = „ETB“ …,
* seltene Wörter zählen mehr als häufige (gewichtete Jaccard-Ähnlichkeit, Gewicht nach
  Seltenheit im TCGplayer-Katalog): „Deoxys“ entscheidet, „Booster“ kaum,
* TCGplayer ergänzt gern in Klammern („Theme Deck [Salamence]“); Klammerwörter, die bei
  Cardmarket fehlen, zählen deshalb nur zu :data:`BRACKET_FACTOR` gegen den Treffer,
* die Produktart muss übereinstimmen (ein Display bekommt nie das Bild eines Boosters); nur
  wenn eine Seite keine Art erkennen lässt („Battle Academy“), reicht ein fast gleicher Name,
* „Code Card“-Produkte (digitale Codes) kommen nie in Frage,
* asiatische Cardmarket-Ausgaben suchen zuerst im japanischen Katalog,
* knapp zweideutige Treffer werden verworfen (lieber kein Bild als ein falsches).
"""

from __future__ import annotations

import asyncio
import math
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
MIN_SIMILARITY = 0.72
MIN_SIMILARITY_ANY_KIND = 0.9  # Art auf einer Seite unbekannt → Name muss fast gleich sein
MIN_LEAD = 0.05  # Vorsprung vor dem Zweitbesten, sonst zweideutig
BRACKET_FACTOR = 0.25  # Gewicht von TCGplayer-Klammerwörtern, die Cardmarket nicht nennt
CONCURRENCY = 4
# „Unlimited Edition“ ist die normale Ausgabe, „1st Edition“ bleibt über „1st“ unterscheidbar.
_STOPWORDS = frozenset(
    {
        "pokemon",
        "tcg",
        "the",
        "and",
        "of",
        "x",
        "en",
        "english",
        "exclusive",
        "unlimited",
        "edition",
        "s",  # Rest von „Collector's“
        # Kürzel der Serien-Epochen („XY BREAKthrough“ = „BREAKthrough“); „EX“ nur am Anfang
        # (_ERA_PREFIX), sonst ist „Reshiram ex Box“ ein anderes Produkt als „Reshiram Box“.
        "xy",
        "bw",
        "sm",
        "swsh",
        "dp",
        "hgss",
    }
)
_SINGULAR = {
    "tins": "tin",
    "decks": "deck",
    "boosters": "booster",
    "packs": "pack",
    "boxes": "box",
    "bundles": "bundle",
    "blisters": "blister",
    "collections": "collection",
    "coins": "coin",
    "displays": "display",
}
# Einzelwörter nach den Wortgruppen: „POP Series 1 Pack“ = „… Booster“, „EU Version“ = …
_WORDS = {"pack": "booster", "eu": "international"}
_ERA_PREFIX = re.compile(r"^\s*ex\b", re.I)  # „EX Dragon: …“, „EX Trainer Kit“
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_CODE_CARD = re.compile(r"^\s*code card\b", re.I)
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
    text = _ERA_PREFIX.sub(" ", name).casefold().replace("é", "e").replace("&", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = f" {' '.join(_SINGULAR.get(word, word) for word in text.split())} "
    for phrase, replacement in _SYNONYMS:
        text = text.replace(f" {phrase} ", f" {replacement} ")
    return frozenset(_WORDS.get(word, word) for word in text.split() if word not in _STOPWORDS)


def main_tokens(name: str) -> frozenset[str]:
    """Wörter außerhalb von ``[…]`` und ``(…)``."""
    return tokens(_BRACKETS.sub(" ", name))


@dataclass(frozen=True)
class Candidate:
    """Ein bewerteter TCGplayer-Kandidat (für :meth:`Matcher.ranked` und die Analyse)."""

    score: float
    product: TcgProduct
    kind: ProductKind
    same_kind: bool

    @property
    def acceptable(self) -> bool:
        """Ähnlich genug – mit gleicher Art normal, mit unbekannter Art fast gleich."""
        return self.score >= (MIN_SIMILARITY if self.same_kind else MIN_SIMILARITY_ANY_KIND)


def _compatible(first: ProductKind, second: ProductKind) -> bool | None:
    """``True`` gleiche Art, ``False`` unbekannte Art auf einer Seite, ``None`` verschieden."""
    if first == second:
        return True
    if ProductKind.OTHER in (first, second):
        return False
    return None


class Matcher:
    """Index der TCGplayer-Produkte je Sprache (Wort → Produkte) für schnelle Suche."""

    def __init__(self, products: Iterable[TcgProduct]) -> None:
        # je Eintrag: Produkt, alle Wörter, Wörter außerhalb von Klammern, Art
        self._entries: dict[
            str, list[tuple[TcgProduct, frozenset[str], frozenset[str], ProductKind]]
        ] = defaultdict(list)
        self._index: dict[tuple[str, str], list[int]] = defaultdict(list)
        for product in products:
            if _CODE_CARD.search(product.name):
                continue  # digitaler Code mit eigenem Bild, nie die Verpackung
            words = tokens(product.name)
            entries = self._entries[product.language]
            for word in words:
                self._index[(product.language, word)].append(len(entries))
            entries.append(
                (product, words, main_tokens(product.name), kind_for(None, product.name))
            )
        # Gewicht je Wort: selten = wichtig (log(1 + N/df)); unbekannte Wörter wie die seltensten.
        self._weights: dict[str, dict[str, float]] = {}
        self._unknown: dict[str, float] = {}
        for language, entries in self._entries.items():
            frequency = Counter(word for _, words, _, _ in entries for word in words)
            total = len(entries)
            self._weights[language] = {
                word: math.log1p(total / count) for word, count in frequency.items()
            }
            self._unknown[language] = math.log1p(total)

    def _similarity(
        self, language: str, words: frozenset[str], tcg: frozenset[str], tcg_main: frozenset[str]
    ) -> float:
        """Gewichtete Jaccard-Ähnlichkeit; fehlende Klammerwörter zählen gedämpft."""
        weights, unknown = self._weights.get(language, {}), self._unknown.get(language, 1.0)

        def weight(group: frozenset[str]) -> float:
            return sum(weights.get(word, unknown) for word in group)

        shared = weight(words & tcg)
        extra = tcg - words
        union = (
            shared
            + weight(words - tcg)
            + weight(extra & tcg_main)
            + BRACKET_FACTOR * weight(extra - tcg_main)
        )
        return shared / union if union else 0.0

    def ranked(
        self, name: str, kind: ProductKind, language: str, *, limit: int = 3
    ) -> list[Candidate]:
        """Beste Kandidaten einer Sprache (auch andere Art, für die Analyse)."""
        words = tokens(name)
        entries = self._entries.get(language, [])
        found = {i for word in words for i in self._index.get((language, word), [])}
        candidates = [
            Candidate(
                self._similarity(language, words, entries[i][1], entries[i][2]),
                entries[i][0],
                entries[i][3],
                _compatible(kind, entries[i][3]) is True,
            )
            for i in found
        ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[:limit] if limit else candidates

    def best(self, name: str, kind: ProductKind, languages: Sequence[str]) -> TcgProduct | None:
        """Bestes eindeutiges Produkt passender Art – Sprachen in Reihenfolge der Vorliebe."""
        for language in languages:
            scored = [
                candidate
                for candidate in self.ranked(name, kind, language, limit=0)
                if _compatible(kind, candidate.kind) is not None
            ]
            if not scored or not scored[0].acceptable:
                continue
            if len(scored) > 1 and scored[0].score - scored[1].score < MIN_LEAD:
                return None  # zweideutig
            return scored[0].product
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
            # Zuordnung neu bewertet → altes, jetzt verworfenes Bild nicht stehen lassen.
            product.image_url = None
            product.tcgplayer_product_id = None
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
