"""Einstiegspunkt der FastAPI-Anwendung."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.compression import SelectiveGZip
from app.api.errors import register_error_handlers
from app.api.limits import MULTIPART_OVERHEAD, UploadSizeLimit
from app.api.security_headers import SecurityHeaders
from app.api.v1 import api_router
from app.api.web import mount_web_app
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.providers.apify import ApifyClient
from app.providers.pricing import PriceProvider
from app.providers.pricing.registry import build_price_providers
from app.providers.psa import PsaClient
from app.providers.tcgdex import TcgdexClient
from app.scanner.ocr import RapidOcrReader, TextReader
from app.scanner.runtime import ScannerRuntime
from app.services.image_proxy import ImageProxy
from app.services.price_health import SourceHealth
from app.services.rate_limit import FailureLimiter


def create_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    price_providers: Sequence[PriceProvider] | None = None,
    text_reader: TextReader | None = None,
    image_transport: httpx.AsyncBaseTransport | None = None,
    apify_transport: httpx.AsyncBaseTransport | None = None,
    psa_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Erzeugt die Anwendung (Factory, damit Tests Settings, Engine, Preisquellen,
    Texterkennung, Bild-Downloads und Apify ersetzen können)."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own_engine = engine is None
        app_engine = engine or create_engine(settings.database_url)
        app.state.engine = app_engine
        app.state.session_factory = create_session_factory(app_engine)
        async with (
            TcgdexClient(
                base_url=settings.tcgdex_base_url, user_agent=settings.http_user_agent
            ) as tcgdex,
            httpx.AsyncClient(
                transport=image_transport,
                timeout=15.0,
                follow_redirects=True,  # nur erlaubte Hosts werden überhaupt angefragt
                headers={"User-Agent": settings.http_user_agent},
            ) as image_client,
        ):
            app.state.price_providers = (
                list(price_providers)
                if price_providers is not None
                else build_price_providers(settings, tcgdex)
            )
            app.state.image_proxy = ImageProxy(
                image_client,
                settings.scanner_data_dir / "image-cache",
                allowed_hosts=[*settings.scanner_image_hosts, *settings.image_proxy_extra_hosts],
            )
            app.state.scanner = ScannerRuntime(
                settings, text_reader or RapidOcrReader(), image_client
            )
            # eBay.de-Verkäufe auf Knopfdruck – nur mit Token in der .env.
            token = settings.apify_token.get_secret_value() if settings.apify_token else ""
            app.state.apify = (
                ApifyClient(token, user_agent=settings.http_user_agent, transport=apify_transport)
                if token
                else None
            )
            # PSA-Zertifikate beim Slab-Scan prüfen – nur mit Token in der .env.
            psa_token = settings.psa_token.get_secret_value() if settings.psa_token else ""
            app.state.psa = (
                PsaClient(psa_token, user_agent=settings.http_user_agent, transport=psa_transport)
                if psa_token
                else None
            )
            try:
                yield
            finally:
                if app.state.apify is not None:
                    await app.state.apify.aclose()
                if app.state.psa is not None:
                    await app.state.psa.aclose()
        if own_engine:
            await app_engine.dispose()

    app = FastAPI(
        title="Pokemon Tracker API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.price_health = SourceHealth(
        threshold=settings.price_breaker_threshold,
        pause=timedelta(minutes=settings.price_breaker_pause_minutes),
    )
    app.state.login_limiter = FailureLimiter(
        max_failures=settings.login_rate_limit, window_seconds=settings.login_rate_window_seconds
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def scan_upload_limit(path: str) -> int:
        files = settings.scan_batch_max if path.endswith("/batch") else 1
        return files * settings.scan_max_upload_mb * 1024 * 1024 + MULTIPART_OVERHEAD

    app.add_middleware(SelectiveGZip)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(UploadSizeLimit, prefix="/api/v1/scan", max_bytes=scan_upload_limit)
    register_error_handlers(app)
    app.include_router(api_router)
    mount_web_app(app, settings.web_dir)  # zuletzt: fängt alle übrigen Pfade ab
    return app


app = create_app()
