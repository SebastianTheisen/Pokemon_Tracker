"""Fehlende Kartenbilder von PriceCharting – für Sets, die keine andere Quelle bebildert.

Übrig bleiben nach TCGdex, pokemontcg.io und den offiziellen Datenbanken vor allem
Sondersets (Trainer-Kits, McDonald's, „My First Battle“) und einzelne Karten japanischer
Sets. PriceCharting führt sie mit Bild (1600 px).

1. Sets mit mindestens :data:`MIN_MISSING` Karten ohne Bild (Englisch, Japanisch; deutsche
   Karten übernehmen danach das englische Bild derselben Karte).
2. Passende PriceCharting-Seite über den Namen: Wörter des (englischen) Set-Namens gegen die
   Wörter der Adresse („McDonald's Collection 2023“ ↔ ``pokemon-mcdonalds-2023``), mindestens
   :data:`MIN_SIMILARITY` und eindeutig. Japanische Sets über ihren englischen Namen
   (:mod:`app.services.set_names`) und nur unter ``pokemon-japanese-…``.
3. Je Karte ohne Bild: gleiche Nummer, sonst eindeutiger Name. Teilen sich mehrere unserer
   Sets eine Seite (Trainer-Kit-Hälften mit eigenen Nummern), zählt nur der Name.

Kosten: Set-Liste ~0,005 $, je Set ~0,007 $ (Collection-Scraper wie beim Katalog).
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Card, CardSet, ImageSource
from app.providers.apify import ApifyError
from app.services.card_names import translate_card_name
from app.services.catalog_numbers import normalize_number
from app.services.catalog_sync import fill_image_fallbacks
from app.services.pricecharting_catalog import (
    BATCH,
    Console,
    PriceChartingCatalog,
    parse_product,
)
from app.services.set_names import translated_set_name

log = structlog.get_logger(__name__)

IMAGE_LANGUAGES = ("en", "ja")
MIN_MISSING = 3
MIN_SIMILARITY = 0.6
_SLUG = re.compile(r"/console/(pokemon-[a-z0-9&%._'-]+)", re.I)
_STOPWORDS = frozenset({"pokemon", "the", "of", "and", "collection", "set", "cards"})
_LANGUAGE_WORDS = frozenset({"japanese", "korean", "chinese"})


def words(text: str) -> frozenset[str]:
    """Vergleichswörter: „McDonald's Collection 2023“ → {mcdonalds, 2023}."""
    plain = text.casefold().replace("%27", "").replace("'", "").replace("&", " ")
    return frozenset(w for w in re.split(r"[^a-z0-9]+", plain) if w and w not in _STOPWORDS)


def card_key(name: str) -> str:
    return re.sub(r"[\W_]+", "", re.sub(r"\s*\[.*?\]", "", name).casefold())


def choose_slug(name: str, language: str, slugs: list[str]) -> str | None:
    """Passende PriceCharting-Seite zu einem Set-Namen (eindeutig, sonst ``None``)."""
    wanted = words(name)
    if not wanted:
        return None
    scored: list[tuple[float, str]] = []
    for slug in slugs:
        slug_words = words(slug.replace("-", " "))
        japanese = "japanese" in slug_words
        if (language == "ja") != japanese or (language != "ja" and slug_words & _LANGUAGE_WORDS):
            continue
        slug_words -= _LANGUAGE_WORDS
        if not slug_words:
            continue
        score = len(wanted & slug_words) / len(wanted | slug_words)
        if score >= MIN_SIMILARITY:
            scored.append((score, slug))
    scored.sort(reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


@dataclass
class ImageReport:
    sets_missing: int = 0
    mapping: dict[str, str] = field(default_factory=dict)  # „en/tk-xy-su …“ → Slug
    unmapped: list[str] = field(default_factory=list)
    images_set: int = 0
    fallbacks: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class _Target:
    set_id: uuid.UUID
    label: str
    language: str
    name: str


async def _targets(session: AsyncSession, limit: int | None) -> list[_Target]:
    missing = func.count().filter(Card.image_url.is_(None))
    rows = (
        await session.execute(
            select(CardSet.id, CardSet.external_id, CardSet.language, CardSet.name)
            .join(Card, Card.set_id == CardSet.id)
            .where(CardSet.language.in_(IMAGE_LANGUAGES), ~CardSet.external_id.startswith("pc-"))
            .group_by(CardSet.id)
            .having(missing >= MIN_MISSING)
            .order_by(missing.desc())
        )
    ).all()
    targets = []
    for set_id, external_id, language, name in rows[:limit]:
        english = translated_set_name(external_id, language, name) or name
        targets.append(_Target(set_id, f"{language}/{external_id} {name}", language, english))
    return targets


def _english_card_name(name: str, language: str) -> str:
    if language == "en":
        return name
    return translate_card_name(name, language, target="en") or name


async def _apply_collection(
    session: AsyncSession, target: _Target, collection: dict[str, Any], *, shared: bool
) -> int:
    by_number: dict[str, str] = {}
    by_name: defaultdict[str, list[str]] = defaultdict(list)
    for product in collection.get("products") or []:
        url = str(product.get("imageUrl") or "")[:500] if isinstance(product, dict) else ""
        parsed = parse_product(product) if url else None
        if parsed is None:
            continue
        product_name, number = parsed
        by_number.setdefault(normalize_number(number), url)
        by_name[card_key(product_name)].append(url)
    unique = {key: images[0] for key, images in by_name.items() if len(images) == 1}
    cards = (
        await session.execute(
            select(Card.id, Card.name, Card.number_norm).where(
                Card.set_id == target.set_id, Card.image_url.is_(None)
            )
        )
    ).all()
    updated = 0
    for card_id, name, number_norm in cards:
        image: str | None = None if shared else by_number.get(number_norm)
        image = image or unique.get(card_key(_english_card_name(name, target.language)))
        if image is None:
            continue
        await session.execute(
            update(Card)
            .where(Card.id == card_id, Card.image_url.is_(None))
            .values(image_url=image, image_source=ImageSource.PRICECHARTING, image_language=None)
        )
        updated += 1
    return updated


async def import_pricecharting_images(
    session_factory: async_sessionmaker[AsyncSession],
    catalog: PriceChartingCatalog,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> ImageReport:
    """Bilder für Sets ohne Bilder. Probelauf: nur Set-Liste und Zuordnung (~0,005 $)."""
    report = ImageReport()
    async with session_factory() as session:
        targets = await _targets(session, limit)
    report.sets_missing = len(targets)
    if not targets:
        return report
    try:
        slugs = sorted({s.lower() for s in _SLUG.findall(await catalog.links())})
    except ApifyError as exc:
        report.errors.append(f"Set-Liste: {exc}")
        return report
    chosen: dict[uuid.UUID, str] = {}
    for target in targets:
        slug = choose_slug(target.name, target.language, slugs)
        if slug is None:
            report.unmapped.append(target.label)
            continue
        chosen[target.set_id] = slug
        report.mapping[target.label] = slug
    if dry_run or not chosen:
        return report
    usage = Counter(chosen.values())
    by_slug: defaultdict[str, list[_Target]] = defaultdict(list)
    for target in targets:
        if target.set_id in chosen:
            by_slug[chosen[target.set_id]].append(target)
    unique_slugs = list(by_slug)
    for start in range(0, len(unique_slugs), BATCH):
        batch = [Console(slug, "") for slug in unique_slugs[start : start + BATCH]]
        try:
            collections, cost = await catalog.collections(batch)
        except ApifyError as exc:
            report.errors.append(f"Apify: {exc}")
            break
        report.cost_usd += cost
        async with session_factory() as session:
            for collection in collections:
                slug = str(collection.get("collectionUrl") or "").rstrip("/").rpartition("/")[2]
                for target in by_slug.get(slug.lower(), []):
                    report.images_set += await _apply_collection(
                        session, target, collection, shared=usage[slug.lower()] > 1
                    )
            await session.commit()
    async with session_factory() as session:
        report.fallbacks = await fill_image_fallbacks(session)  # deutsche Karten
        await session.commit()
    log.info(
        "pricecharting_images.done",
        sets=len(chosen),
        images=report.images_set,
        fallbacks=report.fallbacks,
        cost=report.cost_usd,
    )
    return report


def render_image_report(report: ImageReport, *, dry_run: bool) -> str:
    lines = [f"Sets mit fehlenden Bildern: {report.sets_missing}"]
    lines += [f"  {label} → {slug}" for label, slug in report.mapping.items()]
    if report.unmapped:
        lines.append("Ohne passende PriceCharting-Seite: " + "; ".join(report.unmapped[:60]))
    if not dry_run:
        lines.append(
            f"Bilder gesetzt: {report.images_set}, deutsche Ersatzbilder: {report.fallbacks}, "
            f"Kosten {report.cost_usd:.3f} $"
        )
    lines += [f"  ! {error}" for error in report.errors]
    return "\n".join(lines)
