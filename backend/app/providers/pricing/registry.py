"""Zusammenstellung der aktiven Preisquellen (API und Worker nutzen dieselbe Liste)."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.pricing import PriceProvider
from app.providers.pricing.plugins import load_plugins
from app.providers.pricing.tcgdex_prices import TcgdexPriceProvider
from app.providers.tcgdex import TcgdexClient


def build_price_providers(settings: Settings, client: TcgdexClient) -> list[PriceProvider]:
    """Eingebaute Quelle (TCGdex) plus konfigurierte Plug-ins."""
    return [TcgdexPriceProvider(client), *load_plugins(settings.extra_price_providers, settings)]
