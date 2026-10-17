"""Eigenes Konto: Profil, Passwort, Sitzungen."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import AuthServiceDep, CurrentUser, client_ip
from app.schemas.auth import ChangePasswordRequest, SessionOut, UpdateMeRequest, UserOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("")
async def update_me(body: UpdateMeRequest, user: CurrentUser) -> UserOut:
    user.display_name = body.display_name
    return UserOut.model_validate(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest, request: Request, user: CurrentUser, auth: AuthServiceDep
) -> None:
    """Passwort ändern. Alle Sitzungen werden beendet; danach neu anmelden."""
    await auth.change_password(
        user,
        current_password=body.current_password,
        new_password=body.new_password,
        ip=client_ip(request),
    )


@router.get("/sessions")
async def list_sessions(user: CurrentUser, auth: AuthServiceDep) -> list[SessionOut]:
    return [SessionOut.model_validate(token) for token in await auth.list_sessions(user)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, user: CurrentUser, auth: AuthServiceDep) -> None:
    """Eine eigene Sitzung beenden (z. B. verlorenes Handy)."""
    await auth.revoke_session(user, session_id)
