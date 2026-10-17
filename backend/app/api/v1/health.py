"""Health-Check für Monitoring und Docker."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.api.deps import SessionDep

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Antwort des Health-Checks."""

    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "error"]


@router.get("/health")
async def health(session: SessionDep, response: Response) -> HealthResponse:
    """Meldet, ob der Dienst läuft und die Datenbank erreichbar ist."""
    try:
        await session.execute(text("SELECT 1"))
        database: Literal["ok", "error"] = "ok"
    except Exception:  # jeder DB-Fehler bedeutet „nicht gesund“
        database = "error"
        await session.rollback()
    if database != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if database == "ok" else "degraded", version=__version__, database=database
    )
