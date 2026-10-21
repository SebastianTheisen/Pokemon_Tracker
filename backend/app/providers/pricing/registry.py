"""Zusammenstellung der aktiven Preisquellen (API und Worker nutzen dieselbe Liste)."""

from __future__ import annotations

from app.core.config import Settings
from app.providers.apify import ApifyClient
from app.providers.fx import EcbRates
from app.providers.pricing import PriceProvider
from app.providers.pricing.plugins import load_plugins
from app.providers.pricing.pricecharting import PriceChartingProvider
from app.providers.pricing.tcgdex_prices import TcgdexPriceProvider
from app.providers.tcgdex import TcgdexClient


def build_price_providers(settings: Settings, client: TcgdexClient) -> list[PriceProvider]:
    """Eingebaute Quelle (TCGdex), Plug-ins und – mit Apify-Token – PriceCharting.

    PriceCharting steht am Ende: Es springt nur ein, wenn die Quellen davor keinen
    Cardmarket-Preis geliefert haben (oder für Slabs).
    """
    providers: list[PriceProvider] = [
        TcgdexPriceProvider(client),
        *load_plugins(settings.extra_price_providers, settings),
    ]
    token = settings.apify_token
    if settings.pricecharting_enabled and token is not None and token.get_secret_value():
        rates = EcbRates(user_agent=settings.http_user_agent, url=settings.ecb_rates_url)

        def apify() -> ApifyClient:
            return ApifyClient(token.get_secret_value(), user_agent=settings.http_user_agent)

        providers.append(PriceChartingProvider(settings, rates, apify))
    return providers
