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
from datetime import datetime
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


async def translate_query(session: AsyncSession, query: str) -> str:
    """Deutsche Suche in Cardmarket-Englisch übersetzen (Set-Namen und Produktarten)."""
    text = f" {query.casefold()} "
    for german, english in await _set_names_de_en(session):
        if f" {german} " in text:
            text = text.replace(f" {german} ", f" {english} ")
    for pattern, english in _GERMAN_TERMS:
        text = pattern.sub(english, text)
    # „Booster-Bundle“ = „Booster Bundle“; Wörter werden einzeln im Namen gesucht.
    return " ".join(text.replace("-", " ").split())


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


@dataclass(frozen=True)
class SealedPrice:
    """Wert je Stück eines verknüpften Produkts."""

    value: Decimal
    basis: str
    updated_at: datetime
    url: str


async def search_sealed(
    session: AsyncSession, query: str, *, limit: int = SEARCH_LIMIT
) -> list[SealedOffer]:
    """Versiegelte Produkte, deren Name alle Suchwörter enthält (kurze Namen zuerst).

    Deutsche Begriffe werden übersetzt; findet die Übersetzung nichts, zählt die Eingabe.
    """
    translated = await translate_query(session, query)
    offers = await _search_words(session, translated.split(), limit)
    if offers or translated == " ".join(query.casefold().split()):
        return offers
    return await _search_words(session, query.casefold().split(), limit)


async def _search_words(session: AsyncSession, words: list[str], limit: int) -> list[SealedOffer]:
    if not words:
        return []
    statement = (
        select(CmProduct, CmPrice)
        .outerjoin(CmPrice, CmPrice.id_product == CmProduct.id_product)
        .where(CmProduct.id_category.is_not(None), CmProduct.id_category != SINGLE_CATEGORY)
        .order_by(func.length(CmProduct.name), CmProduct.name)
        .limit(limit)
    )
    for word in words:
        statement = statement.where(func.lower(CmProduct.name).contains(word, autoescape=True))
    offers = []
    for product, price in (await session.execute(statement)).all():
        metrics = _metrics(price.metrics) if price is not None else {}
        basis = nm_basis(metrics)
        offers.append(
            SealedOffer(
                cardmarket_product_id=product.id_product,
                name=product.name,
                category=product.category_name,
                kind=kind_for(product.category_name, product.name),
                trend=metrics.get("trend"),
                low=metrics.get("low"),
                value=basis[1] if basis else None,
                url=product_url(product.id_product),
                image_url=product.image_url,
            )
        )
    return offers


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
