"""Health-Check für Monitoring und Docker."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Antwort des Health-Checks."""

    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Meldet, dass der Dienst läuft (noch ohne Datenbankprüfung)."""
    return HealthResponse(status="ok", version=__version__)
