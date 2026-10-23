"""Überwachung mit Push-Nachricht aufs Handy (ntfy) – eigener Dienst ``monitor``.

Start (im Container)::

    python -m app.monitor          # Dauerbetrieb
    python -m app.monitor --once   # einmal prüfen und Ergebnis ausgeben (Test)

Alle ``PT_MONITOR_INTERVAL_MINUTES`` Minuten werden geprüft:

=====================  ==============================================================
Prüfung                Störung, wenn …
=====================  ==============================================================
API                    ``/api/v1/health`` nicht mit 200 antwortet
Worker                 sein Lebenszeichen älter als ``PT_MONITOR_HEARTBEAT_MAX_MINUTES``
Preisrunde             der letzte Tageswert einer Sammlung älter als 36 h ist
Cardmarket             der letzte erfolgreiche Katalog-Import älter als 60 h ist
Sicherung              die letzte Sicherung älter als 30 h ist (oder keine existiert)
Speicherplatz          weniger als 10 % frei sind
=====================  ==============================================================

Gemeldet wird beim **Wechsel**: Störung (⚠️) und Entwarnung (✅); eine bestehende Störung
nach ``PT_MONITOR_REMIND_HOURS`` erneut. Beim Start kommt einmal „Überwachung läuft“ –
so ist sofort zu sehen, ob die Nachrichten ankommen. Ohne ``PT_NTFY_TOPIC`` nur Log.

Der Dienst läuft getrennt vom Worker, damit er auch dessen Ausfall bemerkt.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.models import PortfolioSnapshot
from app.services.cardmarket_catalog import last_successful_import
from app.worker import HEARTBEAT_FILE

log = structlog.get_logger(__name__)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Check:
    """Ergebnis einer Prüfung."""

    name: str
    ok: bool
    detail: str


def _age_text(age: timedelta) -> str:
    hours = age.total_seconds() / 3600
    return f"{hours * 60:.0f} min" if hours < 1 else f"{hours:.0f} h"


def check_age(name: str, when: datetime | None, limit: timedelta, now: datetime) -> Check:
    if when is None:
        return Check(name, ok=False, detail="noch nie gelaufen")
    age = now - when
    return Check(name, ok=age <= limit, detail=f"zuletzt vor {_age_text(age)}")


def latest_backup(directory: Path) -> datetime | None:
    """Zeitpunkt der letzten vollständigen Sicherung (Datei ``latest`` von backup.sh)."""
    try:
        stamp = (directory / "latest").read_text(encoding="utf-8").strip()
        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except (OSError, ValueError):
        return None


def heartbeat(path: Path) -> datetime | None:
    try:
        return datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def check_disk(directory: Path, min_free_percent: int) -> Check:
    try:
        usage = shutil.disk_usage(directory)
    except OSError as exc:
        return Check("Speicherplatz", ok=False, detail=f"nicht lesbar ({exc.strerror})")
    free = usage.free / usage.total * 100
    return Check(
        "Speicherplatz",
        ok=free >= min_free_percent,
        detail=f"{free:.0f} % frei ({usage.free / 1e9:.1f} GB)",
    )


async def check_api(client: httpx.AsyncClient, url: str) -> Check:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return Check("API", ok=False, detail=f"nicht erreichbar ({type(exc).__name__})")
    if response.status_code != httpx.codes.OK:
        return Check("API", ok=False, detail=f"Antwort {response.status_code}")
    return Check("API", ok=True, detail="erreichbar")


async def run_checks(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    now: datetime,
) -> list[Check]:
    checks = [await check_api(client, settings.monitor_api_url)]
    checks.append(
        check_age(
            "Worker",
            await asyncio.to_thread(heartbeat, settings.scanner_data_dir / HEARTBEAT_FILE),
            timedelta(minutes=settings.monitor_heartbeat_max_minutes),
            now,
        )
    )
    try:
        async with session_factory() as session:
            last_day = await session.scalar(select(func.max(PortfolioSnapshot.day)))
            last_import = await last_successful_import(session)
    except Exception as exc:  # Datenbank weg – das ist selbst die Störung
        checks.append(Check("Datenbank", ok=False, detail=f"{type(exc).__name__}"))
    else:
        if last_day is not None:  # ohne Sammlungen gibt es keine Tageswerte
            snapshot = datetime.combine(last_day, datetime.min.time(), tzinfo=UTC)
            checks.append(
                check_age(
                    "Preisrunde",
                    snapshot + timedelta(days=1),  # Tageswert entsteht im Laufe des Tages
                    timedelta(hours=settings.monitor_price_run_max_age_hours),
                    now,
                )
            )
        checks.append(
            check_age(
                "Cardmarket-Import",
                last_import,
                timedelta(hours=settings.monitor_cardmarket_max_age_hours),
                now,
            )
        )
    checks.append(
        check_age(
            "Sicherung",
            await asyncio.to_thread(latest_backup, settings.monitor_backup_dir),
            timedelta(hours=settings.monitor_backup_max_age_hours),
            now,
        )
    )
    checks.append(
        await asyncio.to_thread(
            check_disk, settings.monitor_backup_dir, settings.monitor_min_free_disk_percent
        )
    )
    return checks


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    priority: str  # ntfy: min, low, default, high, urgent
    tags: str


@dataclass
class Monitor:
    """Merkt sich den letzten Zustand je Prüfung und entscheidet, was gemeldet wird."""

    remind_after: timedelta
    failing_since: dict[str, datetime] = field(default_factory=dict)
    last_alert: dict[str, datetime] = field(default_factory=dict)

    def evaluate(self, checks: list[Check], now: datetime) -> list[Message]:
        messages = []
        for check in checks:
            if check.ok:
                if self.failing_since.pop(check.name, None) is not None:
                    self.last_alert.pop(check.name, None)
                    messages.append(
                        Message(
                            f"{check.name} wieder in Ordnung",
                            check.detail,
                            "default",
                            "white_check_mark",
                        )
                    )
                continue
            self.failing_since.setdefault(check.name, now)
            last = self.last_alert.get(check.name)
            if last is None or now - last >= self.remind_after:
                self.last_alert[check.name] = now
                again = " (weiterhin)" if last is not None else ""
                messages.append(
                    Message(
                        f"Kartenkiste: {check.name} gestört{again}", check.detail, "high", "warning"
                    )
                )
        return messages


Sender = Callable[[Message], Awaitable[None]]


def ntfy_sender(settings: Settings, client: httpx.AsyncClient) -> Sender:
    """Schickt Nachrichten an ntfy; ohne Thema nur ins Log."""
    topic = settings.ntfy_topic.get_secret_value() if settings.ntfy_topic else None

    async def send(message: Message) -> None:
        log.info("monitor.message", title=message.title, body=message.body)
        if not topic:
            return
        try:
            response = await client.post(
                f"{settings.ntfy_url.rstrip('/')}/{topic}",
                content=message.body.encode(),
                headers={
                    # HTTP-Header sind Latin-1: Umlaute kodiert ntfy über RFC 2047.
                    "Title": f"=?UTF-8?B?{_b64(message.title)}?=",
                    "Priority": message.priority,
                    "Tags": message.tags,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("monitor.ntfy_failed", error=str(exc))

    return send


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


async def run_monitor(
    settings: Settings, *, once: bool = False, clock: Clock = lambda: datetime.now(UTC)
) -> list[Check]:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    monitor = Monitor(remind_after=timedelta(hours=settings.monitor_remind_hours))
    try:
        async with httpx.AsyncClient(
            timeout=20, headers={"User-Agent": settings.http_user_agent}
        ) as client:
            send = ntfy_sender(settings, client)
            if once:
                return await run_checks(settings, session_factory, client, clock())
            await send(
                Message("Kartenkiste: Überwachung läuft", "Nachrichten kommen an.", "low", "eyes")
            )
            while True:
                checks = await run_checks(settings, session_factory, client, clock())
                for message in monitor.evaluate(checks, clock()):
                    await send(message)
                await asyncio.sleep(settings.monitor_interval_minutes * 60)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Überwachung der Kartenkiste")
    parser.add_argument("--once", action="store_true", help="einmal prüfen und ausgeben")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    checks = asyncio.run(run_monitor(settings, once=args.once))
    for check in checks:
        print(f"{'OK  ' if check.ok else 'FEHLER'} {check.name}: {check.detail}")


if __name__ == "__main__":
    main()
