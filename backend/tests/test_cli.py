"""Tests der Kommandozeile (``python -m app.cli``) gegen die Test-Datenbank.

Die CLI startet ihre eigene Event-Loop (``asyncio.run``), deshalb sind diese Tests synchron.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from functools import partial

import pytest
from sqlalchemy import text

from app import cli
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine
from app.providers.tcgdex import TcgdexClient
from tests.fake_tcgdex import FakeTcgdex


async def _truncate(database_url: str) -> None:
    engine = create_engine(database_url)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def cli_env(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Leere Datenbank; die CLI liest ihre Einstellungen aus der Umgebung."""
    asyncio.run(_truncate(migrated_database))
    monkeypatch.setenv("PT_DATABASE_URL", migrated_database)
    monkeypatch.setenv("PT_LOG_LEVEL", "WARNING")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_admin_and_invite(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PT_ADMIN_PASSWORD", "admin-passwort-123")

    cli.main(["create-admin", "--email", "Chef@Example.com", "--name", "Chef"])
    cli.main(["create-invite", "--note", "für Max", "--days", "3"])

    output = capsys.readouterr().out
    assert "Admin angelegt: chef@example.com" in output
    assert "Einladungscode: " in output


def test_create_admin_rejects_short_password_and_duplicates(
    cli_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PT_ADMIN_PASSWORD", "kurz")
    with pytest.raises(SystemExit, match="mindestens 10 Zeichen"):
        cli.main(["create-admin", "--email", "a@example.com", "--name", "A"])

    monkeypatch.setenv("PT_ADMIN_PASSWORD", "admin-passwort-123")
    cli.main(["create-admin", "--email", "a@example.com", "--name", "A"])
    with pytest.raises(SystemExit, match="bereits registriert"):
        cli.main(["create-admin", "--email", "a@example.com", "--name", "A"])


def test_create_invite_requires_admin(cli_env: None) -> None:
    with pytest.raises(SystemExit, match="Kein aktiver Admin"):
        cli.main(["create-invite"])


def test_sync_catalog_and_search(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeTcgdex()
    monkeypatch.setattr(cli, "TcgdexClient", partial(TcgdexClient, transport=fake.transport()))

    cli.main(["sync-catalog", "--languages", "de", "en"])
    cli.main(["search", "nachtara 215", "--language", "de"])
    cli.main(["search", "gibtsnicht"])

    output = capsys.readouterr().out
    assert "de           1         1             0        4 0" in output
    assert "[de   ] Nachtara VMAX · Drachenwandel · 215  (swsh7-215)" in output
    assert "Keine Treffer." in output


def test_sync_catalog_exits_with_error_on_failures(
    cli_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTcgdex()
    fake.failing_sets.add("S12")
    monkeypatch.setattr(cli, "TcgdexClient", partial(TcgdexClient, transport=fake.transport()))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["sync-catalog", "--languages", "ja"])

    assert exc_info.value.code == 1
