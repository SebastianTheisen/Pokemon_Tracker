"""Meldungen „Das fehlt“ – Nutzer melden, Admins bekommen eine Mitteilung und haken ab."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, SessionDep, SettingsDep
from app.models import MissingReport, ReportKind, Role, User
from app.services import push
from app.services.errors import InvalidInputError, NotFoundError

router = APIRouter(tags=["reports"])

MAX_OPEN_PER_USER = 20
KIND_LABELS = {
    ReportKind.CARD: "Karte fehlt",
    ReportKind.SEALED: "Produkt fehlt",
    ReportKind.WRONG: "Falsche Daten",
    ReportKind.OTHER: "Sonstiges",
}


class ReportCreate(BaseModel):
    kind: ReportKind
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    context: Annotated[str, Field(max_length=200)] | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    kind: ReportKind
    text: str
    context: str | None
    created_at: datetime
    done_at: datetime | None
    reporter: str = Field(description="Anzeigename der meldenden Person")

    @classmethod
    def build(cls, report: MissingReport) -> ReportOut:
        return cls(
            id=report.id,
            kind=report.kind,
            text=report.text,
            context=report.context,
            created_at=report.created_at,
            done_at=report.done_at,
            reporter=report.user.display_name,
        )


class ReportUpdate(BaseModel):
    done: bool


@router.post("/reports", status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate, session: SessionDep, user: CurrentUser, settings: SettingsDep
) -> ReportOut:
    """Etwas Fehlendes melden; alle Admins bekommen eine Mitteilung (wenn eingeschaltet)."""
    open_count = await session.scalar(
        select(func.count()).where(
            MissingReport.user_id == user.id, MissingReport.done_at.is_(None)
        )
    )
    if (open_count or 0) >= MAX_OPEN_PER_USER:
        raise InvalidInputError("Du hast schon viele offene Meldungen – bitte etwas warten.")
    report = MissingReport(
        user_id=user.id, kind=body.kind, text=body.text, context=(body.context or None)
    )
    session.add(report)
    await session.flush()
    await session.refresh(report, ["user"])
    admins = (
        await session.scalars(select(User).where(User.role == Role.ADMIN, User.is_active))
    ).all()
    message = push.PushMessage(
        title=f"Meldung von {user.display_name}: {KIND_LABELS[body.kind]}",
        body=body.text[:180],
        url="/admin/reports",
        tag=f"report-{report.id}",
    )
    async with httpx.AsyncClient(timeout=20) as client:
        for admin in admins:
            await push.notify_user(session, client, settings, admin.id, message)
    return ReportOut.build(report)


@router.get("/reports/mine")
async def my_reports(session: SessionDep, user: CurrentUser) -> list[ReportOut]:
    rows = await session.scalars(
        select(MissingReport)
        .where(MissingReport.user_id == user.id)
        .order_by(MissingReport.created_at.desc())
        .limit(50)
    )
    return [ReportOut.build(r) for r in rows.unique().all()]


@router.get("/admin/reports")
async def list_reports(session: SessionDep, _admin: AdminUser) -> list[ReportOut]:
    """Alle Meldungen, offene zuerst."""
    rows = await session.scalars(
        select(MissingReport)
        .order_by(MissingReport.done_at.is_not(None), MissingReport.created_at.desc())
        .limit(200)
    )
    return [ReportOut.build(r) for r in rows.unique().all()]


@router.patch("/admin/reports/{report_id}")
async def update_report(
    report_id: uuid.UUID, body: ReportUpdate, session: SessionDep, _admin: AdminUser
) -> ReportOut:
    report = await session.get(MissingReport, report_id)
    if report is None:
        raise NotFoundError("Meldung nicht gefunden.")
    report.done_at = datetime.now(UTC) if body.done else None
    await session.flush()
    return ReportOut.build(report)
