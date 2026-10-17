"""Preise je Karte, Preisverlauf, persönliche Einstellungen, Status der Preisquellen."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, CurrentUser, PriceServiceDep, SessionDep
from app.schemas.pricing import (
    CardPricesOut,
    PriceHistoryOut,
    PriceSourceOut,
    UserSettingsOut,
    UserSettingsUpdate,
)
from app.services import catalog_search
from app.services.user_settings import (
    effective_factors,
    get_user_settings,
    update_user_settings,
)

router = APIRouter(tags=["pricing"])


@router.get("/cards/{card_id}/prices")
async def card_prices(
    card_id: uuid.UUID, session: SessionDep, user: CurrentUser, prices: PriceServiceDep
) -> CardPricesOut:
    """Aktuelle Preise; veraltete werden vorher bei den Quellen nachgeladen.

    Ohne belegten Preis ist ``status = "no_data"`` – es wird nichts geschätzt.
    """
    card = await catalog_search.get_card(session, card_id)
    await prices.refresh(card, viewed=True)
    return CardPricesOut.build(await prices.get_prices(card, user))


@router.get("/cards/{card_id}/price-history")
async def card_price_history(
    card_id: uuid.UUID,
    *,
    session: SessionDep,
    _user: CurrentUser,
    prices: PriceServiceDep,
    source: Annotated[str, Query(max_length=64)] = "cardmarket",
    variant: Annotated[str, Query(max_length=32)] = "normal",
    metric: Annotated[str, Query(max_length=32)] = "trend",
    days: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> PriceHistoryOut:
    card = await catalog_search.get_card(session, card_id)
    history = await prices.get_history(
        card, source=source, variant=variant, metric=metric, days=days
    )
    return PriceHistoryOut.build(history)


@router.get("/me/settings", tags=["me"])
async def read_settings(session: SessionDep, user: CurrentUser) -> UserSettingsOut:
    settings = await get_user_settings(session, user)
    return UserSettingsOut(
        condition_factors=effective_factors(settings),
        custom_condition_factors=sorted(settings.condition_factors) if settings else [],
        default_language=settings.default_language if settings else None,
    )


@router.patch("/me/settings", tags=["me"])
async def change_settings(
    body: UserSettingsUpdate, session: SessionDep, user: CurrentUser
) -> UserSettingsOut:
    """Eigene Zustandsfaktoren (relativ zu Near Mint) und Standardsprache setzen."""
    await update_user_settings(
        session,
        user,
        condition_factors=body.condition_factors,
        reset_condition_factors=body.reset_condition_factors,
        default_language=body.default_language,
    )
    return await read_settings(session, user)


@router.get("/admin/price-sources", tags=["admin"])
async def price_sources(_admin: AdminUser, prices: PriceServiceDep) -> list[PriceSourceOut]:
    """Status der Preisquellen (Fehler, Pause) – für den Admin-Bereich."""
    statuses = prices.health.snapshot([p.name for p in prices.providers])
    return [
        PriceSourceOut.build(
            status, kind=provider.kind, paused=prices.health.is_paused(provider.name)
        )
        for provider, status in zip(prices.providers, statuses, strict=True)
    ]
