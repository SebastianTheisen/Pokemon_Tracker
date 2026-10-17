"""Größenbegrenzung für Uploads – greift, *bevor* der Body gelesen wird.

Ohne diese Middleware würde der Server eine beliebig große Datei erst vollständig
annehmen (zwischenspeichern) und sie danach ablehnen. Hier wird schon am
``Content-Length``-Header bzw. beim Mitzählen der empfangenen Bytes abgebrochen (HTTP 413).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_OVERHEAD = 64 * 1024


class _BodyTooLargeError(Exception):
    pass


class UploadSizeLimit:
    """ASGI-Middleware für alle Pfade mit ``prefix``; ``max_bytes(path)`` liefert das Limit."""

    def __init__(self, app: ASGIApp, *, prefix: str, max_bytes: Callable[[str], int]) -> None:
        self.app = app
        self.prefix = prefix
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope["path"]).startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        limit = self.max_bytes(str(scope["path"]))
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject(send, limit)
            return

        received = 0
        too_large = False
        started = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    raise _BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            # FastAPI fängt Fehler beim Lesen des Formulars ab und antwortet selbst (400).
            # Diese Antwort wird verworfen und durch 413 ersetzt.
            nonlocal started
            if too_large:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        with contextlib.suppress(_BodyTooLargeError):
            await self.app(scope, limited_receive, guarded_send)
        if too_large and not started:
            await _reject(send, limit)


async def _reject(send: Send, limit: int) -> None:
    body = json.dumps(
        {
            "error": {
                "code": "file_too_large",
                "message": f"Upload ist zu groß (höchstens {limit // (1024 * 1024)} MB).",
            }
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
