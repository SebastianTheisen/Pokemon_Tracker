"""Schemas des Admin-Bereichs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import InviteCode, Role

InviteStatus = Literal["open", "used", "revoked", "expired"]


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: Role | None = None


class InviteCreate(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    ttl_days: Annotated[int, Field(ge=1, le=90)] | None = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note: str | None
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_by_id: uuid.UUID | None
    revoked_at: datetime | None
    status: InviteStatus

    @classmethod
    def from_invite(cls, invite: InviteCode, now: datetime) -> InviteOut:
        status: InviteStatus
        if invite.used_at is not None:
            status = "used"
        elif invite.revoked_at is not None:
            status = "revoked"
        elif invite.expires_at <= now:
            status = "expired"
        else:
            status = "open"
        return cls(
            id=invite.id,
            note=invite.note,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            used_at=invite.used_at,
            used_by_id=invite.used_by_id,
            revoked_at=invite.revoked_at,
            status=status,
        )


class InviteCreated(InviteOut):
    code: str = Field(description="Klartext-Code – wird nur dieses eine Mal angezeigt.")


class PasswordResetCreated(BaseModel):
    code: str = Field(description="Einmal-Code – wird nur dieses eine Mal angezeigt.")
    expires_at: datetime
