"""Admin-Bereich: Nutzer, Einladungen, Passwort-Reset-Codes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import AdminServiceDep, AdminUser, PriceServiceDep, SessionDep, client_ip
from app.schemas.admin import (
    AdminUserUpdate,
    InviteCreate,
    InviteCreated,
    InviteOut,
    PasswordResetCreated,
)
from app.schemas.auth import UserOut
from app.schemas.collection import ItemOut, ItemPage, SummaryOut
from app.services.audit import record_audit
from app.services.collection import CollectionService, ItemFilter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(_admin: AdminUser, admin_service: AdminServiceDep) -> list[UserOut]:
    return [UserOut.model_validate(user) for user in await admin_service.list_users()]


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    request: Request,
    admin: AdminUser,
    admin_service: AdminServiceDep,
) -> UserOut:
    """Nutzer sperren/entsperren oder Rolle ändern."""
    user = await admin_service.update_user(
        admin, user_id, is_active=body.is_active, role=body.role, ip=client_ip(request)
    )
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/password-reset", status_code=status.HTTP_201_CREATED)
async def create_password_reset(
    user_id: uuid.UUID, request: Request, admin: AdminUser, admin_service: AdminServiceDep
) -> PasswordResetCreated:
    """Einmal-Code für einen Passwort-Reset erzeugen (an den Nutzer weitergeben)."""
    issued = await admin_service.create_password_reset(admin, user_id, ip=client_ip(request))
    return PasswordResetCreated(code=issued.plain_code, expires_at=issued.record.expires_at)


@router.get("/invites")
async def list_invites(_admin: AdminUser, admin_service: AdminServiceDep) -> list[InviteOut]:
    now = datetime.now(UTC)
    return [InviteOut.from_invite(invite, now) for invite in await admin_service.list_invites()]


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreate, admin: AdminUser, admin_service: AdminServiceDep
) -> InviteCreated:
    issued = await admin_service.create_invite(admin, note=body.note, ttl_days=body.ttl_days)
    base = InviteOut.from_invite(issued.record, datetime.now(UTC))
    return InviteCreated(**base.model_dump(), code=issued.plain_code)


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: uuid.UUID, admin: AdminUser, admin_service: AdminServiceDep
) -> InviteOut:
    invite = await admin_service.revoke_invite(admin, invite_id)
    return InviteOut.from_invite(invite, datetime.now(UTC))


# ------------------------------------------------ Sammlungen anderer (nur lesend)


async def get_foreign_collection(
    user_id: uuid.UUID,
    *,
    request: Request,
    admin: AdminUser,
    admin_service: AdminServiceDep,
    session: SessionDep,
    prices: PriceServiceDep,
) -> CollectionService:
    """Lesender Zugriff auf eine fremde Sammlung – jeder Zugriff landet im Audit-Log."""
    owner = await admin_service.get_user(user_id)
    record_audit(
        session,
        action="admin.collection_viewed",
        actor_id=admin.id,
        target_user_id=owner.id,
        ip=client_ip(request),
        details={"view": request.url.path.rsplit("/", 1)[-1]},
    )
    return CollectionService(session, owner, prices)


ForeignCollection = Annotated[CollectionService, Depends(get_foreign_collection)]


@router.get("/users/{user_id}/collection/summary")
async def user_collection_summary(collection: ForeignCollection) -> SummaryOut:
    return SummaryOut.build(await collection.summary())


@router.get("/users/{user_id}/collection/items")
async def user_collection_items(collection: ForeignCollection) -> ItemPage:
    items, total = await collection.list_items(ItemFilter(), limit=500)
    return ItemPage(items=[ItemOut.build(i) for i in items], total=total)
