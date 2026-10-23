"""Überwachung: Prüfungen, Meldelogik (Störung, Erinnerung, Entwarnung) und ntfy."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.monitor import Check, Message, Monitor, latest_backup, ntfy_sender, run_checks
from app.worker import HEARTBEAT_FILE

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def test_alert_reminder_and_recovery() -> None:
    monitor = Monitor(remind_after=timedelta(hours=24))
    broken = [Check("Sicherung", ok=False, detail="noch nie gelaufen")]

    first = monitor.evaluate(broken, NOW)
    quiet = monitor.evaluate(broken, NOW + timedelta(hours=1))
    reminder = monitor.evaluate(broken, NOW + timedelta(hours=25))
    recovered = monitor.evaluate([Check("Sicherung", ok=True, detail="vor 1 h")], NOW)
    still_quiet = monitor.evaluate([Check("Sicherung", ok=True, detail="vor 2 h")], NOW)

    assert [m.title for m in first] == ["Kartenkiste: Sicherung gestört"]
    assert quiet == []
    assert [m.title for m in reminder] == ["Kartenkiste: Sicherung gestört (weiterhin)"]
    assert [(m.title, m.tags) for m in recovered] == [
        ("Sicherung wieder in Ordnung", "white_check_mark")
    ]
    assert still_quiet == []


def test_latest_backup(tmp_path: Path) -> None:
    assert latest_backup(tmp_path) is None
    (tmp_path / "latest").write_text("20261024-023001\n", encoding="utf-8")
    assert latest_backup(tmp_path) == datetime(2026, 10, 24, 2, 30, 1, tzinfo=UTC)


async def test_checks_report_each_part(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings, tmp_path: Path
) -> None:
    backups, scanner = tmp_path / "backups", tmp_path / "scanner"
    backups.mkdir()
    scanner.mkdir()
    (backups / "latest").write_text("20261023-023000", encoding="utf-8")  # 33,5 h alt
    (scanner / HEARTBEAT_FILE).write_text((NOW - timedelta(minutes=3)).isoformat())
    config = settings.model_copy(
        update={"monitor_backup_dir": backups, "scanner_data_dir": scanner}
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        checks = {c.name: c for c in await run_checks(config, session_factory, client, NOW)}

    assert (checks["API"].ok, checks["API"].detail) == (False, "Antwort 503")
    assert checks["Worker"].ok
    assert (checks["Sicherung"].ok, checks["Sicherung"].detail) == (False, "zuletzt vor 34 h")
    assert (checks["Cardmarket-Import"].ok, checks["Cardmarket-Import"].detail) == (
        False,
        "noch nie gelaufen",
    )
    assert "Preisrunde" not in checks  # ohne Sammlungen keine Tageswerte
    assert "frei" in checks["Speicherplatz"].detail  # Wert hängt vom Testrechner ab


async def test_ntfy_message(settings: Settings) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    config = settings.model_copy(update={"ntfy_topic": SecretStr("kartenkiste-geheim-123")})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ntfy_sender(config, client)(
            Message("Kartenkiste: Sicherung gestört", "noch nie gelaufen", "high", "warning")
        )

    request = sent[0]
    assert str(request.url) == "https://ntfy.sh/kartenkiste-geheim-123"
    assert request.content == b"noch nie gelaufen"
    title = request.headers["Title"].removeprefix("=?UTF-8?B?").removesuffix("?=")
    assert base64.b64decode(title).decode() == "Kartenkiste: Sicherung gestört"
    assert (request.headers["Priority"], request.headers["Tags"]) == ("high", "warning")
