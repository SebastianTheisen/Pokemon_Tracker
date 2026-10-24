"""Tests für den Health-Check."""

from __future__ import annotations

from httpx import AsyncClient

from app import __version__


async def test_health_reports_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/api/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"/api/v1/health", "/api/v1/auth/login", "/api/v1/cards/search"} <= set(paths)


async def test_security_headers_on_every_response(client: AsyncClient) -> None:
    for path in ("/api/v1/health", "/api/v1/cards/search?q=x"):  # auch bei 401
        response = await client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "camera=(self)" in response.headers["permissions-policy"]
