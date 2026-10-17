"""Strukturiertes Logging mit structlog."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Richtet structlog und das Standard-Logging einheitlich ein.

    Args:
        level: Minimales Log-Level, z. B. ``"INFO"``.
        json_output: ``True`` für JSON-Zeilen (Produktion), sonst farbige Konsolenausgabe.
    """
    log_level = logging.getLevelNamesMapping()[level]
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level, force=True)
    # httpx/httpcore loggen sonst jede einzelne Anfrage auf INFO.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )
