"""Preise je Karte, Preisverlauf, persönliche Einstellungen, Status der Preisquellen."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, CurrentUser, PriceServiceDep, SessionDep
from app.models import UserSettings
from app.schemas.pricing import (
    CardmarketConditionOut,
    CardmarketOffersIn,
    CardmarketOffersOut,
    CardPricesOut,
    EbayGroupOut,
    EbaySaleOut,
    EbaySoldIn,
    EbaySoldOut,
    PriceHistoryOut,
    PriceSourceOut,
    PriceTargetIn,
    PriceTargetOut,
    UserSettingsOut,
    UserSettingsUpdate,
)
from app.services import catalog_search
from app.services.cardmarket_offers import (
    OfferRow,
    evaluate_offers,
    remember_product_page,
    save_offers,
)
from app.services.ebay_sold import SoldRow, evaluate_sold, save_sold
from app.services.user_settings import (
    effective_factors,
    effective_language_factors,
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


@router.post("/cards/{card_id}/cardmarket-offers")
async def cardmarket_offers(
    card_id: uuid.UUID, body: CardmarketOffersIn, session: SessionDep, user: CurrentUser
) -> CardmarketOffersOut:
    """Selbst ausgelesene Cardmarket-Angebote auswerten (Vorschau) und mit ``save`` speichern.

    Die Angebote stammen aus dem Browser des Nutzers (Lesezeichen); der Server ruft
    Cardmarket nicht ab. Gespeichert wird je Variante und Zustand das günstigste Angebot
    und der Durchschnitt der drei günstigsten – mit Datum und Link auf die Seite.
    """
    card = await catalog_search.get_card(session, card_id)
    result = evaluate_offers(
        card,
        body.page_url,
        [OfferRow(row.condition, row.price, tuple(row.labels)) for row in body.rows],
    )
    if body.save:
        await save_offers(session, card, result)
        # Seite merken: korrigiert falsche Cardmarket-Zuordnungen von TCGdex.
        if body.remember_page and result.accepted:
            await remember_product_page(session, card, result.page_url, user.id)
    return CardmarketOffersOut(
        card_id=card.id,
        card_language=result.card_language,
        page_url=result.page_url,
        accepted=result.accepted,
        skipped=result.skipped,
        prices=[CardmarketConditionOut(**price.__dict__) for price in result.prices],
        warnings=result.warnings,
        saved=result.saved,
    )


@router.post("/cards/{card_id}/ebay-sold")
async def ebay_sold(
    card_id: uuid.UUID, body: EbaySoldIn, session: SessionDep, _user: CurrentUser
) -> EbaySoldOut:
    """Selbst ausgelesene eBay-Verkäufe auswerten (Vorschau) und mit ``save`` speichern.

    Ohne ``selected`` werden die Verkäufe gezählt, die sicher zur Karte passen (Nummer im
    Titel, kein Konvolut, Euro, nicht älter als vier Monate). Gegradete Verkäufe bilden
    eigene Gruppen („PSA 10“) und bewerten gegradete Sammlungspositionen.
    """
    card = await catalog_search.get_card(session, card_id)
    result = evaluate_sold(
        card,
        body.page_url,
        [SoldRow(row.title, row.price, row.sold, row.url) for row in body.rows],
        selected=body.selected,
    )
    if body.save:
        await save_sold(session, card, result)
    return EbaySoldOut(
        card_id=card.id,
        page_url=result.page_url,
        sales=[
            EbaySaleOut(
                index=sale.index,
                title=sale.title,
                price=sale.price,
                sold_on=sale.sold_on,
                group=sale.group,
                url=sale.url,
                issues=list(sale.issues),
                suggested=sale.suggested,
            )
            for sale in result.sales
        ],
        groups=[EbayGroupOut(**group.__dict__) for group in result.groups],
        warnings=result.warnings,
        saved=result.saved,
    )


PRICE_TARGET_MAX_AGE = timedelta(hours=2)


@router.put("/me/price-target", tags=["me"])
async def set_price_target(
    body: PriceTargetIn, session: SessionDep, user: CurrentUser
) -> PriceTargetOut:
    """Merkt die Karte, für die gerade „Preis holen“ geöffnet wurde (für das Lesezeichen)."""
    card = await catalog_search.get_card(session, body.card_id)
    settings = await session.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id, condition_factors={}, language_factors={})
        session.add(settings)
    settings.price_target_card_id = card.id
    settings.price_target_at = datetime.now(UTC)
    return PriceTargetOut(card_id=card.id)


@router.get("/me/price-target", tags=["me"])
async def get_price_target(session: SessionDep, user: CurrentUser) -> PriceTargetOut:
    settings = await session.get(UserSettings, user.id)
    if (
        settings is None
        or settings.price_target_at is None
        or datetime.now(UTC) - settings.price_target_at > PRICE_TARGET_MAX_AGE
    ):
        return PriceTargetOut(card_id=None)
    return PriceTargetOut(card_id=settings.price_target_card_id)


@router.get("/me/settings", tags=["me"])
async def read_settings(session: SessionDep, user: CurrentUser) -> UserSettingsOut:
    settings = await get_user_settings(session, user)
    return UserSettingsOut(
        condition_factors=effective_factors(settings),
        custom_condition_factors=sorted(settings.condition_factors) if settings else [],
        language_factors=effective_language_factors(settings),
        custom_language_factors=sorted(settings.language_factors or {}) if settings else [],
        default_language=settings.default_language if settings else None,
    )


@router.patch("/me/settings", tags=["me"])
async def change_settings(
    body: UserSettingsUpdate, session: SessionDep, user: CurrentUser
) -> UserSettingsOut:
    """Eigene Zustandsfaktoren (relativ zu Near Mint), Sprachfaktoren und Standardsprache."""
    await update_user_settings(
        session,
        user,
        condition_factors=body.condition_factors,
        reset_condition_factors=body.reset_condition_factors,
        language_factors=body.language_factors,
        reset_language_factors=body.reset_language_factors,
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
