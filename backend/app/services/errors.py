"""Fachliche Fehler. Die API übersetzt sie zentral in HTTP-Antworten (``app.api.errors``)."""

from __future__ import annotations


class ServiceError(Exception):
    """Basisklasse. ``code`` ist maschinenlesbar, die Nachricht für Menschen (Deutsch)."""

    code: str = "error"

    def __init__(
        self, message: str, *, code: str | None = None, persist_changes: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        # True: Änderungen der Transaktion trotz Fehler speichern (z. B. Sperre einer
        # Sitzungsfamilie bei erkanntem Token-Diebstahl, bevor 401 zurückgegeben wird).
        self.persist_changes = persist_changes


class AuthenticationError(ServiceError):
    """Anmeldung fehlgeschlagen oder Token ungültig (HTTP 401)."""

    code = "authentication_failed"


class PermissionDeniedError(ServiceError):
    """Angemeldet, aber nicht berechtigt (HTTP 403)."""

    code = "permission_denied"


class NotFoundError(ServiceError):
    """Objekt existiert nicht – oder gehört jemand anderem (HTTP 404, bewusst kein 403)."""

    code = "not_found"


class ConflictError(ServiceError):
    """Widerspruch zum aktuellen Zustand, z. B. E-Mail schon vergeben (HTTP 409)."""

    code = "conflict"


class InvalidInputError(ServiceError):
    """Fachlich ungültige Eingabe, z. B. abgelaufener Code (HTTP 400)."""

    code = "invalid_input"


class UpstreamError(ServiceError):
    """Ein externer Dienst (z. B. Apify) ist ausgefallen oder lieferte Unbrauchbares (HTTP 502)."""

    code = "upstream_failed"


class RateLimitedError(ServiceError):
    """Zu viele Versuche (HTTP 429)."""

    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
