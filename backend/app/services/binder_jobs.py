"""Binder-Scan als Auftrag: Die App bekommt sofort die Felder der Seite und fragt den Stand ab,
während die Karten im Hintergrund nacheinander erkannt werden (eine Seite dauert auf dem Server
rund 15 s – so steht die erste Karte nach etwa 2 s da).

Aufträge liegen nur im Arbeitsspeicher (ein API-Prozess) und verfallen nach
:data:`JOB_TTL_SECONDS`. Jeder Auftrag gehört einem Nutzer; andere sehen ihn nicht.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import User
from app.scanner.runtime import ScannerRuntime
from app.services.scan import BinderCellOutcome, BinderPage, ScanService

log = structlog.get_logger(__name__)

JOB_TTL_SECONDS = 30 * 60
MAX_JOBS = 200

CellSerializer = Callable[[BinderCellOutcome], dict[str, Any]]


@dataclass
class BinderJob:
    id: uuid.UUID
    user_id: uuid.UUID
    method: str
    cells: list[tuple[int, int]]
    results: dict[int, dict[str, Any]] = field(default_factory=dict)
    done: bool = False
    error: str | None = None
    created: float = field(default_factory=time.monotonic)


class BinderJobs:
    """Laufende und kürzlich fertige Binder-Aufträge."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[uuid.UUID, BinderJob] = OrderedDict()
        self._tasks: set[asyncio.Task[None]] = set()  # Referenzen halten (sonst GC)

    def _prune(self) -> None:
        now = time.monotonic()
        for job_id in [j for j, job in self._jobs.items() if now - job.created > JOB_TTL_SECONDS]:
            del self._jobs[job_id]
        while len(self._jobs) > MAX_JOBS:
            self._jobs.popitem(last=False)

    def get(self, job_id: uuid.UUID, user_id: uuid.UUID) -> BinderJob | None:
        self._prune()
        job = self._jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None

    def start(
        self,
        page: BinderPage,
        *,
        user: User,
        runtime: ScannerRuntime,
        session_factory: async_sessionmaker[AsyncSession],
        serialize: CellSerializer,
        language_hint: str | None,
    ) -> BinderJob:
        """Auftrag anlegen und die Erkennung im Hintergrund starten."""
        self._prune()
        job = BinderJob(
            id=uuid.uuid4(),
            user_id=user.id,
            method=page.method,
            cells=[(cell.row, cell.column) for cell in page.cells],
        )
        self._jobs[job.id] = job
        task = asyncio.create_task(
            self._run(
                job,
                page,
                user=user,
                runtime=runtime,
                session_factory=session_factory,
                serialize=serialize,
                language_hint=language_hint,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    @staticmethod
    async def _run(
        job: BinderJob,
        page: BinderPage,
        *,
        user: User,
        runtime: ScannerRuntime,
        session_factory: async_sessionmaker[AsyncSession],
        serialize: CellSerializer,
        language_hint: str | None,
    ) -> None:
        try:
            async with session_factory() as session:
                service = ScanService(session, runtime, user)
                async for index, cell in service.recognize_binder(
                    page, language_hint=language_hint
                ):
                    result = serialize(cell)  # vor dem Commit, solange alles geladen ist
                    await session.commit()  # Protokoll sofort speichern (Bestätigen geht dann)
                    job.results[index] = result
        except Exception:  # Hintergrund: Fehler melden statt still hängen zu bleiben
            log.exception("scan.binder_job_failed", job=str(job.id))
            job.error = "Die Erkennung ist fehlgeschlagen – bitte nochmal versuchen."
        finally:
            job.done = True

    async def wait_all(self) -> None:
        """Für Tests und das Herunterfahren: laufende Aufträge abwarten."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
