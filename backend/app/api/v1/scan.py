"""Scanner: Foto, Stapel, Binderseite (Beta), Bestätigen, eigene Referenzbilder."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import ScanServiceDep, SettingsDep
from app.core.config import CatalogLanguage, Settings
from app.scanner.binder import BinderLayout
from app.schemas.catalog import CardOut
from app.schemas.scan import (
    BatchItemOut,
    BinderResultOut,
    ConfirmIn,
    ConfirmOut,
    ReferenceOut,
    ScanResultOut,
)
from app.services.errors import InvalidInputError

router = APIRouter(prefix="/scan", tags=["scan"])

LanguageHint = Annotated[
    CatalogLanguage | None,
    Query(description="Sprache der Karte, falls bekannt (sonst automatisch erkannt)"),
]


async def _read_upload(upload: UploadFile, settings: Settings) -> bytes:
    """Liest die Datei höchstens bis zur erlaubten Größe (größere werden abgelehnt)."""
    max_bytes = settings.scan_max_upload_mb * 1024 * 1024
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InvalidInputError(
            f"Bild ist zu groß (höchstens {settings.scan_max_upload_mb} MB).", code="file_too_large"
        )
    return data


@router.post("")
async def scan(
    service: ScanServiceDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="Foto (JPEG, PNG, WebP oder HEIC)")],
    language: LanguageHint = None,
) -> ScanResultOut:
    """Eine Karte erkennen: bester Treffer plus bis zu 4 Alternativen."""
    outcome = await service.scan(await _read_upload(file, settings), language_hint=language)
    return ScanResultOut.build(outcome)


@router.post("/batch")
async def scan_batch(
    service: ScanServiceDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File(description="Mehrere Fotos, je eine Karte")],
    language: LanguageHint = None,
) -> list[BatchItemOut]:
    """Stapel-Scan: Ergebnisliste zum Bestätigen und Korrigieren."""
    if len(files) > settings.scan_batch_max:
        raise InvalidInputError(
            f"Höchstens {settings.scan_batch_max} Bilder pro Stapel.", code="batch_too_large"
        )
    uploads = [
        (f.filename or f"bild-{i + 1}", await _read_upload(f, settings))
        for i, f in enumerate(files)
    ]
    return [
        BatchItemOut.build(item)
        for item in await service.scan_batch(uploads, language_hint=language)
    ]


@router.post("/binder")
async def scan_binder(
    service: ScanServiceDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="Foto einer Binderseite")],
    layout: Annotated[
        BinderLayout, Query(description="auto, 3x3 (9er-Seite), 4x3 (12er-Seite quer), 2x2")
    ] = "auto",
    language: LanguageHint = None,
) -> BinderResultOut:
    """Binderseite (Beta): jede Karte der Seite einzeln erkennen."""
    outcome = await service.scan_binder(
        await _read_upload(file, settings), layout=layout, language_hint=language
    )
    return BinderResultOut.build(outcome)


@router.post("/{scan_id}/confirm")
async def confirm_scan(scan_id: uuid.UUID, body: ConfirmIn, service: ScanServiceDep) -> ConfirmOut:
    """Treffer bestätigen oder korrigieren; speichert auf Wunsch ein eigenes Referenzbild."""
    outcome = await service.confirm(scan_id, body.card_id, save_reference=body.save_reference)
    return ConfirmOut(
        scan_id=outcome.scan_id,
        card=CardOut.model_validate(outcome.card),
        reference_saved=outcome.reference is not None,
        reference_id=outcome.reference.id if outcome.reference else None,
        note=outcome.reference_note,
    )


@router.get("/references")
async def list_references(
    service: ScanServiceDep, card_id: uuid.UUID | None = None
) -> list[ReferenceOut]:
    """Eigene Referenzbilder (wirken nur bei eigenen Scans)."""
    return [ReferenceOut.model_validate(row) for row in await service.list_references(card_id)]


@router.get(
    "/references/{reference_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def reference_image(reference_id: uuid.UUID, service: ScanServiceDep) -> Response:
    return Response(
        content=await service.reference_image(reference_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference(reference_id: uuid.UUID, service: ScanServiceDep) -> None:
    await service.delete_reference(reference_id)
