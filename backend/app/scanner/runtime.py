"""Bündelt alles, was der Scanner zur Laufzeit braucht (lebt in ``app.state.scanner``)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.scanner.catalog_images import CatalogImageIndex
from app.scanner.ocr import TextReader
from app.scanner.storage import FeatureCache, PendingScans, ReferenceStore


class ScannerRuntime:
    """Texterkennung, Katalogbild-Index, Referenzbilder, offene Scans und CPU-Begrenzung.

    OCR und Bildabgleich blockieren die CPU. Sie laufen in Threads, begrenzt durch
    ``PT_SCANNER_CONCURRENCY`` – so bleibt die API für andere Anfragen ansprechbar.
    """

    def __init__(self, settings: Settings, reader: TextReader, client: httpx.AsyncClient) -> None:
        root = settings.scanner_data_dir
        self.settings = settings
        self.reader = reader
        self.references = ReferenceStore(root)
        self.pending = PendingScans(ttl_seconds=settings.scan_pending_minutes * 60)
        self._cpu = asyncio.Semaphore(settings.scanner_concurrency)
        self.catalog_images = CatalogImageIndex(
            FeatureCache(root),
            client,
            self.run_cpu,
            allowed_hosts=settings.scanner_image_hosts,
        )

    async def run_cpu(self, func: Callable[..., Any], *args: Any) -> Any:
        """Führt CPU-Arbeit in einem Thread aus (höchstens ``scanner_concurrency`` zugleich)."""
        async with self._cpu:
            return await asyncio.to_thread(func, *args)
