"""Lasttest (Phase 6): Wie schnell bleibt der Server unter gleichzeitiger Nutzung?

Läuft im api-Container gegen die echte Datenbank, ändert nichts:

* 200 Health-Abrufe über HTTP, 20 gleichzeitig (Web-Server + Datenbank-Verbindung)
* 100 Kartensuchen, 10 gleichzeitig (Name, Nummer, Kürzel, Japanisch)
* Sammlungswert für 2.000 zufällige Karten (wie eine große Sammlung), 5× hintereinander

Aufruf: ``docker compose exec -T api python - < deploy/spikes/loadtest.py``
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.models import Card
from app.services.catalog_search import search_cards
from app.services.price_health import SourceHealth
from app.services.pricing import PriceService

QUERIES = ["glurak", "pikachu 25", "nachtara 215", "PFL077", "s6a095", "リザードン", "mewtu ex",
           "evoli", "umbreon vmax", "lugia v 186"]  # fmt: skip


def report(name: str, durations: list[float]) -> None:
    ordered = sorted(durations)
    p95 = ordered[int(len(ordered) * 0.95) - 1]
    print(
        f"| {name} | {len(ordered)} | {statistics.median(ordered) * 1000:.0f} ms "
        f"| {p95 * 1000:.0f} ms | {ordered[-1] * 1000:.0f} ms |"
    )


async def measured(
    count: int, parallel: int, task: Callable[[int], Awaitable[object]]
) -> list[float]:
    semaphore = asyncio.Semaphore(parallel)
    durations: list[float] = []

    async def one(index: int) -> None:
        async with semaphore:
            started = time.perf_counter()
            await task(index)
            durations.append(time.perf_counter() - started)

    await asyncio.gather(*(one(i) for i in range(count)))
    return durations


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_size=10, max_overflow=10)
    factory = create_session_factory(engine)
    print("# Lasttest\n")
    print("| Messung | Anzahl | Median | 95 % | Max |")
    print("|---|---:|---:|---:|---:|")

    async with httpx.AsyncClient(timeout=30) as client:

        async def health(_: int) -> None:
            (await client.get("http://127.0.0.1:8000/api/v1/health")).raise_for_status()

        report("Health über HTTP (20 parallel)", await measured(200, 20, health))

    async def search(index: int) -> None:
        async with factory() as session:
            await search_cards(session, QUERIES[index % len(QUERIES)])

    report("Kartensuche (10 parallel)", await measured(100, 10, search))

    async with factory() as session:
        total = await session.scalar(select(func.count()).select_from(Card)) or 0
        ids = list((await session.scalars(select(Card.id).limit(50_000))).all())
    sample = random.Random(7).sample(ids, min(2000, len(ids)))  # noqa: S311 – Stichprobe
    health_state = SourceHealth(threshold=5, pause=timedelta(minutes=5))

    async def valuation(_: int) -> None:
        async with factory() as session:
            await PriceService(session, settings, [], health_state).prices_for_cards(sample, None)

    report(f"Sammlungswert {len(sample)} Karten (nacheinander)", await measured(5, 1, valuation))
    print(f"\nKatalog: {total} Karten")
    await engine.dispose()


asyncio.run(main())
