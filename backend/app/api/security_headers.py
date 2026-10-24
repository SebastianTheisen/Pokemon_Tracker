"""Sicherheits-Header für alle Antworten (API und Web-App).

* ``X-Content-Type-Options: nosniff`` – der Browser rät keine Dateitypen.
* ``X-Frame-Options: DENY`` – die App lässt sich nicht in fremde Seiten einbetten.
* ``Referrer-Policy: no-referrer`` – Links zu Cardmarket/eBay verraten die Tailnet-Adresse nicht.
* ``Permissions-Policy`` – Kamera nur für die App selbst, Mikrofon/Standort gar nicht.
* ``Strict-Transport-Security`` – die App ist nur per HTTPS (Tailscale) erreichbar.

Eine Content-Security-Policy fehlt bewusst: Die Flutter-Web-App braucht dafür Ausnahmen
(WASM, Inline-Skripte), die ihren Nutzen weitgehend aufheben.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(self), microphone=(), geolocation=()"),
    (b"strict-transport-security", b"max-age=31536000"),
)


class SecurityHeaders:
    """Hängt :data:`HEADERS` an jede HTTP-Antwort (vorhandene gleichen Namens bleiben)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers += [(name, value) for name, value in HEADERS if name not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
