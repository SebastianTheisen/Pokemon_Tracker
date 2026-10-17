"""Von Nutzern angelegte Katalogeinträge: fehlende Karten und versiegelte Produkte.

Entscheidung 17.10.2026: für **alle** Nutzer sichtbar; bearbeiten/löschen nur Admins.
Selbst angelegte Karten tragen ``source = user`` und werden vom TCGdex-Import nie berührt.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, CardSet, CardSource, Product, ProductKind, User
from app.services.audit import record_audit
from app.services.catalog_numbers import normalize_number
from app.services.errors import ConflictError, InvalidInputError, NotFoundError


@dataclass
class NewCard:
    name: str
    number: str
    language: str
    set_id: uuid.UUID | None = None
    set_name: str | None = None
    image_url: str | None = None


async def _resolve_set(
    session: AsyncSession, *, set_id: uuid.UUID | None, set_name: str | None, language: str
) -> CardSet:
    """Vorhandenes Set (per ID) oder ein eigenes Set (per Name, je Sprache einmalig)."""
    if set_id is not None:
        card_set = await session.get(CardSet, set_id)
        if card_set is None:
            raise NotFoundError("Set nicht gefunden.")
        if card_set.language != language:
            raise InvalidInputError("Set und Karte müssen dieselbe Sprache haben.")
        return card_set
    if not set_name:
        raise InvalidInputError("Set auswählen oder einen Set-Namen angeben.")
    existing = await session.scalar(
        select(CardSet).where(
            CardSet.language == language,
            func.lower(CardSet.name) == set_name.casefold(),
            CardSet.external_id.like("user-%"),
        )
    )
    if existing is not None:
        return existing
    card_set = CardSet(
        external_id=f"user-{uuid.uuid4().hex[:12]}", language=language, name=set_name
    )
    session.add(card_set)
    await session.flush()
    return card_set


async def create_card(session: AsyncSession, author: User, data: NewCard) -> Card:
    card_set = await _resolve_set(
        session, set_id=data.set_id, set_name=data.set_name, language=data.language
    )
    number_norm = normalize_number(data.number)
    duplicate = await session.scalar(
        select(Card.id).where(
            Card.set_id == card_set.id,
            Card.number_norm == number_norm,
            Card.language == data.language,
            func.lower(Card.name) == data.name.casefold(),
        )
    )
    if duplicate:
        raise ConflictError("Diese Karte gibt es in dem Set bereits.", code="card_exists")
    card = Card(
        language=data.language,
        set_id=card_set.id,
        number=data.number,
        number_norm=number_norm,
        name=data.name,
        image_url=data.image_url,
        source=CardSource.USER,
        created_by_id=author.id,
    )
    session.add(card)
    await session.flush()
    await session.refresh(card, ["card_set"])
    record_audit(
        session,
        action="catalog.card_created",
        actor_id=author.id,
        details={"card_id": str(card.id)},
    )
    return card


async def _user_card(session: AsyncSession, card_id: uuid.UUID) -> Card:
    card = await session.get(Card, card_id)
    if card is None:
        raise NotFoundError("Karte nicht gefunden.")
    if card.source is not CardSource.USER:
        raise InvalidInputError("Nur selbst angelegte Karten können bearbeitet werden.")
    return card


async def update_card(
    session: AsyncSession, admin: User, card_id: uuid.UUID, changes: dict[str, object]
) -> Card:
    card = await _user_card(session, card_id)
    for name in ("name", "image_url"):
        if name in changes:
            setattr(card, name, changes[name])
    if "number" in changes and isinstance(changes["number"], str):
        card.number = changes["number"]
        card.number_norm = normalize_number(card.number)
    card.updated_by_id = admin.id
    record_audit(
        session, action="admin.card_updated", actor_id=admin.id, details={"card_id": str(card.id)}
    )
    await session.flush()
    return card


async def delete_card(session: AsyncSession, admin: User, card_id: uuid.UUID) -> None:
    card = await _user_card(session, card_id)
    try:
        async with session.begin_nested():
            await session.delete(card)
            await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "Die Karte liegt noch in Sammlungen und kann nicht gelöscht werden.", code="in_use"
        ) from exc
    record_audit(
        session, action="admin.card_deleted", actor_id=admin.id, details={"card_id": str(card_id)}
    )


# ------------------------------------------------------------------ Produkte


@dataclass
class NewProduct:
    kind: ProductKind
    language: str
    name: str
    set_id: uuid.UUID | None = None
    image_url: str | None = None


async def create_product(session: AsyncSession, author: User, data: NewProduct) -> Product:
    if data.set_id is not None and await session.get(CardSet, data.set_id) is None:
        raise NotFoundError("Set nicht gefunden.")
    duplicate = await session.scalar(
        select(Product.id).where(
            Product.kind == data.kind,
            Product.language == data.language,
            func.lower(Product.name) == data.name.casefold(),
        )
    )
    if duplicate:
        raise ConflictError("Dieses Produkt gibt es bereits.", code="product_exists")
    product = Product(
        kind=data.kind,
        language=data.language,
        name=data.name,
        set_id=data.set_id,
        image_url=data.image_url,
        created_by_id=author.id,
    )
    session.add(product)
    await session.flush()
    await session.refresh(product, ["card_set"])
    return product


async def search_products(
    session: AsyncSession, query: str, *, language: str | None = None, limit: int = 30
) -> Sequence[Product]:
    statement = select(Product).order_by(Product.name).limit(limit)
    if query.strip():
        statement = statement.where(func.lower(Product.name).like(f"%{query.strip().casefold()}%"))
    if language is not None:
        statement = statement.where(Product.language == language)
    return (await session.scalars(statement)).unique().all()


async def update_product(
    session: AsyncSession, admin: User, product_id: uuid.UUID, changes: dict[str, object]
) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Produkt nicht gefunden.")
    for name in ("name", "kind", "image_url", "set_id"):
        if name in changes:
            setattr(product, name, changes[name])
    record_audit(
        session,
        action="admin.product_updated",
        actor_id=admin.id,
        details={"product_id": str(product.id)},
    )
    await session.flush()
    return product


async def delete_product(session: AsyncSession, admin: User, product_id: uuid.UUID) -> None:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Produkt nicht gefunden.")
    try:
        async with session.begin_nested():
            await session.delete(product)
            await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "Das Produkt liegt noch in Sammlungen und kann nicht gelöscht werden.", code="in_use"
        ) from exc
    record_audit(
        session,
        action="admin.product_deleted",
        actor_id=admin.id,
        details={"product_id": str(product_id)},
    )
