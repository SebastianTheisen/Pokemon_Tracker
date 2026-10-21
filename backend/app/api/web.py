"""Auslieferung der Flutter-Web-App (PWA) unter ``/`` – gleiche Adresse wie die API.

* Unbekannte Pfade (z. B. ``/card/123`` beim Neuladen) liefern ``index.html``, damit die
  App ihr eigenes Routing übernimmt.
* ``/api/...`` wird nie umgeleitet: Fehler der API bleiben JSON.
* Alles wird vor jeder Nutzung beim Server nachgefragt (``no-cache``): Flutter benennt seine
  Dateien nicht nach Inhalt (``main.dart.js`` heißt nach jedem Update gleich). Sonst mischt
  Safari nach einem Update alte und neue Dateien, und die App startet nicht. Unveränderte
  Dateien kosten dank ETag nur eine kurze 304-Antwort.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

log = structlog.get_logger(__name__)


class SpaStaticFiles(StaticFiles):
    """Statische Dateien mit Rückfall auf ``index.html`` (Single-Page-App)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):  # noqa: PLR2004
                raise
            response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def mount_web_app(app: FastAPI, web_dir: Path | None) -> bool:
    """Hängt die Web-App ein, wenn ein Build vorhanden ist. Gibt ``True`` zurück, wenn ja."""
    if web_dir is None:
        return False
    if not (web_dir / "index.html").is_file():
        log.warning("web.build_missing", web_dir=str(web_dir))
        return False
    app.mount("/", SpaStaticFiles(directory=web_dir, html=True), name="web")
    return True
