"""Gemeinsame Test-Fixtures.

Die Tests laufen gegen eine echte PostgreSQL-Datenbank (Standard:
``postgresql+asyncpg://tracker:tracker@localhost:5432/tracker_test``, änderbar über
``PT_TEST_DATABASE_URL``). Zu Beginn wird das Schema per Alembic frisch aufgebaut – das
testet gleichzeitig die Migrationen. Vor jedem Test werden alle Tabellen geleert.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.models import Role, User
from app.services.admin import AdminService
from tests.pricing_helpers import FakeProvider

TEST_DATABASE_URL = os.environ.get(
    "PT_TEST_DATABASE_URL", "postgresql+asyncpg://tracker:tracker@localhost:5432/tracker_test"
)
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PASSWORD = "richtig-gutes-passwort"


async def _reset_schema() -> None:
    dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Baut das Schema einmal pro Testlauf über alle Alembic-Migrationen auf."""
    asyncio.run(_reset_schema())
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
def settings(migrated_database: str) -> Settings:
    """Einstellungen für Tests (kurze Limits, festes Geheimnis)."""
    return Settings(
        environment="test",
        log_level="WARNING",
        database_url=migrated_database,
        jwt_secret="test-secret-mit-ausreichender-laenge-1234567890",
        login_rate_limit=3,
    )


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Engine ohne Pool (jede Verbindung gehört zum Event-Loop des Tests); leert alle Tabellen."""
    db_engine = create_engine(settings.database_url, poolclass=NullPool)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with db_engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def price_provider() -> FakeProvider:
    """Steuerbare Preisquelle statt TCGdex – kein Test geht ins Netz."""
    return FakeProvider()


@pytest.fixture
async def client(
    settings: Settings, engine: AsyncEngine, price_provider: FakeProvider
) -> AsyncIterator[AsyncClient]:
    """HTTP-Client gegen die App (inkl. Lifespan), ohne echten Server."""
    app = create_app(settings, engine=engine, price_providers=[price_provider])
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


@dataclass
class Account:
    """Ein Testkonto samt Tokens."""

    user_id: uuid.UUID
    email: str
    password: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, object]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()
    return data


@pytest.fixture
async def admin(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> Account:
    """Ein angemeldeter Admin (angelegt wie per CLI)."""
    async with session_factory() as session:
        user: User = await AdminService(session, settings).create_user(
            email="admin@example.com",
            password=DEFAULT_PASSWORD,
            display_name="Admin",
            role=Role.ADMIN,
        )
        await session.commit()
    tokens = await _login(client, "admin@example.com", DEFAULT_PASSWORD)
    return Account(
        user_id=user.id,
        email="admin@example.com",
        password=DEFAULT_PASSWORD,
        access_token=str(tokens["access_token"]),
        refresh_token=str(tokens["refresh_token"]),
    )


RegisterUser = Callable[[str], Awaitable[Account]]


@pytest.fixture
def register_user(client: AsyncClient, admin: Account) -> RegisterUser:
    """Registriert einen Nutzer über den echten Weg: Admin-Einladung → /auth/register."""

    async def _register(email: str) -> Account:
        invite = await client.post("/api/v1/admin/invites", json={}, headers=admin.headers)
        assert invite.status_code == 201, invite.text
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "invite_code": invite.json()["code"],
                "email": email,
                "password": DEFAULT_PASSWORD,
                "display_name": email.split("@", maxsplit=1)[0],
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        return Account(
            user_id=uuid.UUID(data["user"]["id"]),
            email=email,
            password=DEFAULT_PASSWORD,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )

    return _register
