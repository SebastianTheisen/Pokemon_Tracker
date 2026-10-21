"""Auslieferung der Flutter-Web-App unter / (Rückfall auf index.html, API bleibt JSON)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.main import create_app
from tests.pricing_helpers import FakeProvider


@pytest.fixture
def web_dir(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>Kartenkiste</html>", encoding="utf-8")
    (web / "main.dart.js").write_text("console.log(1);" * 200, encoding="utf-8")
    (web / "flutter_service_worker.js").write_text("// sw", encoding="utf-8")
    (web / "assets" / "logo.png").write_bytes(b"png")
    return web


async def _client(
    settings: Settings, engine: AsyncEngine, web: Path | None
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        settings.model_copy(update={"web_dir": web}),
        engine=engine,
        price_providers=[FakeProvider()],
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


async def test_web_app_is_served_with_spa_fallback(
    settings: Settings, engine: AsyncEngine, web_dir: Path
) -> None:
    async for client in _client(settings, engine, web_dir):
        index = await client.get("/")
        assert index.status_code == 200
        assert "Kartenkiste" in index.text
        assert index.headers["cache-control"] == "no-cache"

        deep_link = await client.get("/card/123")  # Neuladen auf einer App-Seite
        assert deep_link.status_code == 200
        assert "Kartenkiste" in deep_link.text

        big = await client.get("/main.dart.js", headers={"Accept-Encoding": "gzip"})
        assert big.headers.get("content-encoding") == "gzip"  # Web-App komprimiert
        logo = await client.get("/assets/logo.png", headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in logo.headers  # Bilder nicht

        script = await client.get("/main.dart.js")
        assert script.text == "console.log(1);" * 200
        assert script.headers["cache-control"] == "no-cache"  # Name ohne Inhalts-Hash
        etag = script.headers["etag"]
        unchanged = await client.get("/main.dart.js", headers={"If-None-Match": etag})
        assert unchanged.status_code == 304  # Nachfragen kostet fast nichts
        assert (await client.get("/flutter_service_worker.js")).headers["cache-control"] == (
            "no-cache"
        )
        assert (await client.get("/assets/logo.png")).content == b"png"

        # Die API bleibt API: Health geht, unbekannte API-Pfade sind JSON-404.
        assert (await client.get("/api/v1/health")).json()["status"] == "ok"
        missing = await client.get("/api/v1/gibt-es-nicht")
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith("application/json")


async def test_without_build_only_the_api_is_served(
    settings: Settings, engine: AsyncEngine, tmp_path: Path
) -> None:
    async for client in _client(settings, engine, tmp_path / "leer"):
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/api/v1/health")).status_code == 200
