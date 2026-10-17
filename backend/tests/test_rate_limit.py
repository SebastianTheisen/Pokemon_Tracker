"""Unit-Tests für den Fehlversuch-Limiter (mit steuerbarer Uhr)."""

from __future__ import annotations

from app.services.rate_limit import FailureLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_blocks_after_max_failures_and_recovers_after_window() -> None:
    clock = FakeClock()
    limiter = FailureLimiter(max_failures=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert limiter.retry_after("k") == 0
        limiter.register_failure("k")

    assert limiter.retry_after("k") > 0
    clock.now += 61
    assert limiter.retry_after("k") == 0


def test_expired_and_unused_keys_do_not_accumulate() -> None:
    clock = FakeClock()
    limiter = FailureLimiter(max_failures=3, window_seconds=60, clock=clock)

    for index in range(100):
        limiter.retry_after(f"nur-geprueft-{index}")
    limiter.register_failure("alt")
    assert len(limiter) == 1

    clock.now += 61
    assert limiter.retry_after("alt") == 0
    assert len(limiter) == 0


def test_keys_are_independent_and_reset_clears() -> None:
    limiter = FailureLimiter(max_failures=1, window_seconds=60, clock=FakeClock())
    limiter.register_failure("a")

    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0
    limiter.reset("a")
    assert limiter.retry_after("a") == 0
