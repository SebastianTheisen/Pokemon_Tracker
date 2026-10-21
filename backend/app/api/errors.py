"""Einheitliches Fehlerformat: ``{"error": {"code": "...", "message": "..."}}``."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import (
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ServiceError,
    UpstreamError,
)

_STATUS: dict[type[ServiceError], int] = {
    AuthenticationError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    InvalidInputError: 400,
    RateLimitedError: 429,
    UpstreamError: 502,
}


async def _handle_service_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)  # noqa: S101 – nur für ServiceError registriert
    status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)
    headers: dict[str, str] = {}
    if isinstance(exc, AuthenticationError):
        headers["WWW-Authenticate"] = "Bearer"
    if isinstance(exc, RateLimitedError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _handle_service_error)
