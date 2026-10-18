"""Verkaufte eBay-Angebote, die der Nutzer selbst ausgelesen hat (Lesezeichen im Browser).

Wie bei Cardmarket ruft der Server eBay nie ab: Der Nutzer öffnet in der Karte „Verkaufte
Angebote bei eBay“ (Suche mit Filter „Verkaufte Artikel“), tippt auf das Lesezeichen „An
Kartenkiste senden“ und bekommt eine Vorschau. Darin sind die Verkäufe vorausgewählt, die
sicher zur Karte passen; der Nutzer kann ab- und zuwählen und speichert dann.

Je Verkauf werden aus den Rohtexten gelesen: Preis (nur EUR), Verkaufsdatum, Grading
(„PSA 10“, „BGS 9.5“, „CGC 9“ im Titel) und Hinweise, die gegen die Karte sprechen
(Konvolut, Booster, Fälschung, andere Nummer).

Gespeichert wird je Gruppe – ungegradet bzw. je Grading-Firma und Note – Median, günstigster,
teuerster Verkauf und Anzahl als Beleg der Quelle ``ebay_sold`` mit Link auf die Suche.
Gegradete Sammlungspositionen erhalten daraus ihren Wert (Median), ungegradete Verkäufe
sind nur Information – der Wert von Rohkarten kommt weiter von Cardmarket.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Card, PricePoint
from app.services.cardmarket_offers import parse_price
from app.services.errors import InvalidInputError

SOURCE = "ebay_sold"
CURRENCY = "EUR"
RAW_VARIANT = "raw"
MAX_ROWS = 120
MAX_AGE_DAYS = 120
CENT = Decimal("0.01")
GRADERS = ("PSA", "BGS", "CGC", "SGC", "TAG", "ACE")

_GRADE = re.compile(
    r"\b(PSA|BGS|BECKETT|CGC|SGC|TAG|ACE)\s*(?:GEM\s*(?:MINT|MT)\s*)?(10|[1-9](?:[.,]5)?)\b",
    re.I,
)
_LOT = re.compile(
    r"\b(lot|konvolut|sammlung|bundle|set\s+von|\d+\s*(?:x|stück|karten|cards)\b|booster|"
    r"display|etb|elite trainer|blister|proxy|fake|custom|orica|nachdruck|replica|"
    r"metal|metall|jumbo|oversize)\b",
    re.I,
)
_RANGE = re.compile(r"\b(bis|to)\b|–|-\s*\d", re.I)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mär": 3,
    "mrz": 3,
    "mar": 3,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "dez": 12,
    "dec": 12,
}
_DATE_DE = re.compile(r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]{3,5})\.?\s+(\d{4})")
_DATE_EN = re.compile(r"\b([A-Za-z]{3,5})\.?\s+(\d{1,2}),?\s+(\d{4})")
_DATE_NUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b")


@dataclass(frozen=True)
class SoldRow:
    """Ein ausgelesener Verkauf (Rohtexte der eBay-Seite)."""

    title: str
    price: str
    sold: str = ""
    url: str = ""


@dataclass(frozen=True)
class SoldSale:
    """Ein ausgewerteter Verkauf."""

    index: int
    title: str
    price: Decimal | None
    sold_on: date | None
    group: str  # „raw“ oder z. B. „PSA 10“
    url: str
    issues: tuple[str, ...]

    @property
    def suggested(self) -> bool:
        return self.price is not None and not self.issues


@dataclass(frozen=True)
class SoldGroup:
    group: str
    median: Decimal
    low: Decimal
    high: Decimal
    count: int


@dataclass
class SoldResult:
    page_url: str
    sales: list[SoldSale] = field(default_factory=list)
    groups: list[SoldGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    saved: int = 0


def validate_page_url(page_url: str) -> str:
    parts = urlsplit(page_url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not re.fullmatch(r"(www\.)?ebay\.[a-z.]{2,6}", host):
        raise InvalidInputError("Das ist keine eBay-Seite.")
    return parts._replace(fragment="").geturl()[:500]


def parse_sold_date(text: str, *, today: date) -> date | None:
    """„Verkauft 12. Okt 2026“, „Sold Oct 12, 2026“, „12.10.2026“ → Datum."""
    match = _DATE_DE.search(text)
    if match and (month := _MONTHS.get(match.group(2)[:3].casefold())):
        return _safe_date(int(match.group(3)), month, int(match.group(1)), today)
    match = _DATE_EN.search(text)
    if match and (month := _MONTHS.get(match.group(1)[:3].casefold())):
        return _safe_date(int(match.group(3)), month, int(match.group(2)), today)
    match = _DATE_NUM.search(text)
    if match:
        year = int(match.group(3))
        year = year + 2000 if year < 100 else year  # noqa: PLR2004 – „12.10.26“
        return _safe_date(year, int(match.group(2)), int(match.group(1)), today)
    return None


def _safe_date(year: int, month: int, day: int, today: date) -> date | None:
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    return value if value <= today + timedelta(days=1) else None


def grading_group(title: str) -> str:
    """Gruppe eines Verkaufs: ``raw`` oder ``"PSA 10"``, ``"BGS 9.5"`` …"""
    match = _GRADE.search(title)
    if match is None:
        return RAW_VARIANT
    company = match.group(1).upper()
    company = "BGS" if company == "BECKETT" else company
    return f"{company} {match.group(2).replace(',', '.')}"


def _number_tokens(card: Card) -> set[str]:
    """Wie die Kartennummer im Titel stehen kann: „215“, „215/203“, „SV068“, „TG24“."""
    head = card.number.strip().upper()
    tokens = {head, head.lstrip("0") or "0", card.number_norm.upper()}
    return {token for token in tokens if token}


def _issues(card: Card, title: str, price_text: str) -> tuple[str, ...]:
    issues: list[str] = []
    upper = title.upper()
    numbers = _number_tokens(card)
    found = re.findall(r"[A-Z]{0,4}\d{1,4}[A-Z]?", upper)
    normalized = {token.lstrip("0") or "0" for token in found} | set(found)
    if not numbers & normalized:
        issues.append("Nummer fehlt im Titel")
    if _LOT.search(title):
        issues.append("Konvolut/Produkt/Fälschung?")
    if _RANGE.search(price_text):
        issues.append("Preisspanne")
    return tuple(issues)


def evaluate_sold(
    card: Card,
    page_url: str,
    rows: Sequence[SoldRow],
    *,
    selected: Sequence[int] | None = None,
    today: date | None = None,
) -> SoldResult:
    """Verkäufe auswerten. ``selected`` = vom Nutzer gewählte Zeilen (sonst Vorschlag)."""
    url = validate_page_url(page_url)
    if len(rows) > MAX_ROWS:
        raise InvalidInputError(f"Höchstens {MAX_ROWS} Verkäufe auf einmal.")
    today = today or datetime.now(UTC).date()
    result = SoldResult(page_url=url)
    foreign_currency = 0
    for index, row in enumerate(rows):
        price_text = row.price.strip()
        is_euro = "€" in price_text or "EUR" in price_text.upper()
        price = parse_price(price_text) if is_euro else None
        if not is_euro and price_text:
            foreign_currency += 1
        sold_on = parse_sold_date(row.sold, today=today)
        issues = list(_issues(card, row.title, price_text))
        if sold_on is not None and (today - sold_on).days > MAX_AGE_DAYS:
            issues.append("älter als 4 Monate")
        result.sales.append(
            SoldSale(
                index=index,
                title=row.title.strip()[:200],
                price=price,
                sold_on=sold_on,
                group=grading_group(row.title),
                url=row.url[:500],
                issues=tuple(issues),
            )
        )
    if foreign_currency:
        result.warnings.append(
            f"{foreign_currency} Verkäufe nicht in Euro – bitte die Suche auf ebay.de öffnen."
        )

    chosen = (
        {index for index in selected if 0 <= index < len(result.sales)}
        if selected is not None
        else {sale.index for sale in result.sales if sale.suggested}
    )
    by_group: defaultdict[str, list[Decimal]] = defaultdict(list)
    for sale in result.sales:
        if sale.index in chosen and sale.price is not None:
            by_group[sale.group].append(sale.price)
    for group, prices in sorted(
        by_group.items(), key=lambda item: (item[0] != RAW_VARIANT, item[0])
    ):
        result.groups.append(
            SoldGroup(
                group=group,
                median=Decimal(statistics.median(prices)).quantize(CENT),
                low=min(prices),
                high=max(prices),
                count=len(prices),
            )
        )
    if not result.sales:
        result.warnings.append("Keine Verkäufe gefunden – ist die Seite ganz geladen?")
    return result


def group_variant(group: str) -> str:
    """Variante in ``price_points``: ``raw`` bzw. ``graded:PSA 10``."""
    return RAW_VARIANT if group == RAW_VARIANT else f"graded:{group}"


def graded_variant(company: str, grade: str | None) -> str | None:
    """Variante zu einer gegradeten Sammlungsposition (``None`` ohne Note)."""
    if not grade:
        return None
    normalized = grade.strip().replace(",", ".")
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    return f"graded:{company.upper()} {normalized}"


async def save_sold(
    session: AsyncSession, card: Card, result: SoldResult, *, now: datetime | None = None
) -> int:
    """Speichert je Gruppe Median, günstigsten, teuersten Verkauf und Anzahl."""
    observed = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    rows = [
        {
            "card_id": card.id,
            "source": SOURCE,
            "variant": group_variant(group.group),
            "metric": metric,
            "condition": None,
            "value": value,
            "currency": CURRENCY,
            "source_updated_at": observed,
            "source_url": result.page_url,
        }
        for group in result.groups
        for metric, value in (
            ("median", group.median),
            ("low", group.low),
            ("high", group.high),
            ("count", Decimal(group.count)),
        )
    ]
    if not rows:
        return 0
    await session.execute(insert(PricePoint).values(rows).on_conflict_do_nothing())
    result.saved = len(rows)
    return len(rows)
