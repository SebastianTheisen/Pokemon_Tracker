"""Gemeinsame FastAPI-Abhängigkeiten: Einstellungen, DB-Sitzung, angemeldeter Nutzer."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_session
from app.models import User
from app.services.admin import AdminService
from app.services.auth import AuthService
from app.services.errors import AuthenticationError, PermissionDeniedError
from app.services.rate_limit import FailureLimiter

_bearer = HTTPBearer(auto_error=False, description="Access-Token aus /auth/login")


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_login_limiter(request: Request) -> FailureLimiter:
    limiter: FailureLimiter = request.app.state.login_limiter
    return limiter


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Prüft das Access-Token und lädt den Nutzer frisch aus der Datenbank.

    Dadurch wirken Sperren und Rollenänderungen sofort, nicht erst nach Ablauf des Tokens.
    """
    if credentials is None:
        raise AuthenticationError("Anmeldung erforderlich.", code="not_authenticated")
    try:
        claims = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret.get_secret_value()
        )
    except InvalidTokenError as exc:
        raise AuthenticationError(
            "Sitzung ungültig oder abgelaufen.", code="invalid_token"
        ) from exc
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Konto ist deaktiviert.", code="account_disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Nur für Admins.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_auth_service(
    session: SessionDep,
    settings: SettingsDep,
    limiter: Annotated[FailureLimiter, Depends(get_login_limiter)],
) -> AuthService:
    return AuthService(session, settings, limiter=limiter)


def get_admin_service(session: SessionDep, settings: SettingsDep) -> AdminService:
    return AdminService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
