"""Katalog: Suche, Kartendetails, Sets. Nur für angemeldete Nutzer."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.core.config import CatalogLanguage
from app.schemas.catalog import CardOut, SearchHitOut, SetOut
from app.services import catalog_search

router = APIRouter(tags=["catalog"])


@router.get("/cards/search")
async def search_cards(
    session: SessionDep,
    _user: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=100, description="z. B. „nachtara 215“")],
    language: CatalogLanguage | None = None,
    limit: Annotated[int, Query(ge=1, le=catalog_search.MAX_LIMIT)] = catalog_search.DEFAULT_LIMIT,
) -> list[SearchHitOut]:
    """Suche nach Name (Deutsch/Englisch, auch gemischt, tippfehlertolerant) und/oder Nummer."""
    hits = await catalog_search.search_cards(session, q, language=language, limit=limit)
    return [SearchHitOut(score=hit.score, card=CardOut.model_validate(hit.card)) for hit in hits]


@router.get("/cards/{card_id}")
async def get_card(card_id: uuid.UUID, session: SessionDep, _user: CurrentUser) -> CardOut:
    return CardOut.model_validate(await catalog_search.get_card(session, card_id))


@router.get("/sets")
async def list_sets(
    session: SessionDep, _user: CurrentUser, language: CatalogLanguage | None = None
) -> list[SetOut]:
    return [SetOut.model_validate(s) for s in await catalog_search.list_sets(session, language)]
