"""Registrierung, Anmeldung, Token-Erneuerung, Abmeldung, Passwort-Reset."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import AuthServiceDep, client_ip
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth import TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        user=UserOut.model_validate(pair.user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, auth: AuthServiceDep) -> TokenResponse:
    """Konto mit Einladungscode anlegen; meldet direkt an."""
    pair = await auth.register(
        invite_code=body.invite_code,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )
    return _token_response(pair)


@router.post("/login")
async def login(body: LoginRequest, request: Request, auth: AuthServiceDep) -> TokenResponse:
    pair = await auth.login(
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _token_response(pair)


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request, auth: AuthServiceDep) -> TokenResponse:
    """Neues Token-Paar; das alte Refresh-Token wird dabei ungültig (Rotation)."""
    pair = await auth.refresh(
        refresh_token=body.refresh_token, user_agent=request.headers.get("user-agent")
    )
    return _token_response(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, auth: AuthServiceDep) -> None:
    await auth.logout(refresh_token=body.refresh_token)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordRequest, request: Request, auth: AuthServiceDep
) -> None:
    """Neues Passwort mit dem Einmal-Code vom Admin setzen. Beendet alle Sitzungen."""
    await auth.reset_password(code=body.code, new_password=body.new_password, ip=client_ip(request))
