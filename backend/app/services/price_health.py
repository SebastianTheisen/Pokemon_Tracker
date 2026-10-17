"""Gesundheit der Preisquellen („Sicherung“): pausiert eine Quelle nach Fehlern in Folge.

Gilt je Prozess (API und Worker getrennt) – bei 5–10 Nutzern ausreichend. Der Zustand ist
für den Admin-Bereich abrufbar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class SourceStatus:
    """Momentaufnahme einer Quelle."""

    name: str
    consecutive_failures: int = 0
    paused_until: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    last_success_at: datetime | None = None


class SourceHealth:
    """Zählt Fehler je Quelle und pausiert sie nach ``threshold`` Fehlern für ``pause``."""

    def __init__(
        self,
        *,
        threshold: int,
        pause: timedelta,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._threshold = threshold
        self._pause = pause
        self._now = clock
        self._sources: dict[str, SourceStatus] = {}

    def _status(self, name: str) -> SourceStatus:
        return self._sources.setdefault(name, SourceStatus(name=name))

    def is_paused(self, name: str) -> bool:
        paused_until = self._status(name).paused_until
        return paused_until is not None and paused_until > self._now()

    def record_success(self, name: str) -> None:
        status = self._status(name)
        status.consecutive_failures = 0
        status.paused_until = None
        status.last_success_at = self._now()

    def record_failure(self, name: str, error: str) -> None:
        status = self._status(name)
        status.consecutive_failures += 1
        status.last_error = error[:300]
        status.last_error_at = self._now()
        if status.consecutive_failures >= self._threshold:
            status.paused_until = self._now() + self._pause

    def snapshot(self, names: list[str]) -> list[SourceStatus]:
        return [self._status(name) for name in names]
