"""Sammlung aus anderen Apps übernehmen (Collectr-Showcase per Lesezeichen)."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep, SettingsDep
from app.core.config import Settings
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
    clean_portfolio,
)
from app.services.tcgplayer_sets import set_aliases

router = APIRouter(prefix="/import", tags=["import"])
log = structlog.get_logger(__name__)

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


def _remember_preview(
    settings: Settings, user_id: uuid.UUID, body: CollectrPreviewIn, out: CollectrPreviewOut
) -> None:
    """Letzte Vorschau je Nutzer als Datei (Rohzeilen + Zuordnung) – zum Nachsehen mit
    ``deploy/phase8_collectr_last.sh``, wenn eine Zuordnung unklar ist. Fehler stören nicht."""
    by_index = {row.index: row for row in out.rows}
    entries = []
    for index, lines in enumerate(body.rows):
        row = by_index.get(index)
        entries.append(
            {
                "index": index,
                "lines": lines,
                "status": row.status if row else "unlesbar",
                "matches": [
                    {
                        "score": m.score,
                        "set": m.card.card_set.external_id,
                        "number": m.card.number,
                        "name": m.card.name,
                        "language": m.card.language,
                    }
                    for m in (row.matches if row else [])
                ],
            }
        )
    target = settings.scanner_data_dir / "collectr" / f"{user_id}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"portfolio": body.portfolio, "rows": entries}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        log.warning("collectr.preview_not_saved", exc_info=True)


@router.post("/collectr/preview")
async def collectr_preview(
    body: CollectrPreviewIn, importer: Importer, user: CurrentUser, settings: SettingsDep
) -> CollectrPreviewOut:
    """Kacheln des Showcase auswerten und dem Katalog zuordnen (speichert nichts)."""
    body.portfolio = clean_portfolio(body.portfolio)
    results = await importer.preview(body.rows, await set_aliases(settings))
    out = CollectrPreviewOut(
        portfolio=body.portfolio, rows=[CollectrRowOut.build(r) for r in results]
    )
    _remember_preview(settings, user.id, body, out)
    return out


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
