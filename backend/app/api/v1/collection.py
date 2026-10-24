"""Sammlung, Ordner, Merkliste und Dashboard des angemeldeten Nutzers."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep
from app.core.config import CatalogLanguage
from app.providers.pricing import Condition
from app.schemas.catalog import CardOut
from app.schemas.collection import (
    CollectionHistoryOut,
    FolderCreate,
    FolderOut,
    FolderSummaryOut,
    FolderUpdate,
    HistoryPointOut,
    ItemCreate,
    ItemOut,
    ItemPage,
    ItemsBulk,
    ItemsBulkResult,
    ItemUpdate,
    MarkerOut,
    MoversOut,
    ProductOut,
    SetOverviewOut,
    SummaryOut,
    WishlistAdd,
    WishlistEntryOut,
)
from app.services.collection import CollectionService, ItemFilter, ItemInput, SortKey
from app.services.errors import InvalidInputError
from app.services.valuation import ItemKind

router = APIRouter(tags=["collection"])


def get_collection(
    session: SessionDep, user: CurrentUser, prices: PriceServiceDep
) -> CollectionService:
    return CollectionService(session, user, prices)


Collection = Annotated[CollectionService, Depends(get_collection)]


# ---------------------------------------------------------------------- Ordner


@router.get("/folders")
async def list_folders(collection: Collection) -> list[FolderOut]:
    return [FolderOut.model_validate(f) for f in await collection.list_folders()]


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(body: FolderCreate, collection: Collection) -> FolderOut:
    return FolderOut.model_validate(await collection.create_folder(body.name))


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: uuid.UUID, body: FolderUpdate, collection: Collection
) -> FolderOut:
    folder = await collection.update_folder(folder_id, name=body.name, sort_order=body.sort_order)
    return FolderOut.model_validate(folder)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    collection: Collection,
    move_to: Annotated[
        uuid.UUID | None, Query(description="Zielordner für enthaltene Karten")
    ] = None,
) -> None:
    await collection.delete_folder(folder_id, move_to=move_to)


# ------------------------------------------------------------------ Positionen


@router.get("/collection/items")
async def list_items(
    collection: Collection,
    *,
    folder_id: uuid.UUID | None = None,
    kind: ItemKind | None = None,
    set_id: uuid.UUID | None = None,
    language: CatalogLanguage | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    condition: Condition | None = None,
    min_value: Annotated[Decimal | None, Query(ge=0, le=10_000_000)] = None,
    max_value: Annotated[Decimal | None, Query(ge=0, le=10_000_000)] = None,
    with_purchase: bool | None = None,
    sort: SortKey = "added_desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPage:
    """Positionen mit Bewertung. Wertspanne bezieht sich auf den Gesamtwert der Position."""
    item_filter = ItemFilter(
        folder_id=folder_id,
        kind=kind,
        set_id=set_id,
        language=language,
        query=q,
        condition=condition,
        min_value=min_value,
        max_value=max_value,
        with_purchase=with_purchase,
    )
    items, total = await collection.list_items(item_filter, sort=sort, limit=limit, offset=offset)
    return ItemPage(items=[ItemOut.build(i) for i in items], total=total)


@router.post("/collection/items", status_code=status.HTTP_201_CREATED)
async def add_item(body: ItemCreate, collection: Collection) -> ItemOut:
    item = await collection.add_item(ItemInput(**body.model_dump()))
    return await _item_out(collection, item.id)


@router.post("/collection/items/bulk")
async def bulk_items(body: ItemsBulk, collection: Collection) -> ItemsBulkResult:
    """Mehrere Positionen auf einmal verschieben, kopieren (zählt als neu) oder entfernen."""
    if body.action == "delete":
        return ItemsBulkResult(count=await collection.delete_items(body.item_ids))
    if body.folder_id is None:
        raise InvalidInputError("Bitte einen Zielordner wählen.")
    if body.action == "move":
        return ItemsBulkResult(count=await collection.move_items(body.item_ids, body.folder_id))
    copies = await collection.copy_items(body.item_ids, body.folder_id)
    return ItemsBulkResult(count=len(copies))


@router.get("/collection/items/{item_id}")
async def get_item(item_id: uuid.UUID, collection: Collection) -> ItemOut:
    return await _item_out(collection, item_id)


@router.patch("/collection/items/{item_id}")
async def update_item(item_id: uuid.UUID, body: ItemUpdate, collection: Collection) -> ItemOut:
    await collection.update_item(item_id, body.model_dump(exclude_unset=True))
    return await _item_out(collection, item_id)


@router.delete("/collection/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, collection: Collection) -> None:
    await collection.delete_item(item_id)


async def _item_out(collection: CollectionService, item_id: uuid.UUID) -> ItemOut:
    return ItemOut.build(await collection.valued_item(item_id))


# --------------------------------------------------------------- Übersichten


@router.get("/collection/movers")
async def movers(collection: Collection, days: Annotated[int, Query(ge=1, le=90)] = 7) -> MoversOut:
    """Größte Gewinner und Verlierer der eigenen Rohkarten (Cardmarket-Trend, ab 1 € und 5 %)."""
    return MoversOut.build(await collection.price_movers(days=days))


@router.get("/collection/summary")
async def summary(collection: Collection, folder_id: uuid.UUID | None = None) -> SummaryOut:
    return SummaryOut.build(await collection.summary(folder_id))


@router.get("/dashboard")
async def dashboard(collection: Collection, folder_id: uuid.UUID | None = None) -> SummaryOut:
    """Kennzahlen für die Übersicht (Wert, Veränderung, Gewinn, Highlights) – optional je Ordner."""
    return SummaryOut.build(await collection.summary(folder_id))


@router.get("/collection/folders")
async def folder_summaries(collection: Collection) -> list[FolderSummaryOut]:
    """Alle Ordner als Portfolios mit Wert, Kaufpreisen und Gewinn."""
    return [FolderSummaryOut.build(f) for f in await collection.folder_summaries()]


@router.get("/collection/sets")
async def sets_overview(collection: Collection) -> list[SetOverviewOut]:
    return [SetOverviewOut.build(o) for o in await collection.sets_overview()]


@router.get("/collection/history")
async def history(
    collection: Collection,
    days: Annotated[int, Query(ge=1, le=3650)] = 90,
    folder_id: uuid.UUID | None = None,
) -> CollectionHistoryOut:
    """Wertkurve der Sammlung oder eines Ordners (dann ohne Bestandsmarkierungen)."""
    points, markers = await collection.history(days, folder_id)
    return CollectionHistoryOut(
        points=[HistoryPointOut.build(p) for p in points],
        markers=[MarkerOut.build(m) for m in markers],
    )


@router.get("/collection/export.csv", response_class=Response)
async def export_csv(collection: Collection) -> Response:
    """CSV mit allen Positionen (Semikolon, Dezimalkomma, UTF-8 mit BOM für Excel)."""
    return Response(
        content="﻿" + await collection.export_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sammlung.csv"'},
    )


# ------------------------------------------------------------------- Merkliste


@router.get("/wishlist")
async def wishlist(collection: Collection) -> list[WishlistEntryOut]:
    entries, prices = await collection.wishlist()
    result: list[WishlistEntryOut] = []
    for entry in entries:
        card_prices = prices.get(entry.card_id) if entry.card_id else None
        nm = next(
            (
                c
                for c in (card_prices.conditions if card_prices else [])
                if c.variant == "normal" and c.condition == "NM"
            ),
            None,
        )
        result.append(
            WishlistEntryOut(
                id=entry.id,
                created_at=entry.created_at,
                card=CardOut.model_validate(entry.card) if entry.card else None,
                product=ProductOut.model_validate(entry.product) if entry.product else None,
                nm_value=nm.value if nm else None,
                nm_value_kind=nm.kind if nm else None,
            )
        )
    return result


@router.post("/wishlist", status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(body: WishlistAdd, collection: Collection) -> dict[str, uuid.UUID]:
    entry = await collection.add_to_wishlist(card_id=body.card_id, product_id=body.product_id)
    return {"id": entry.id}


@router.delete("/wishlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(entry_id: uuid.UUID, collection: Collection) -> None:
    await collection.remove_from_wishlist(entry_id)
