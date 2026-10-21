"""Schemas für Scans, Bestätigungen und eigene Referenzbilder."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.providers.psa import PsaCert
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


def _psa_warning(outcome: ScanOutcome, psa: PsaCert | None) -> str | None:
    """Hinweis, wenn PSA eine andere Kartennummer nennt als der beste Treffer."""
    if psa is None or not psa.card_number or outcome.best is None:
        return None
    psa_number = psa.card_number.lstrip("0") or "0"
    if psa_number.upper() == outcome.best.card.number_norm.upper():
        return None
    return (
        f"Laut PSA ist es Nr. {psa.card_number} ({psa.subject or 'unbekannt'}) – "
        "bitte die Karte prüfen."
    )


class GradingOut(BaseModel):
    company: str
    grade: str | None
    cert: str | None = Field(default=None, description="Zertifikatsnummer vom Etikett")


class PsaCertOut(BaseModel):
    """Von PSA bestätigtes Zertifikat (offizielle PSA-API)."""

    cert: str
    year: str | None
    brand: str | None = Field(description="Set laut PSA, z. B. „POKEMON JAPANESE …“")
    card_number: str | None
    subject: str | None = Field(description="Karte laut PSA, z. B. „FA/LUGIA V“")
    variety: str | None
    grade_description: str | None
    grade: str | None
    population: int | None
    population_higher: int | None

    @classmethod
    def build(cls, cert: PsaCert) -> PsaCertOut:
        return cls(**asdict(cert))


class ScanResultOut(BaseModel):
    scan_id: uuid.UUID
    confident: bool
    hint: str
    best: ScanMatchOut | None
    alternatives: list[ScanMatchOut]
    grading: GradingOut | None = Field(description="Slab erkannt → als gegradet vorschlagen")
    psa: PsaCertOut | None = Field(
        default=None, description="Von PSA bestätigt (nur mit PSA-Token und lesbarer Nummer)"
    )
    psa_warning: str | None = Field(
        default=None, description="PSA nennt eine andere Kartennummer als der beste Treffer"
    )
    detected: dict[str, Any]
    duration_ms: int
    can_save_reference: bool

    @classmethod
    def build(cls, outcome: ScanOutcome, *, psa: PsaCert | None = None) -> ScanResultOut:
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
                GradingOut(
                    company=outcome.grading.company,
                    # PSA kennt die Note sicher – sie gilt vor der gelesenen.
                    grade=(psa.grade if psa and psa.grade else outcome.grading.grade),
                    cert=outcome.grading.cert,
                )
                if outcome.grading
                else None
            ),
            psa=PsaCertOut.build(psa) if psa else None,
            psa_warning=_psa_warning(outcome, psa),
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
