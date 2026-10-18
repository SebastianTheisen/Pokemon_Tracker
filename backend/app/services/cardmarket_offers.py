"""Cardmarket-Angebote, die der Nutzer selbst ausgelesen hat (Lesezeichen in seinem Browser).

Unser Server darf Cardmarket nicht abrufen (Cloudflare-Sperre, keine Umgehung). Der Nutzer
öffnet die Angebotsseite einer Karte deshalb selbst – vorgefiltert nach Sprache und Zustand
(Link aus der App) – und tippt auf das Lesezeichen „An Kartenkiste senden“. Es liest die
sichtbaren Angebote ab (Zustand, Sprache, Besonderheiten, Preis) und gibt sie an die App,
die sie hierher schickt. Erst nach der Vorschau werden sie gespeichert.

Berechnung je Variante (normal / Reverse Holo) und Zustand Z:

* berücksichtigt werden Angebote **in der Sprache der Karte** im Zustand Z **oder besser**
  (wer „EX“ sucht, kauft auch eine NM-Karte zum gleichen Preis),
* ``low`` = günstigstes Angebot, ``low3`` = Durchschnitt der drei günstigsten,
* ein Zustand wird nur ausgewertet, wenn die Seite ihn nicht weggefiltert hat (Filter
  „ab NM“ blendet EX-Angebote aus – deren Preis wäre sonst zu hoch).

Cardmarket sortiert die Angebote nach Preis; die günstigsten stehen also immer auf der
ersten Seite. Signierte, veränderte, Erstauflage- und Playset-Angebote zählen nicht.

Gespeichert wird als belegter Zustandspreis der Quelle ``cardmarket_offers`` mit Datum und
Link auf genau die ausgelesene Seite („kein Beleg, kein Preis“).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, PricePoint
from app.providers.pricing import CONDITIONS
from app.services.errors import InvalidInputError

SOURCE = "cardmarket_offers"
CURRENCY = "EUR"
CHEAPEST_FOR_AVERAGE = 3
MAX_ROWS = 200
MAX_PRICE = Decimal("100000")
CENT = Decimal("0.01")
ALLOWED_HOSTS = frozenset({"www.cardmarket.com", "cardmarket.com"})

# Sprach-IDs der Cardmarket-Filter (``?language=3``) ↔ unsere Kartensprachen.
CARDMARKET_LANGUAGE_IDS: dict[str, int] = {
    "en": 1,
    "de": 3,
    "zh-cn": 6,
    "ja": 7,
    "ko": 10,
    "zh-tw": 11,
}
# Zustands-IDs der Cardmarket-Filter (``?minCondition=2`` = ab Near Mint).
CARDMARKET_CONDITION_IDS: dict[str, int] = {
    condition: index + 1 for index, condition in enumerate(CONDITIONS)
}

# Bezeichnungen der Sprach-Symbole auf Cardmarket (deutsche und englische Oberfläche).
_LANGUAGE_LABELS: dict[str, tuple[str, ...]] = {
    "de": ("deutsch", "german"),
    "en": ("englisch", "english"),
    "ja": ("japanisch", "japanese"),
    "ko": ("koreanisch", "korean"),
    "zh-tw": ("t-chinese", "traditional chinese", "chinesisch (traditionell)", "t-chinesisch"),
    "zh-cn": ("s-chinese", "simplified chinese", "chinesisch (vereinfacht)", "s-chinesisch"),
    "other": (
        "französisch",
        "french",
        "spanisch",
        "spanish",
        "italienisch",
        "italian",
        "portugiesisch",
        "portuguese",
        "russisch",
        "russian",
        "niederländisch",
        "dutch",
        "polnisch",
        "polish",
    ),
}
_REVERSE = re.compile(r"reverse", re.I)
_EXCLUDED = re.compile(
    r"signed|signiert|altered|verändert|first edition|1st edition|erstauflage|playset",
    re.I,
)
_PRICE = re.compile(r"(\d[\d.,\s]*)")


@dataclass(frozen=True)
class OfferRow:
    """Ein ausgelesenes Angebot, wie es das Lesezeichen liefert (Rohtexte)."""

    condition: str
    price: str
    labels: Sequence[str] = ()


@dataclass(frozen=True)
class ConditionOffers:
    variant: str
    condition: str
    low: Decimal
    low3: Decimal
    offers: int


@dataclass
class OffersResult:
    card_language: str
    page_url: str
    accepted: int = 0
    skipped: int = 0
    prices: list[ConditionOffers] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    saved: int = 0


def parse_price(text: str) -> Decimal | None:
    """``"1.234,56 €"`` → 1234.56; ``"0,02 €"`` → 0.02. ``None`` bei Unsinn."""
    match = _PRICE.search(text)
    if match is None:
        return None
    raw = re.sub(r"\s", "", match.group(1)).rstrip(".,")
    if "," in raw and "." in raw:
        decimal_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
    elif "," in raw:
        decimal_sep = ","
    elif raw.count(".") == 1 and len(raw.rsplit(".", 1)[1]) == 2:  # noqa: PLR2004 – Cent
        decimal_sep = "."
    else:
        decimal_sep = ""
    if decimal_sep:
        thousands = "." if decimal_sep == "," else ","
        normalized = raw.replace(thousands, "").replace(decimal_sep, ".")
    else:  # nur Tausenderpunkte („1.000 €“)
        normalized = raw.replace(".", "").replace(",", "")
    try:
        value = Decimal(normalized).quantize(CENT)
    except InvalidOperation:
        return None
    return value if Decimal(0) < value < MAX_PRICE else None


def label_language(labels: Sequence[str]) -> str | None:
    """Sprache aus den Symbol-Beschriftungen eines Angebots (``None`` = keine erkannt)."""
    for label in labels:
        text = label.strip().casefold()
        for language, names in _LANGUAGE_LABELS.items():
            if any(text == name or text.endswith(f": {name}") for name in names):
                return language
    return None


def page_filters(page_url: str) -> tuple[str | None, str | None]:
    """Sprach- und Zustandsfilter der Seite (``?language=3&minCondition=2``)."""
    query = parse_qs(urlsplit(page_url).query)
    by_id = {str(v): k for k, v in CARDMARKET_LANGUAGE_IDS.items()}
    conditions = {str(v): k for k, v in CARDMARKET_CONDITION_IDS.items()}
    language_ids = query.get("language", [""])[0].split(",")
    language = by_id.get(language_ids[0]) if len(language_ids) == 1 else None
    min_condition = conditions.get(query.get("minCondition", [""])[0])
    return language, min_condition


def validate_page_url(page_url: str) -> str:
    """Nur Cardmarket-Seiten; ohne Sprungmarke (``#kartenkiste=…``) gespeichert."""
    parts = urlsplit(page_url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        raise InvalidInputError("Das ist keine Cardmarket-Seite.")
    return parts._replace(fragment="").geturl()[:500]


def evaluate_offers(card: Card, page_url: str, rows: Sequence[OfferRow]) -> OffersResult:
    """Angebote prüfen und je Variante und Zustand auswerten (speichert nichts)."""
    url = validate_page_url(page_url)
    if len(rows) > MAX_ROWS:
        raise InvalidInputError(f"Höchstens {MAX_ROWS} Angebote auf einmal.")
    result = OffersResult(card_language=card.language, page_url=url)
    page_language, min_condition = page_filters(url)
    if page_language is not None and page_language != card.language:
        result.warnings.append(
            f"Die Seite ist auf eine andere Sprache gefiltert ({page_language}) als die Karte "
            f"({card.language}) – nur passende Angebote werden gezählt."
        )

    prices: dict[str, list[tuple[int, Decimal]]] = {"normal": [], "reverse": []}
    for row in rows:
        condition = row.condition.strip().upper()
        price = parse_price(row.price)
        labels = [label for label in row.labels if label]
        language = label_language(labels) or page_language
        joined = " ".join(labels)
        if (
            condition not in CONDITIONS
            or price is None
            or language != card.language
            or _EXCLUDED.search(joined)
        ):
            result.skipped += 1
            continue
        variant = "reverse" if _REVERSE.search(joined) else "normal"
        prices[variant].append((CONDITIONS.index(condition), price))
        result.accepted += 1

    worst_shown = CONDITIONS.index(min_condition) if min_condition else len(CONDITIONS) - 1
    for variant, offers in prices.items():
        for rank, condition in enumerate(CONDITIONS[: worst_shown + 1]):
            eligible = sorted(price for offer_rank, price in offers if offer_rank <= rank)
            if not eligible:
                continue
            cheapest = eligible[:CHEAPEST_FOR_AVERAGE]
            result.prices.append(
                ConditionOffers(
                    variant=variant,
                    condition=condition,
                    low=eligible[0],
                    low3=(sum(cheapest, Decimal(0)) / len(cheapest)).quantize(CENT),
                    offers=len(eligible),
                )
            )
    if result.accepted == 0:
        result.warnings.append(
            "Keine passenden Angebote gefunden – stimmt die Sprache, und ist die Seite ganz "
            "geladen?"
        )
    return result


async def save_offers(
    session: AsyncSession, card: Card, result: OffersResult, *, now: datetime | None = None
) -> int:
    """Speichert die ausgewerteten Preise als Belege (eine Zeile je Wert)."""
    observed = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    rows = [
        {
            "card_id": card.id,
            "source": SOURCE,
            "variant": price.variant,
            "metric": metric,
            "condition": price.condition,
            "value": value,
            "currency": CURRENCY,
            "source_updated_at": observed,
            "source_url": result.page_url,
        }
        for price in result.prices
        for metric, value in (("low", price.low), ("low3", price.low3))
    ]
    if not rows:
        return 0
    await session.execute(insert(PricePoint).values(rows).on_conflict_do_nothing())
    result.saved = len(rows)
    return len(rows)
