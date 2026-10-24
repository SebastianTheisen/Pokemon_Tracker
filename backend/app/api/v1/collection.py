"""Sammlung, Ordner, Merkliste und Dashboard des angemeldeten Nutzers."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep
from app.core.config import CatalogLanguage
from app.models import Card
from app.providers.pricing import Condition
from app.schemas.catalog import CardOut, SetOut
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
    SetProgressOut,
    SummaryOut,
    WishlistAdd,
    WishlistBulkAdd,
    WishlistEntryOut,
)
from app.services.collection import CollectionService, ItemFilter, ItemInput, SortKey
from app.services.errors import InvalidInputError
from app.services.pricing import PriceService
from app.services.set_analytics import CardMarket, SetAnalytics, set_analytics
from app.services.set_progress import SetProgressService
from app.services.valuation import ItemKind

router = APIRouter(tags=["collection"])
log = structlog.get_logger(__name__)


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
    folder = await collection.update_folder(
        folder_id, name=body.name, sort_order=body.sort_order, shared=body.shared
    )
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


class OwnedOut(BaseModel):
    card_id: uuid.UUID
    folder_id: uuid.UUID
    folder_name: str
    variant: str
    grading_company: str | None
    grade: str | None
    quantity: int
    condition: str | None
    unit_value: Decimal | None = Field(description="Stückwert in der Sammlung; null = kein Preis")
    value_kind: str
    value_source: str | None
    value_basis: str | None
    item_ids: list[uuid.UUID] = Field(description="Zusammengefasste Positionen (Bearbeiten)")


@router.get("/collection/owned")
async def owned_cards(
    collection: Collection,
    card_id: Annotated[list[uuid.UUID], Query(max_length=100)],
) -> list[OwnedOut]:
    """Bestand je Karte, Ordner und Fassung – „schon in deiner Sammlung“ in Suche und Karte."""
    return [
        OwnedOut.model_validate(entry, from_attributes=True)
        for entry in await collection.owned_cards(card_id)
    ]


async def refresh_card_prices(app_state: Any, card_id: uuid.UUID) -> None:
    """Preise einer Karte gleich holen statt erst in der nächsten Tagesrunde (Slab gespeichert:
    Notenpreise; Karte gemerkt: Cardmarket). Läuft nach der Antwort; veraltete Preise holt
    ``refresh`` nur, wenn nötig. Fehler landen nur im Log."""
    try:
        async with app_state.session_factory() as session:
            card = await session.get(Card, card_id)
            if card is None:
                return
            prices = PriceService(
                session, app_state.settings, app_state.price_providers, app_state.price_health
            )
            await prices.refresh(card)
            await session.commit()
    except Exception:
        log.exception("collection.price_refresh_failed", card=str(card_id))


def _schedule_slab_refresh(request: Request, background: BackgroundTasks, item: ItemOut) -> None:
    if item.kind == "graded" and item.card is not None and item.value.unit_value is None:
        background.add_task(refresh_card_prices, request.app.state, item.card.id)


@router.post("/collection/items", status_code=status.HTTP_201_CREATED)
async def add_item(
    body: ItemCreate, collection: Collection, request: Request, background: BackgroundTasks
) -> ItemOut:
    item = await collection.add_item(ItemInput(**body.model_dump()))
    out = await _item_out(collection, item.id)
    _schedule_slab_refresh(request, background, out)
    return out


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
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    collection: Collection,
    request: Request,
    background: BackgroundTasks,
) -> ItemOut:
    await collection.update_item(item_id, body.model_dump(exclude_unset=True))
    out = await _item_out(collection, item_id)
    _schedule_slab_refresh(request, background, out)
    return out


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


def get_set_progress(
    session: SessionDep, user: CurrentUser, prices: PriceServiceDep
) -> SetProgressService:
    return SetProgressService(session, user, prices)


SetProgressDep = Annotated[SetProgressService, Depends(get_set_progress)]


@router.get("/collection/sets")
async def sets_overview(collection: Collection, progress: SetProgressDep) -> list[SetOverviewOut]:
    """Sets der Sammlung mit Fortschritt (Set und Master-Set inkl. Reverse Holo)."""
    overview = await collection.sets_overview()
    counts = await progress.counts([o.card_set.id for o in overview])
    return [SetOverviewOut.build(o, counts.get(o.card_set.id)) for o in overview]


class MarketCardOut(BaseModel):
    card: CardOut
    trend: Decimal
    avg30: Decimal | None
    change: float | None = Field(description="Trend gegenüber Ø 30 Tage (0.12 = +12 %)")


class SetAnalyticsOut(BaseModel):
    card_set: SetOut
    cards_total: int
    cards_priced: int
    set_value: Decimal
    master_value: Decimal
    change: float | None
    volatility: float | None
    stability: Literal["ruhig", "normal", "bewegt"] | None
    gainers: list[MarketCardOut]
    losers: list[MarketCardOut]
    top_cards: list[MarketCardOut]

    @classmethod
    def build(cls, analytics: SetAnalytics) -> SetAnalyticsOut:
        def card(entry: CardMarket) -> MarketCardOut:
            return MarketCardOut(
                card=CardOut.model_validate(entry.card),
                trend=Decimal(str(entry.trend)).quantize(Decimal("0.01")),
                avg30=Decimal(str(entry.avg30)).quantize(Decimal("0.01")) if entry.avg30 else None,
                change=entry.change,
            )

        return cls(
            card_set=SetOut.model_validate(analytics.card_set),
            cards_total=analytics.cards_total,
            cards_priced=analytics.cards_priced,
            set_value=analytics.set_value,
            master_value=analytics.master_value,
            change=analytics.change,
            volatility=analytics.volatility,
            stability=analytics.stability,
            gainers=[card(c) for c in analytics.gainers],
            losers=[card(c) for c in analytics.losers],
            top_cards=[card(c) for c in analytics.top_cards],
        )


@router.get("/collection/sets/{set_id}/analytics")
async def set_analytics_endpoint(set_id: uuid.UUID, session: SessionDep) -> SetAnalyticsOut:
    """Set-Analyse aus dem Cardmarket-Preisführer: Wert, Veränderung, Stabilität, Bewegungen."""
    return SetAnalyticsOut.build(await set_analytics(session, set_id))


@router.get("/collection/sets/{set_id}")
async def set_progress(set_id: uuid.UUID, progress: SetProgressDep) -> SetProgressOut:
    """Alle Karten eines Sets mit Besitz je Fassung, Merkliste und NM-Preis."""
    return SetProgressOut.build(await progress.progress(set_id))


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
    view = await collection.wishlist()
    result: list[WishlistEntryOut] = []
    for entry in view.entries:
        card_prices = view.prices.get(entry.card_id) if entry.card_id else None
        nm = next(
            (
                c
                for c in (card_prices.conditions if card_prices else [])
                if c.variant == "normal" and c.condition == "NM"
            ),
            None,
        )
        sealed = view.sealed.get(entry.product_id) if entry.product_id else None
        change = view.changes.get(entry.card_id) if entry.card_id else None
        value, kind = (
            (nm.value, nm.kind) if nm else (sealed.value, "external") if sealed else (None, None)
        )
        result.append(
            WishlistEntryOut(
                id=entry.id,
                created_at=entry.created_at,
                card=CardOut.model_validate(entry.card) if entry.card else None,
                product=ProductOut.model_validate(entry.product) if entry.product else None,
                nm_value=value,
                nm_value_kind=kind,
                change=change.change if change else None,
                change_pct=change.change_pct if change else None,
                change_days=view.days,
            )
        )
    return result


@router.post("/wishlist", status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    body: WishlistAdd, collection: Collection, request: Request, background: BackgroundTasks
) -> dict[str, uuid.UUID]:
    """Merken – und den Preis gleich holen (sonst stünde bis zur Tagesrunde „–“ da)."""
    entry = await collection.add_to_wishlist(card_id=body.card_id, product_id=body.product_id)
    if body.card_id is not None:
        background.add_task(refresh_card_prices, request.app.state, body.card_id)
    return {"id": entry.id}


@router.post("/wishlist/bulk")
async def add_many_to_wishlist(body: WishlistBulkAdd, progress: SetProgressDep) -> ItemsBulkResult:
    """Mehrere Karten auf die Merkliste (z. B. alle fehlenden eines Sets); zählt nur neue."""
    return ItemsBulkResult(count=await progress.add_to_wishlist(body.card_ids))


@router.delete("/wishlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(entry_id: uuid.UUID, collection: Collection) -> None:
    await collection.remove_from_wishlist(entry_id)
