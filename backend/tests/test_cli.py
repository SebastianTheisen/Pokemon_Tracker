"""Tests der Kommandozeile (``python -m app.cli``) gegen die Test-Datenbank.

Die CLI startet ihre eigene Event-Loop (``asyncio.run``), deshalb sind diese Tests synchron.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from functools import partial

import pytest
from sqlalchemy import func, select, text

from app import cli
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine
from app.models import CollectionItem, Folder, Product
from app.providers.tcgdex import TcgdexClient
from tests.fake_tcgdex import FakeTcgdex
from tests.pricing_helpers import FakeProvider, cardmarket


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


def test_refresh_prices_command(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = FakeProvider(quotes=[cardmarket("trend", "10")])
    monkeypatch.setattr(cli, "build_price_providers", lambda _settings, _client: [provider])

    cli.main(["refresh-prices"])

    assert "Karten: 0 · neue Preiswerte: 0 · mit Fehlern: 0 · Tageswerte: 0" in (
        capsys.readouterr().out
    )


def test_prices_command_shows_proof_and_estimates(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeTcgdex()
    monkeypatch.setattr(cli, "TcgdexClient", partial(TcgdexClient, transport=fake.transport()))
    cli.main(["sync-catalog", "--languages", "de"])
    provider = FakeProvider(quotes=[cardmarket("trend", "1805.90")])
    monkeypatch.setattr(cli, "build_price_providers", lambda _settings, _client: [provider])

    cli.main(["prices", "nachtara 215", "--language", "de"])
    cli.main(["prices", "gibtsnicht"])

    output = capsys.readouterr().out
    assert "Nachtara VMAX · Drachenwandel · 215 [de] (swsh7-215)" in output
    assert "cardmarket/normal: trend 1805.90 EUR" in output
    assert "Beleg: https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273" in output
    assert "EX: 1535.02 EUR (Schätzung, trend = 1805.90 × 0.85)" in output
    assert "Keine Karte gefunden." in output


def test_collection_check_leaves_no_data(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeTcgdex()
    monkeypatch.setattr(cli, "TcgdexClient", partial(TcgdexClient, transport=fake.transport()))
    cli.main(["sync-catalog", "--languages", "de"])
    monkeypatch.setenv("PT_ADMIN_PASSWORD", "admin-passwort-123")
    cli.main(["create-admin", "--email", "chef@example.com", "--name", "Chef"])
    provider = FakeProvider(quotes=[cardmarket("trend", "100")])
    monkeypatch.setattr(cli, "build_price_providers", lambda _settings, _client: [provider])

    cli.main(["collection-check", "--email", "Chef@example.com"])

    output = capsys.readouterr().out
    assert "raw    2× Nachtara VMAX [NM]: 200.00 € (estimated" in output
    assert "sealed 1× Probe-Display [-]: 150.00 € (manual)" in output
    assert "Gesamt: 350.00 €" in output  # Glurak/Mewtu fehlen im Test-Katalog
    assert "Probe zurückgerollt" in output

    async def count_rows() -> list[int]:
        engine = create_engine(get_settings().database_url)
        async with engine.connect() as connection:
            counts = [
                int(await connection.scalar(select(func.count()).select_from(model)) or 0)
                for model in (CollectionItem, Product, Folder)
            ]
        await engine.dispose()
        return counts

    assert asyncio.run(count_rows()) == [0, 0, 0]
