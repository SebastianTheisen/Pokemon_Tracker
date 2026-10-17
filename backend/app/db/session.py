"""Engine, Session-Fabrik und FastAPI-Abhängigkeit für Datenbanksitzungen."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.services.errors import ServiceError


def create_engine(database_url: str, **kwargs: object) -> AsyncEngine:
    """Erzeugt die Async-Engine (``pool_pre_ping`` gegen abgebrochene Verbindungen)."""
    return create_async_engine(database_url, pool_pre_ping=True, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session-Fabrik; ``expire_on_commit=False``, damit Objekte nach dem Commit lesbar bleiben."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI-Abhängigkeit: eine Sitzung pro Anfrage.

    Commit bei Erfolg; bei einer Ausnahme Rollback – außer ein fachlicher Fehler verlangt
    ausdrücklich, dass seine Änderungen bestehen bleiben (``persist_changes``).
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except ServiceError as exc:
            if exc.persist_changes:
                await session.commit()
            else:
                await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise
