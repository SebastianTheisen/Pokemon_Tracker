"""Eigene Karten und versiegelte Produkte (anlegen: alle; bearbeiten/löschen: Admins)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.config import CatalogLanguage
from app.schemas.catalog import CardOut
from app.schemas.collection import CardCreate, CardUpdate, ProductCreate, ProductOut, ProductUpdate
from app.services import contributions

router = APIRouter(tags=["catalog"])


def _url(value: object) -> str | None:
    return str(value) if value is not None else None


@router.post("/cards", status_code=status.HTTP_201_CREATED)
async def create_card(body: CardCreate, session: SessionDep, user: CurrentUser) -> CardOut:
    """Fehlende Karte anlegen – für alle Nutzer sichtbar."""
    card = await contributions.create_card(
        session,
        user,
        contributions.NewCard(
            name=body.name,
            number=body.number,
            language=body.language,
            set_id=body.set_id,
            set_name=body.set_name,
            image_url=_url(body.image_url),
        ),
    )
    return CardOut.model_validate(card)


@router.patch("/admin/cards/{card_id}", tags=["admin"])
async def update_card(
    card_id: uuid.UUID, body: CardUpdate, session: SessionDep, admin: AdminUser
) -> CardOut:
    changes = body.model_dump(exclude_unset=True)
    if "image_url" in changes:
        changes["image_url"] = _url(changes["image_url"])
    return CardOut.model_validate(await contributions.update_card(session, admin, card_id, changes))


@router.delete("/admin/cards/{card_id}", tags=["admin"], status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: uuid.UUID, session: SessionDep, admin: AdminUser) -> None:
    await contributions.delete_card(session, admin, card_id)


@router.get("/products")
async def search_products(
    session: SessionDep,
    _user: CurrentUser,
    q: Annotated[str, Query(max_length=100)] = "",
    language: CatalogLanguage | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[ProductOut]:
    products = await contributions.search_products(session, q, language=language, limit=limit)
    return [ProductOut.model_validate(p) for p in products]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, session: SessionDep, user: CurrentUser) -> ProductOut:
    product = await contributions.create_product(
        session,
        user,
        contributions.NewProduct(
            kind=body.kind,
            language=body.language,
            name=body.name,
            set_id=body.set_id,
            image_url=_url(body.image_url),
        ),
    )
    return ProductOut.model_validate(product)


@router.patch("/admin/products/{product_id}", tags=["admin"])
async def update_product(
    product_id: uuid.UUID, body: ProductUpdate, session: SessionDep, admin: AdminUser
) -> ProductOut:
    changes = body.model_dump(exclude_unset=True)
    if "image_url" in changes:
        changes["image_url"] = _url(changes["image_url"])
    product = await contributions.update_product(session, admin, product_id, changes)
    return ProductOut.model_validate(product)


@router.delete(
    "/admin/products/{product_id}", tags=["admin"], status_code=status.HTTP_204_NO_CONTENT
)
async def delete_product(product_id: uuid.UUID, session: SessionDep, admin: AdminUser) -> None:
    await contributions.delete_product(session, admin, product_id)
