"""Schemas für Scans, Bestätigungen und eigene Referenzbilder."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.catalog import CardOut
from app.services.scan import BatchItem, BinderOutcome, ScanMatch, ScanOutcome

CONFIDENT_HINT = "Erkannt als {name}"
UNSURE_HINT = "Falsche Karte? Selbst suchen"
NOTHING_HINT = "Keine Karte erkannt – bitte selbst suchen"


class ScanMatchOut(BaseModel):
    card: CardOut
    confidence: float = Field(description="0..1, siehe Begründungen")
    reasons: list[str]
    image_inliers: int | None = Field(description="Bildabgleich (RANSAC-Inlier), ab 50 sicher")

    @classmethod
    def build(cls, match: ScanMatch) -> ScanMatchOut:
        return cls(
            card=CardOut.model_validate(match.card),
            confidence=match.confidence,
            reasons=list(match.reasons),
            image_inliers=match.inliers,
        )


class GradingOut(BaseModel):
    company: str
    grade: str | None


class ScanResultOut(BaseModel):
    scan_id: uuid.UUID
    confident: bool
    hint: str
    best: ScanMatchOut | None
    alternatives: list[ScanMatchOut]
    grading: GradingOut | None = Field(description="Slab erkannt → als gegradet vorschlagen")
    detected: dict[str, Any]
    duration_ms: int
    can_save_reference: bool

    @classmethod
    def build(cls, outcome: ScanOutcome) -> ScanResultOut:
        if outcome.best is None:
            hint = NOTHING_HINT
        elif outcome.confident:
            hint = CONFIDENT_HINT.format(name=outcome.best.card.name)
        else:
            hint = UNSURE_HINT
        return cls(
            scan_id=outcome.scan_id,
            confident=outcome.confident,
            hint=hint,
            best=ScanMatchOut.build(outcome.best) if outcome.best else None,
            alternatives=[ScanMatchOut.build(match) for match in outcome.alternatives],
            grading=(
                GradingOut(company=outcome.grading.company, grade=outcome.grading.grade)
                if outcome.grading
                else None
            ),
            detected=outcome.detected,
            duration_ms=outcome.duration_ms,
            can_save_reference=outcome.reference_available,
        )


class BatchItemOut(BaseModel):
    filename: str
    result: ScanResultOut | None
    error: str | None

    @classmethod
    def build(cls, item: BatchItem) -> BatchItemOut:
        return cls(
            filename=item.filename,
            result=ScanResultOut.build(item.outcome) if item.outcome else None,
            error=item.error,
        )


class BinderCellOut(BaseModel):
    row: int
    column: int
    result: ScanResultOut


class BinderResultOut(BaseModel):
    beta: bool = True
    method: str = Field(description="konturen, 3x3, 4x3 oder 2x2")
    cells: list[BinderCellOut]

    @classmethod
    def build(cls, outcome: BinderOutcome) -> BinderResultOut:
        return cls(
            method=outcome.method,
            cells=[
                BinderCellOut(row=c.row, column=c.column, result=ScanResultOut.build(c.outcome))
                for c in outcome.cells
            ],
        )


class ConfirmIn(BaseModel):
    card_id: uuid.UUID = Field(description="Bestätigte oder selbst gewählte Karte")
    save_reference: bool = Field(
        default=True, description="Kartenausschnitt als eigenes Referenzbild speichern"
    )


class ConfirmOut(BaseModel):
    scan_id: uuid.UUID
    card: CardOut
    reference_saved: bool
    reference_id: uuid.UUID | None
    note: str | None


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    card: CardOut
    width: int
    height: int
    feature_count: int
    created_at: datetime
