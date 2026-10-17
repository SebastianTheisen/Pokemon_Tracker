"""Gzip-Kompression für Text, JSON und die Web-App (CanvasKit-WASM, main.dart.js).

Spart beim ersten Laden der App über Tailscale mehrere Megabyte. Bereits komprimierte
Formate (Bilder, APK) werden unverändert durchgereicht – das spart CPU.
"""

from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

ALREADY_COMPRESSED = (".apk", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip")


class SelectiveGZip:
    """Wie ``GZipMiddleware``, aber nicht für bereits komprimierte Dateien und Bilder."""

    def __init__(self, app: ASGIApp, *, minimum_size: int = 1024) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", "")).lower()
        if scope["type"] == "http" and not (
            path.endswith(ALREADY_COMPRESSED) or path.endswith("/image")
        ):
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)
