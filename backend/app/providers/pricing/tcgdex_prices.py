"""Preise aus TCGdex: Cardmarket (EUR) und TCGplayer (USD).

Feldnamen laut Phase-0-Spike: ``pricing.cardmarket.{avg,low,trend,avg1,avg7,avg30}`` für
die normale Variante, dieselben Felder mit Suffix ``-holo`` für **Reverse Holo** (so heißen
die Spalten im Cardmarket-Preisführer). ``pricing.tcgplayer.<variante>.{lowPrice,…}``.
Werte ``0`` oder ``null`` bedeuten „kein Preis“ und werden verworfen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlsplit

from app.providers.pricing import CardRef, PriceKind, PriceNotAvailableError, PriceQuote
from app.providers.tcgdex import TcgdexClient, TcgdexError

HTTP_NOT_FOUND = 404
CARDMARKET = "cardmarket"
TCGPLAYER = "tcgplayer"
CARDMARKET_METRICS = ("trend", "low", "avg", "avg1", "avg7", "avg30")
TCGPLAYER_METRICS = {
    "marketPrice": "market",
    "lowPrice": "low",
    "midPrice": "mid",
    "highPrice": "high",
    "directLowPrice": "direct_low",
}
TCGPLAYER_VARIANTS = {
    "normal": "normal",
    "holofoil": "holo",
    "reverse-holofoil": "reverse",
    "1st-edition": "1st_edition",
    "1st-edition-holofoil": "1st_edition_holo",
    "unlimited": "normal",
    "unlimited-holofoil": "holo",
}


# Pfad je Spiel auf cardmarket.com (``/de/OnePiece/Products?idProduct=…``).
CARDMARKET_URL_NAMES = {"pokemon": "Pokemon", "onepiece": "OnePiece"}


def cardmarket_url(card: CardRef, product_id: object) -> str:
    """Beleglink: direkt per Produkt-ID, sonst Cardmarket-Suche (beide vom Nutzer geprüft)."""
    base = f"https://www.cardmarket.com/de/{CARDMARKET_URL_NAMES.get(card.game, 'Pokemon')}"
    # bool ist in Python ein int – ein fehlerhaftes ``true`` darf keinen Link ergeben.
    if isinstance(product_id, int) and not isinstance(product_id, bool) and product_id > 0:
        return f"{base}/Products?idProduct={product_id}"
    query = quote_plus(f"{card.name} {card.number}")
    return f"{base}/Products/Search?searchString={query}"


def product_id_from_url(url: str | None) -> int | None:
    """Cardmarket-Produkt-ID aus einem Beleglink (``…/Products?idProduct=908315``)."""
    if not url:
        return None
    values = parse_qs(urlsplit(url).query).get("idProduct", [])
    if len(values) != 1 or not values[0].isdigit():
        return None
    product_id = int(values[0])
    return product_id if product_id > 0 else None


def _amount(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def _timestamp(value: object, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return fallback


def parse_pricing(card: CardRef, pricing: dict[str, Any], *, now: datetime) -> list[PriceQuote]:
    """Wandelt den TCGdex-Block ``pricing`` in belegte Preiswerte um."""
    # Ohne Zeitstempel der Quelle: Tagesbeginn – mehrfacher Abruf am selben Tag erzeugt
    # so keine doppelten Historienpunkte.
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    quotes: list[PriceQuote] = []

    cardmarket = pricing.get(CARDMARKET)
    if isinstance(cardmarket, dict):
        updated = _timestamp(cardmarket.get("updated"), day_start)
        currency = str(cardmarket.get("unit") or "EUR")[:3]
        url = cardmarket_url(card, cardmarket.get("idProduct"))
        for variant, suffix in (("normal", ""), ("reverse", "-holo")):
            for metric in CARDMARKET_METRICS:
                if (value := _amount(cardmarket.get(f"{metric}{suffix}"))) is not None:
                    quotes.append(
                        PriceQuote(CARDMARKET, variant, metric, value, currency, updated, url)
                    )

    tcgplayer = pricing.get(TCGPLAYER)
    if isinstance(tcgplayer, dict):
        updated = _timestamp(tcgplayer.get("updated"), day_start)
        currency = str(tcgplayer.get("unit") or "USD")[:3]
        for raw_variant, block in tcgplayer.items():
            if not isinstance(block, dict):
                continue
            variant = TCGPLAYER_VARIANTS.get(raw_variant, raw_variant[:32])
            product_id = block.get("productId")
            product_url: str | None = (
                f"https://www.tcgplayer.com/product/{product_id}"
                if isinstance(product_id, int)
                else None
            )
            for raw_metric, metric in TCGPLAYER_METRICS.items():
                if (value := _amount(block.get(raw_metric))) is not None:
                    quotes.append(
                        PriceQuote(
                            TCGPLAYER, variant, metric, value, currency, updated, product_url
                        )
                    )
    return quotes


class TcgdexPriceProvider:
    """Eingebaute, belegte Preisquelle (kostenlos)."""

    name = "tcgdex"
    kind: PriceKind = "verified"

    def __init__(self, client: TcgdexClient) -> None:
        self._client = client

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        if card.game != "pokemon":
            raise PriceNotAvailableError("TCGdex kennt nur Pokémon")
        if card.external_id is None:
            return []  # selbst angelegte Karte – TCGdex kennt sie nicht
        try:
            data = await self._client.get_card(card.language, card.external_id)
        except TcgdexError as exc:
            if exc.status_code == HTTP_NOT_FOUND:
                raise PriceNotAvailableError(str(exc)) from exc
            raise
        pricing = data.get("pricing")
        if not isinstance(pricing, dict):
            return []
        return parse_pricing(card, pricing, now=datetime.now(UTC))
