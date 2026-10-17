"""Einstiegspunkt der FastAPI-Anwendung."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.errors import register_error_handlers
from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.rate_limit import FailureLimiter


def create_app(settings: Settings | None = None, *, engine: AsyncEngine | None = None) -> FastAPI:
    """Erzeugt die Anwendung (Factory, damit Tests eigene Settings/Engine übergeben können)."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own_engine = engine is None
        app_engine = engine or create_engine(settings.database_url)
        app.state.engine = app_engine
        app.state.session_factory = create_session_factory(app_engine)
        yield
        if own_engine:
            await app_engine.dispose()

    app = FastAPI(
        title="Pokemon Tracker API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.login_limiter = FailureLimiter(
        max_failures=settings.login_rate_limit, window_seconds=settings.login_rate_window_seconds
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
