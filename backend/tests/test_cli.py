"""Tests der Kommandozeile (``python -m app.cli``) gegen die Test-Datenbank.

Die CLI startet ihre eigene Event-Loop (``asyncio.run``), deshalb sind diese Tests synchron.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select, text

from app import cli
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.models import CollectionItem, Folder, Product, ScanLog
from app.providers.tcgdex import TcgdexClient
from app.scanner.runtime import ScannerRuntime
from tests.fake_tcgdex import FakeTcgdex
from tests.pricing_helpers import FakeProvider, cardmarket
from tests.scan_helpers import TESTSET, FakeImages, ScriptedReader, build_scan_catalog, lines


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
    assert "de           1         1             0       0        4 0" in output
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


# ------------------------------------------------------------------ Scanner


@pytest.fixture
def scanner_env(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[ScriptedReader, FakeImages]:
    """Scanner-CLI mit OCR-Attrappe, simuliertem Bild-Server und Testkatalog."""
    monkeypatch.setenv("PT_SCANNER_DATA_DIR", str(tmp_path / "scanner"))
    get_settings.cache_clear()
    reader, images = ScriptedReader(), FakeImages()

    @asynccontextmanager
    async def fake_scanner(settings: Settings) -> AsyncIterator[ScannerRuntime]:
        async with httpx.AsyncClient(transport=images.transport()) as client:
            yield ScannerRuntime(settings, reader, client)

    monkeypatch.setattr(cli, "_scanner", fake_scanner)

    async def prepare() -> None:
        engine = create_engine(get_settings().database_url)
        await build_scan_catalog(create_session_factory(engine), images)
        await engine.dispose()

    asyncio.run(prepare())
    monkeypatch.setenv("PT_ADMIN_PASSWORD", "admin-passwort-123")
    cli.main(["create-admin", "--email", "chef@example.com", "--name", "Chef"])
    return reader, images


def _scan_log_count() -> int:
    async def count() -> int:
        engine = create_engine(get_settings().database_url)
        async with engine.connect() as connection:
            value = int(await connection.scalar(select(func.count()).select_from(ScanLog)) or 0)
        await engine.dispose()
        return value

    return asyncio.run(count())


def test_scan_command(
    scanner_env: tuple[ScriptedReader, FakeImages], capsys: pytest.CaptureFixture[str]
) -> None:
    reader, _ = scanner_env
    reader.script("06.jpg", lines("ルギア", "142/103"))

    cli.main(["scan", str(TESTSET / "06.jpg"), "--email", "chef@example.com"])
    cli.main(["scan", str(TESTSET / "07.jpg"), "--email", "chef@example.com"])
    cli.main(["scan", str(TESTSET / "01.jpg"), "--email", "chef@example.com", "--language", "ja"])

    output = capsys.readouterr().out
    assert "Erkannt als ルギア (sicher)" in output
    assert "1. ルギア · Lugia-Set · 142 [ja] (PCG10-142) · 0.85" in output
    assert "Keine Karte erkannt." in output
    assert _scan_log_count() == 0  # Probe wird zurückgerollt

    with pytest.raises(SystemExit, match="Kein Nutzer"):
        cli.main(["scan", str(TESTSET / "06.jpg"), "--email", "niemand@example.com"])


def test_scan_command_shows_slab(
    scanner_env: tuple[ScriptedReader, FakeImages], capsys: pytest.CaptureFixture[str]
) -> None:
    reader, _ = scanner_env
    reader.script("04.jpg", lines("ルギアV", "#110", "GEM MT", "10", "PSA"))
    cli.main(["scan", str(TESTSET / "04.jpg"), "--email", "chef@example.com"])
    assert "Slab: PSA 10" in capsys.readouterr().out


def test_scan_eval_command(
    scanner_env: tuple[ScriptedReader, FakeImages],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reader, _ = scanner_env
    reader.script("02.jpg", lines("Team Rockets MewtuX", "Fähigkeit", "DR231/182"))
    reader.script("03.jpg", lines("ルギアV", "512 F 110/098 SR"))
    reader.script("01.jpg", lines("ゼニガメ", "No.007"))
    expected = tmp_path / "soll.csv"
    expected.write_text(
        (TESTSET / "soll.csv").read_text(encoding="utf-8") + "fehlt.jpg;X;1;de;\n",
        encoding="utf-8",
    )
    out = tmp_path / "bericht.md"

    cli.main(
        [
            "scan-eval",
            "--photos",
            str(TESTSET),
            "--expected",
            str(expected),
            "--email",
            "chef@example.com",
            "--out",
            str(out),
        ]
    )

    report = out.read_text(encoding="utf-8")
    assert "Bericht geschrieben" in capsys.readouterr().out
    assert "- Fotos: 8 (davon 1 nicht im Katalog)" in report
    assert "- Nicht im Katalog, richtig als unsicher erkannt: 1/1 (100 %)" in report
    assert "- Top-1 DE/EN: 1/2 (50 %) – Ziel ≥ 85 % ❌ (zu wenige Fotos" in report
    assert "| 02.jpg | Team Rockets Mewtu ex · 231/182 [de] (sv10-231) | ✅" in report
    assert "| 03.jpg | ルギアV · 110/098 [ja] (S12-110) | ✅" in report
    assert "| fehlt.jpg | X · 1 [de] | Fehler:" in report
    assert "- **02.jpg:** Nummern DR231/182 · Namen Team Rockets MewtuX" in report
    assert _scan_log_count() == 0

    # Ohne --out: Bericht auf der Konsole.
    cli.main(
        ["scan-eval", "--photos", str(TESTSET), "--expected", str(TESTSET / "soll.csv"),
         "--email", "chef@example.com"]
    )  # fmt: skip
    assert "# Scanner-Evaluation" in capsys.readouterr().out


def test_scanner_warmup(
    cli_env: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeReader:
        def warm_up(self, *, korean: bool = False) -> int:
            return 2 if korean else 1

    monkeypatch.setattr(cli, "RapidOcrReader", FakeReader)
    cli.main(["scanner-warmup", "--korean"])
    output = capsys.readouterr().out
    assert "Standardmodell (PP-OCRv6): 1 Zeilen erkannt" in output
    assert "Koreanisches Modell: 2 Zeilen erkannt" in output
