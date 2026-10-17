"""Auswertung des TCGdex-Preisblocks – mit der echten Antwort aus dem Phase-0-Spike."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.providers.pricing import CardRef, PriceNotAvailableError
from app.providers.pricing.tcgdex_prices import TcgdexPriceProvider, cardmarket_url, parse_pricing
from app.providers.tcgdex import TcgdexClient, TcgdexError

CARD = CardRef(
    card_id=uuid.uuid4(),
    external_id="swsh7-215",
    language="de",
    name="Nachtara VMAX",
    number="215",
    set_name="Drachenwandel",
)
NOW = datetime(2026, 10, 17, 14, 30, tzinfo=UTC)

# Rohdaten aus docs/spikes/datenquellen.md (VPS-Lauf 1)
SPIKE_PRICING = {
    "cardmarket": {
        "updated": "2026-10-16T08:51:36.575Z",
        "unit": "EUR",
        "idProduct": 574273,
        "avg": 1830.92,
        "low": 220,
        "trend": 1805.9,
        "avg1": 1150,
        "avg7": 2249.8,
        "avg30": 1772.15,
        "avg-holo": None,
        "low-holo": None,
        "trend-holo": 0,
        "avg1-holo": None,
        "avg7-holo": None,
        "avg30-holo": None,
    },
    "tcgplayer": {
        "unit": "USD",
        "updated": "2026-10-15T08:51:55.117Z",
        "holofoil": {
            "productId": 246723,
            "lowPrice": 1699.99,
            "midPrice": 2264.7,
            "highPrice": 23406.19,
            "marketPrice": 2264.7,
            "directLowPrice": 2850,
        },
    },
}


def test_parses_cardmarket_values_with_date_and_link() -> None:
    quotes = parse_pricing(CARD, SPIKE_PRICING, now=NOW)
    cardmarket = {q.metric: q for q in quotes if q.source == "cardmarket"}

    assert set(cardmarket) == {"trend", "low", "avg", "avg1", "avg7", "avg30"}
    assert cardmarket["trend"].value == Decimal("1805.90")
    assert cardmarket["low"].value == Decimal("220.00")
    assert all(q.variant == "normal" and q.currency == "EUR" for q in cardmarket.values())
    assert cardmarket["trend"].source_updated_at == datetime(
        2026, 10, 16, 8, 51, 36, 575000, tzinfo=UTC
    )
    assert cardmarket["trend"].source_url == (
        "https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273"
    )


def test_zero_and_missing_values_are_not_prices() -> None:
    quotes = parse_pricing(CARD, SPIKE_PRICING, now=NOW)

    assert not [q for q in quotes if q.source == "cardmarket" and q.variant == "reverse"]


def test_parses_tcgplayer_variants_in_usd() -> None:
    quotes = [q for q in parse_pricing(CARD, SPIKE_PRICING, now=NOW) if q.source == "tcgplayer"]

    assert {q.metric for q in quotes} == {"market", "low", "mid", "high", "direct_low"}
    assert {q.variant for q in quotes} == {"holo"}
    market = next(q for q in quotes if q.metric == "market")
    assert (market.value, market.currency) == (Decimal("2264.70"), "USD")
    assert market.source_url == "https://www.tcgplayer.com/product/246723"


def test_reverse_holo_fields_and_missing_timestamp() -> None:
    pricing = {"cardmarket": {"trend-holo": 3.5, "low-holo": "1.2", "trend": "abc"}}

    quotes = parse_pricing(CARD, pricing, now=NOW)

    assert {(q.variant, q.metric, q.value) for q in quotes} == {
        ("reverse", "trend", Decimal("3.50")),
        ("reverse", "low", Decimal("1.20")),
    }
    # Ohne Zeitstempel der Quelle: Tagesbeginn (verhindert doppelte Tagespunkte).
    assert all(q.source_updated_at == datetime(2026, 10, 17, tzinfo=UTC) for q in quotes)
    assert quotes[0].source_url == (
        "https://www.cardmarket.com/de/Pokemon/Products/Search?searchString=Nachtara+VMAX+215"
    )


@pytest.mark.parametrize("product_id", [None, 0, "574273", True])
def test_cardmarket_url_falls_back_to_search(product_id: object) -> None:
    assert "Search?searchString=" in cardmarket_url(CARD, product_id)


def _client(handler: httpx.MockTransport) -> TcgdexClient:
    return TcgdexClient(base_url="https://api.tcgdex.net/v2", user_agent="t", transport=handler)


async def test_provider_fetches_card_and_parses_prices() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        return httpx.Response(200, json={"id": "swsh7-215", "pricing": SPIKE_PRICING})

    async with _client(httpx.MockTransport(handler)) as client:
        quotes = await TcgdexPriceProvider(client).fetch(CARD)

    assert seen == ["/v2/de/cards/swsh7-215"]
    assert len(quotes) == 11


async def test_provider_maps_404_to_not_available_and_keeps_other_errors() -> None:
    status = {"code": 404}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status["code"])

    async with _client(httpx.MockTransport(handler)) as client:
        provider = TcgdexPriceProvider(client)
        with pytest.raises(PriceNotAvailableError):
            await provider.fetch(CARD)
        status["code"] = 503
        with pytest.raises(TcgdexError):
            await provider.fetch(CARD)


async def test_provider_skips_user_cards_and_cards_without_pricing() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x"})

    async with _client(httpx.MockTransport(handler)) as client:
        provider = TcgdexPriceProvider(client)
        assert await provider.fetch(CARD) == []
        own_card = CardRef(**{**CARD.__dict__, "external_id": None})
        assert await provider.fetch(own_card) == []
