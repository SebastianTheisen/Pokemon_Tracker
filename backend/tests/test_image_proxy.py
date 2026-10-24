"""Bilder über den eigenen Server: nur freigegebene Hosts, verkleinert, gemerkt."""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.main import create_app
from app.services.image_proxy import ImageProxy, ImageProxyError, width_bucket

API = "/api/v1"
JP_IMAGE = "https://www.pokemon-card.com/assets/images/card_images/large/SV2a/043844_P_X.jpg"


def _jpeg(width: int = 734, height: int = 1024) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(out, "JPEG")
    return out.getvalue()


class Origin:
    """Bildserver zum Mitzählen (statt Netz)."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "redirect.pokemon-card.com":
            return httpx.Response(302, headers={"Location": "https://evil.example.org/x.jpg"})
        if request.url.path.endswith("kaputt.jpg"):
            return httpx.Response(200, content=b"kein bild")
        return httpx.Response(200, content=_jpeg(), headers={"Content-Type": "image/jpeg"})


@pytest.fixture
def origin() -> Origin:
    return Origin()


@pytest.fixture
async def image_client(
    settings: Settings, engine: AsyncEngine, tmp_path: Path, origin: Origin
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        settings.model_copy(update={"scanner_data_dir": tmp_path}),
        engine=engine,
        price_providers=[],
        image_transport=httpx.MockTransport(origin.handler),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


def test_width_buckets() -> None:
    widths = [width_bucket(w) for w in (16, 160, 161, 330, 799, 2000)]
    assert widths == [160, 160, 240, 480, 800, 800]


async def test_thumbnail_is_small_webp_and_cached(
    image_client: AsyncClient, origin: Origin
) -> None:
    first = await image_client.get(f"{API}/images", params={"url": JP_IMAGE, "w": 330})
    assert first.status_code == 200, first.text
    assert first.headers["content-type"] == "image/webp"
    assert "immutable" in first.headers["cache-control"]
    with Image.open(io.BytesIO(first.content)) as image:
        assert image.size == (480, 670)  # Stufe 480, Seitenverhältnis bleibt
    assert len(first.content) < 60_000

    again = await image_client.get(f"{API}/images", params={"url": JP_IMAGE, "w": 380})
    assert again.content == first.content
    assert len(origin.requests) == 1  # zweites Mal aus dem Datei-Cache


async def test_only_allowed_hosts_and_no_open_redirect(
    image_client: AsyncClient, origin: Origin
) -> None:
    for url in (
        "https://evil.example.org/x.jpg",
        "http://www.pokemon-card.com/a.jpg",
        "file:///etc",
    ):
        response = await image_client.get(f"{API}/images", params={"url": url})
        assert response.status_code == 404, url
        assert "location" not in response.headers
    broken = await image_client.get(
        f"{API}/images", params={"url": "https://www.pokemon-card.com/kaputt.jpg"}
    )
    assert broken.status_code == 502
    assert all("evil" not in url for url in origin.requests)  # nie angefragt


async def test_redirect_to_foreign_host_is_refused(tmp_path: Path) -> None:
    origin = Origin()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(origin.handler), follow_redirects=True
    ) as client:
        proxy = ImageProxy(client, tmp_path, allowed_hosts=["redirect.pokemon-card.com"])
        with pytest.raises(ImageProxyError):
            await proxy.thumbnail("https://redirect.pokemon-card.com/a.jpg", 200)
    assert not await asyncio.to_thread(lambda: list(tmp_path.rglob("*.webp")))
    assert origin.requests == ["https://redirect.pokemon-card.com/a.jpg"]  # Ziel nie angefragt
