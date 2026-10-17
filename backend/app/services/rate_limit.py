"""Einfacher In-Memory-Limiter für fehlgeschlagene Anmeldeversuche.

Reicht für einen einzelnen API-Prozess (5–10 Nutzer). Bei mehreren Prozessen müsste der
Zähler in die Datenbank oder einen gemeinsamen Speicher wandern.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class FailureLimiter:
    """Zählt Fehlversuche je Schlüssel in einem gleitenden Zeitfenster."""

    def __init__(
        self,
        *,
        max_failures: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _prune(self, key: str) -> deque[float]:
        """Entfernt abgelaufene Einträge; leere Schlüssel verschwinden ganz (kein Speicherleck)."""
        entries = self._failures.get(key)
        if entries is None:
            return deque()
        cutoff = self._clock() - self._window
        while entries and entries[0] <= cutoff:
            entries.popleft()
        if not entries:
            del self._failures[key]
        return entries

    def retry_after(self, key: str) -> int:
        """Sekunden bis zum nächsten erlaubten Versuch; ``0`` = jetzt erlaubt."""
        entries = self._prune(key)
        if len(entries) < self._max_failures:
            return 0
        return max(1, int(entries[0] + self._window - self._clock()) + 1)

    def register_failure(self, key: str) -> None:
        self._prune(key)
        self._failures.setdefault(key, deque()).append(self._clock())

    def __len__(self) -> int:
        """Anzahl der Schlüssel mit aktiven Fehlversuchen (für Tests/Monitoring)."""
        return len(self._failures)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
