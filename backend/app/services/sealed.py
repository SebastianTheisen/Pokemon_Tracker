"""Versiegelte Produkte (Booster, Displays, ETBs …) mit Preisen aus dem Cardmarket-Download.

Der offizielle Produktkatalog enthält neben Einzelkarten auch versiegelte Produkte, der
Preisführer ihre Preise (:mod:`app.services.cardmarket_catalog`, täglich). Damit bekommen
versiegelte Sammlungspositionen kostenlos einen belegten Wert:

* Nutzer suchen das Produkt im Cardmarket-Katalog und legen es mit Sprache an. Cardmarket
  benennt englisch („Prismatic Evolutions Elite Trainer Box“); deutsche Suchbegriffe werden
  übersetzt: Produktarten („Top-Trainer-Box“) über :data:`_GERMAN_TERMS`, Set-Namen
  („Prismatische Entwicklungen“) über die deutschen und englischen Sets des Katalogs.
* Wert je Stück = Median aus Trend, Ø 7 und Ø 30 Tagen (wie die Near-Mint-Basis bei Karten).
  Cardmarket führt westliche Sprachen als ein Produkt – der Preis gilt also sprachübergreifend.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import CardSet, CmPrice, CmProduct, Product, ProductKind, User
from app.services.audit import record_audit
from app.services.cardmarket_catalog import SINGLE_CATEGORY, product_url
from app.services.errors import InvalidInputError, NotFoundError
from app.services.pricing import nm_basis

CENT = Decimal("0.01")
SEARCH_LIMIT = 40
KIND_OVERFETCH = 5
MIN_PARTIAL = 4  # kürzere Anfänge passen auf zu viele Set-Namen
MAX_PARTIAL_SETS = 5
# Reihenfolge zählt: „Elite Trainer Box“ ist auch eine „Box“, „Booster Box“ ein Display.
_KIND_RULES: tuple[tuple[re.Pattern[str], ProductKind], ...] = tuple(
    (re.compile(pattern, re.I), kind)
    for pattern, kind in (
        (r"elite trainer", ProductKind.ELITE_TRAINER_BOX),
        (r"display|booster box", ProductKind.DISPLAY),
        (r"\bcase\b", ProductKind.CASE),
        (r"bundle", ProductKind.BOOSTER_BUNDLE),
        (r"blister", ProductKind.BLISTER),
        (r"\btins?\b", ProductKind.TIN),  # Kategorie „Pokémon Tins“
        (r"booster", ProductKind.BOOSTER),
        (r"box|collection|kollektion", ProductKind.COLLECTION_BOX),
    )
)


def kind_for(category_name: str | None, name: str) -> ProductKind:
    """Art des Produkts: zuerst aus dem Namen (genauer, z. B. „Booster Bundle“ in der
    Kategorie „Pokémon Booster“), sonst aus der Cardmarket-Kategorie („Pokémon Display“)."""
    for text in (name, category_name or ""):
        for pattern, kind in _KIND_RULES:
            if pattern.search(text):
                return kind
    return ProductKind.OTHER


# Deutsche Begriffe → Cardmarket-Englisch. Reihenfolge zählt (spezielle zuerst).
_GERMAN_TERMS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.I), english)
    for pattern, english in (
        (r"\btop[- ]?trainer[- ]?box(en)?\b|\bttb\b", "elite trainer box"),
        (r"\bbooster[- ]?displays?\b|\bdisplays?\b", "booster box"),
        (r"\bsammelkoffer\b", "collector chest"),
        (r"\b(?:tin[- ]?)?dosen?\b", "tin"),
        (r"\bthemendecks?\b", "theme deck"),
        (r"\bkampfdecks?\b", "battle deck"),
        (r"\b3er[- ]?blister\b", "3-pack blister"),
        (r"\bspezial[- ]?kollektion(en)?\b", "special collection"),
        (r"\bfiguren[- ]?kollektion(en)?\b", "figure collection"),
        (r"\b(premium|pin|poster)[- ]?kollektion(en)?\b", r"\1 collection"),
        (r"\bkollektion(en)?\b", "collection"),
        (r"\bboosterpack(ung)?s?\b", "booster"),
        (r"\bpok[eé]mon\b", "pok"),  # passt auf „Pokémon“ und „Pokemon“
    )
)


async def _set_names_de_en(session: AsyncSession) -> list[tuple[str, str]]:
    """Deutsche → englische Set-Namen (gleiche TCGdex-ID), längste zuerst."""
    german, english = aliased(CardSet), aliased(CardSet)
    rows = await session.execute(
        select(german.name, english.name)
        .join(english, english.external_id == german.external_id)
        .where(german.language == "de", english.language == "en", german.name != english.name)
    )
    names = {de.casefold(): en.casefold() for de, en in rows if de and en}
    return sorted(names.items(), key=lambda pair: len(pair[0]), reverse=True)


def _translate(query: str, set_names: list[tuple[str, str]]) -> str:
    text = f" {query.casefold()} "
    for german, english in set_names:
        if f" {german} " in text:
            text = text.replace(f" {german} ", f" {english} ")
    for pattern, english in _GERMAN_TERMS:
        text = pattern.sub(english, text)
    # „Booster-Bundle“ = „Booster Bundle“; Wörter werden einzeln im Namen gesucht.
    return " ".join(text.replace("-", " ").split())


async def translate_query(session: AsyncSession, query: str) -> str:
    """Deutsche Suche in Cardmarket-Englisch übersetzen (Set-Namen und Produktarten)."""
    return _translate(query, await _set_names_de_en(session))


def partial_set_queries(
    query: str, set_names: list[tuple[str, str]], *, limit: int = MAX_PARTIAL_SETS
) -> list[str]:
    """Übersetzungen für angefangene deutsche Set-Namen („prismatische“, „karmesin 151“).

    Gesucht wird die längste Folge von Suchwörtern, mit der ein Wort eines deutschen
    Set-Namens beginnt (mindestens :data:`MIN_PARTIAL` Zeichen); jedes passende Set ergibt
    eine eigene Suche mit dem englischen Namen (kurze Namen zuerst – das Hauptset).
    """
    words = query.casefold().split()
    for size in range(len(words), 0, -1):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start : start + size])
            if len(phrase) < MIN_PARTIAL:
                continue
            matches = sorted(
                {english for german, english in set_names if f" {phrase}" in f" {german}"},
                key=lambda name: (len(name), name),
            )
            if matches:
                rest = [*words[:start], "{}", *words[start + size :]]
                return [
                    _translate(" ".join(rest).replace("{}", english), set_names)
                    for english in matches[:limit]
                ]
    return []


def _metrics(raw: dict[str, float]) -> dict[str, Decimal]:
    """Normale Werte des Preisführers (ohne ``-holo``) als Dezimalzahlen."""
    return {
        key: Decimal(str(value)).quantize(CENT)
        for key, value in raw.items()
        if "-" not in key and value
    }


@dataclass(frozen=True)
class SealedOffer:
    """Ein versiegeltes Produkt aus dem Cardmarket-Katalog (Suchtreffer)."""

    cardmarket_product_id: int
    name: str
    category: str | None
    kind: ProductKind
    trend: Decimal | None
    low: Decimal | None
    value: Decimal | None
    url: str
    image_url: str | None = None
    expansion_id: int | None = None
    set_name: str | None = None  # deutscher (sonst englischer) Name des Sets


@dataclass(frozen=True)
class SealedSet:
    """Ein Set mit versiegelten Produkten (zum Durchblättern, neueste zuerst)."""

    expansion_id: int
    name: str
    release_date: date | None
    logo_url: str | None
    products: int
    image_url: str | None  # Bild eines Produkts (Display bevorzugt)


@dataclass(frozen=True)
class SealedPrice:
    """Wert je Stück eines verknüpften Produkts."""

    value: Decimal
    basis: str
    updated_at: datetime
    url: str


async def search_sealed(
    session: AsyncSession,
    query: str = "",
    *,
    limit: int = SEARCH_LIMIT,
    kind: ProductKind | None = None,
    expansion_id: int | None = None,
) -> list[SealedOffer]:
    """Versiegelte Produkte, deren Name alle Suchwörter enthält (kurze Namen zuerst).

    Deutsche Begriffe werden übersetzt; angefangene deutsche Set-Namen ergänzt
    (:func:`partial_set_queries`). Findet keine Übersetzung etwas, zählt die Eingabe.
    ``expansion_id`` (Set) und ``kind`` (Produktart) grenzen ein; mit Set darf die Suche leer
    sein – dann kommen alle Produkte des Sets.
    """
    names = await _expansion_names(session)

    async def words(text: str) -> list[SealedOffer]:
        return await _search_words(
            session, text.split(), limit, kind=kind, expansion_id=expansion_id, names=names
        )

    if not query.strip():
        return await words("") if expansion_id is not None else []
    set_names = await _set_names_de_en(session)
    translated = _translate(query, set_names)
    offers = await words(translated)
    if offers:
        return offers
    seen: set[int] = set()
    for alternative in partial_set_queries(query, set_names):
        for offer in await words(alternative):
            if offer.cardmarket_product_id not in seen and len(offers) < limit:
                seen.add(offer.cardmarket_product_id)
                offers.append(offer)
    if offers or translated == " ".join(query.casefold().split()):
        return offers
    return await words(query.casefold())


ExpansionNames = dict[int, tuple[str, date | None, str | None]]


async def _expansion_names(session: AsyncSession) -> ExpansionNames:
    """Cardmarket-Ausgabe → (Set-Name, Erscheinungsdatum, Logo); Deutsch vor Englisch."""
    rows = await session.execute(
        select(
            CardSet.cardmarket_expansion_id,
            CardSet.language,
            CardSet.name,
            CardSet.release_date,
            CardSet.logo_url,
        ).where(CardSet.cardmarket_expansion_id.is_not(None), CardSet.language.in_(("de", "en")))
    )
    names: ExpansionNames = {}
    for expansion_id, language, name, released, logo in rows:
        if expansion_id is None:
            continue
        known = names.get(expansion_id)
        # Name: Deutsch gewinnt; Datum und Logo: was die andere Fassung hat, ergänzt.
        names[expansion_id] = (
            name if known is None or language == "de" else known[0],
            (known[1] if known else None) or released,
            (known[2] if known else None) or logo,
        )
    return names


_IMAGE_PREFERENCE = (
    ProductKind.DISPLAY,
    ProductKind.ELITE_TRAINER_BOX,
    ProductKind.BOOSTER_BUNDLE,
    ProductKind.BOOSTER,
)


async def sealed_sets(session: AsyncSession, *, limit: int = 40) -> list[SealedSet]:
    """Sets mit versiegelten Produkten, neueste zuerst (nur Sets, die wir kennen)."""
    names = await _expansion_names(session)
    if not names:
        return []
    rows = await session.execute(
        select(CmProduct.id_expansion, CmProduct.name, CmProduct.category_name, CmProduct.image_url)
        .where(
            CmProduct.id_category.is_not(None),
            CmProduct.id_category != SINGLE_CATEGORY,
            CmProduct.id_expansion.in_(list(names)),
        )
        .order_by(CmProduct.id_product)
    )
    counts: dict[int, int] = {}
    images: dict[int, tuple[int, str]] = {}  # Ausgabe → (Rang der Produktart, Bild)
    for expansion_id, name, category, image in rows:
        product_kind = kind_for(category, name)
        if product_kind == ProductKind.OTHER:
            continue  # Code-Karten, Zubehör
        counts[expansion_id] = counts.get(expansion_id, 0) + 1
        rank = (
            _IMAGE_PREFERENCE.index(product_kind)
            if product_kind in _IMAGE_PREFERENCE
            else len(_IMAGE_PREFERENCE)
        )
        if image and (expansion_id not in images or rank < images[expansion_id][0]):
            images[expansion_id] = (rank, image)
    sets = [
        SealedSet(
            expansion_id=expansion_id,
            name=names[expansion_id][0],
            release_date=names[expansion_id][1],
            logo_url=names[expansion_id][2],
            products=count,
            image_url=images[expansion_id][1] if expansion_id in images else None,
        )
        for expansion_id, count in counts.items()
    ]
    sets.sort(key=lambda s: (s.release_date or date.min, s.expansion_id), reverse=True)
    return sets[:limit]


async def _search_words(
    session: AsyncSession,
    words: list[str],
    limit: int,
    *,
    kind: ProductKind | None = None,
    expansion_id: int | None = None,
    names: ExpansionNames | None = None,
) -> list[SealedOffer]:
    if not words and expansion_id is None:
        return []
    statement = (
        select(CmProduct, CmPrice)
        .outerjoin(CmPrice, CmPrice.id_product == CmProduct.id_product)
        .where(CmProduct.id_category.is_not(None), CmProduct.id_category != SINGLE_CATEGORY)
        .order_by(func.length(CmProduct.name), CmProduct.name)
        # Die Art kommt aus dem Namen (nicht aus SQL) – mit Filter mehr laden, danach filtern.
        .limit(limit if kind is None else limit * KIND_OVERFETCH)
    )
    if expansion_id is not None:
        statement = statement.where(CmProduct.id_expansion == expansion_id)
    for word in words:
        statement = statement.where(func.lower(CmProduct.name).contains(word, autoescape=True))
    offers = []
    for product, price in (await session.execute(statement)).all():
        product_kind = kind_for(product.category_name, product.name)
        if kind is not None and product_kind != kind:
            continue
        metrics = _metrics(price.metrics) if price is not None else {}
        basis = nm_basis(metrics)
        known = (names or {}).get(product.id_expansion)
        offers.append(
            SealedOffer(
                cardmarket_product_id=product.id_product,
                name=product.name,
                category=product.category_name,
                kind=product_kind,
                trend=metrics.get("trend"),
                low=metrics.get("low"),
                value=basis[1] if basis else None,
                url=product_url(product.id_product),
                image_url=product.image_url,
                expansion_id=product.id_expansion,
                set_name=known[0] if known else None,
            )
        )
    return offers[:limit]


async def sealed_prices(
    session: AsyncSession, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, SealedPrice]:
    """Aktueller Wert je Produkt (nur verknüpfte Produkte mit Preis im Preisführer)."""
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return {}
    rows = await session.execute(
        select(Product.id, Product.cardmarket_product_id, CmPrice)
        .join(CmPrice, CmPrice.id_product == Product.cardmarket_product_id)
        .where(Product.id.in_(ids))
    )
    result: dict[uuid.UUID, SealedPrice] = {}
    for product_id, cardmarket_id, price in rows.all():
        basis = nm_basis(_metrics(price.metrics))
        if basis is None or cardmarket_id is None:
            continue
        label, value = basis
        result[product_id] = SealedPrice(
            value=value,
            basis=f"Cardmarket {label}",
            updated_at=price.updated_at,
            url=product_url(cardmarket_id),
        )
    return result


async def product_from_cardmarket(
    session: AsyncSession, user: User, cardmarket_product_id: int, language: str
) -> Product:
    """Produkt zu einem Cardmarket-Eintrag (und Sprache) – vorhandenes oder neu angelegt.

    Ein gleichnamiges, bisher unverknüpftes Produkt wird verknüpft statt doppelt angelegt.
    """
    source = await session.get(CmProduct, cardmarket_product_id)
    if source is None:
        raise NotFoundError("Produkt nicht im Cardmarket-Katalog.")
    if source.id_category in (None, SINGLE_CATEGORY):
        raise InvalidInputError("Das ist eine Einzelkarte, kein versiegeltes Produkt.")
    existing = await session.scalar(
        select(Product).where(
            Product.language == language,
            (Product.cardmarket_product_id == cardmarket_product_id)
            | (
                Product.cardmarket_product_id.is_(None)
                & (func.lower(Product.name) == source.name.casefold())
            ),
        )
    )
    if existing is not None:
        if existing.cardmarket_product_id is None:
            existing.cardmarket_product_id = cardmarket_product_id
        existing.image_url = existing.image_url or source.image_url
        return existing
    product = Product(
        kind=kind_for(source.category_name, source.name),
        language=language,
        name=source.name[:200],
        image_url=source.image_url,
        cardmarket_product_id=cardmarket_product_id,
        created_by_id=user.id,
    )
    session.add(product)
    await session.flush()
    await session.refresh(product, ["card_set"])
    record_audit(
        session,
        action="product.created_from_cardmarket",
        actor_id=user.id,
        details={"product_id": str(product.id), "cardmarket_product_id": cardmarket_product_id},
    )
    return product
