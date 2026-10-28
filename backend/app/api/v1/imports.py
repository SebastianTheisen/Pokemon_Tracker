"""Sammlung aus anderen Apps übernehmen (Collectr-Showcase per Lesezeichen)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep
from app.models import GradingCompany
from app.providers.pricing import Condition
from app.schemas.catalog import CardOut
from app.schemas.collection import FolderOut, Grade, Variant
from app.services.collection import CollectionService
from app.services.collectr_import import (
    MAX_ROWS,
    CollectrImport,
    ImportItem,
    RowResult,
    RowStatus,
)

router = APIRouter(prefix="/import", tags=["import"])

Line = Annotated[str, StringConstraints(max_length=200)]
FolderName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def get_collectr_import(
    session: SessionDep, user: CurrentUser, prices: PriceServiceDep
) -> CollectrImport:
    return CollectrImport(session, user, CollectionService(session, user, prices))


Importer = Annotated[CollectrImport, Depends(get_collectr_import)]


class CollectrPreviewIn(BaseModel):
    portfolio: Annotated[str, StringConstraints(max_length=80)] | None = None
    rows: Annotated[list[Annotated[list[Line], Field(max_length=30)]], Field(max_length=MAX_ROWS)]


class CollectrMatchOut(BaseModel):
    card: CardOut
    score: float


class CollectrRowOut(BaseModel):
    index: int
    name: str
    set_name: str
    rarity: str | None
    number: str | None
    condition: str | None
    variant: str
    quantity: int
    graded: bool
    japanese: bool
    status: RowStatus
    matches: list[CollectrMatchOut]

    @classmethod
    def build(cls, result: RowResult) -> CollectrRowOut:
        row = result.row
        number = f"{row.number}/{row.total}" if row.number and row.total else row.number
        return cls(
            index=result.index,
            name=row.name,
            set_name=row.set_name,
            rarity=row.rarity,
            number=number,
            condition=row.condition,
            variant=row.variant,
            quantity=row.quantity,
            graded=row.graded,
            japanese=row.japanese,
            status=result.status,
            matches=[
                CollectrMatchOut(card=CardOut.model_validate(m.card), score=m.score)
                for m in result.matches
            ],
        )


class CollectrPreviewOut(BaseModel):
    portfolio: str | None
    rows: list[CollectrRowOut]


class CollectrItemIn(BaseModel):
    card_id: uuid.UUID
    quantity: Annotated[int, Field(ge=1, le=9999)] = 1
    condition: Condition | None = None
    variant: Variant = "normal"
    grading_company: GradingCompany | None = None
    grade: Grade | None = None


class CollectrCommitIn(BaseModel):
    folder_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    items: Annotated[list[CollectrItemIn], Field(max_length=MAX_ROWS)]


class CollectrCommitOut(BaseModel):
    folder: FolderOut
    added: int
    skipped: int


@router.post("/collectr/preview")
async def collectr_preview(body: CollectrPreviewIn, importer: Importer) -> CollectrPreviewOut:
    """Kacheln des Showcase auswerten und dem Katalog zuordnen (speichert nichts)."""
    results = await importer.preview(body.rows)
    return CollectrPreviewOut(
        portfolio=body.portfolio, rows=[CollectrRowOut.build(r) for r in results]
    )


@router.post("/collectr/commit")
async def collectr_commit(body: CollectrCommitIn, importer: Importer) -> CollectrCommitOut:
    """Ausgewählte Karten in den Ordner übernehmen (legt ihn bei Bedarf an)."""
    result = await importer.commit(
        body.folder_name,
        [
            ImportItem(
                card_id=item.card_id,
                quantity=item.quantity,
                condition=item.condition,
                variant=item.variant,
                grading_company=item.grading_company,
                grade=item.grade,
            )
            for item in body.items
        ],
    )
    return CollectrCommitOut(
        folder=FolderOut.model_validate(result.folder),
        added=result.added,
        skipped=result.skipped,
    )
