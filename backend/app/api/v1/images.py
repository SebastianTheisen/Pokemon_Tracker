"""Kartenbilder in passender Größe vom eigenen Server (siehe ``services.image_proxy``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.services.image_proxy import ImageProxy, ImageProxyError

router = APIRouter(tags=["images"])

CACHE_SECONDS = 30 * 24 * 3600


@router.get("/images", response_model=None)
async def image(
    request: Request,
    url: Annotated[str, Query(min_length=8, max_length=1000)],
    w: Annotated[int, Query(ge=16, le=2000)] = 400,
) -> Response:
    """Verkleinertes Bild (WebP). Ohne Anmeldung, weil Bild-Elemente keine Tokens mitschicken –
    dafür nur Hosts aus der Freigabeliste. Sonst 404 (keine Weiterleitung: kein offener
    Redirect); die App lädt dann das Original wie bisher."""
    proxy: ImageProxy = request.app.state.image_proxy
    if not proxy.allowed(url):
        return Response(status_code=404)
    try:
        data = await proxy.thumbnail(url, w)
    except ImageProxyError:
        return Response(status_code=502)
    return Response(
        data,
        media_type="image/webp",
        headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}, immutable"},
    )
