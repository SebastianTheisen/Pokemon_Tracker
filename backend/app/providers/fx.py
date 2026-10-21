"""Wechselkurse der Europäischen Zentralbank (Referenzkurse, werktags gegen 16 Uhr MEZ).

Quelle: ``https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`` – frei, ohne
Schlüssel. Die Datei nennt je Währung, wie viel davon 1 Euro kostet (``USD rate="1.08"``);
umgerechnet wird also ``Euro = Dollar / Kurs``. Der Kurs wird einige Stunden im Speicher
gehalten; fällt die EZB aus, gilt der letzte bekannte Kurs (höchstens :data:`MAX_STALE`).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
REFRESH = timedelta(hours=6)
MAX_STALE = timedelta(days=7)
_TIME = re.compile(r"<Cube\s+time=['\"](\d{4}-\d{2}-\d{2})['\"]")


class FxError(Exception):
    """Kein (ausreichend aktueller) Kurs verfügbar."""


@dataclass(frozen=True)
class FxRate:
    """1 EUR = ``per_euro`` Einheiten der Währung, Stand ``day``."""

    currency: str
    per_euro: Decimal
    day: date | None

    def to_euro(self, amount: Decimal) -> Decimal:
        return amount / self.per_euro


def parse_ecb(xml: str, currency: str) -> FxRate:
    """Kurs einer Währung aus der EZB-Tagesdatei."""
    match = re.search(rf"currency=['\"]{currency}['\"]\s+rate=['\"]([\d.]+)['\"]", xml)
    if match is None:
        raise FxError(f"EZB-Datei ohne Kurs für {currency}")
    try:
        per_euro = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise FxError(f"EZB-Kurs für {currency} unlesbar") from exc
    if per_euro <= 0:
        raise FxError(f"EZB-Kurs für {currency} ungültig")
    day_match = _TIME.search(xml)
    day = date.fromisoformat(day_match.group(1)) if day_match else None
    return FxRate(currency=currency, per_euro=per_euro, day=day)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EcbRates:
    """Zwischengespeicherte EZB-Kurse (eine Instanz je Prozess genügt)."""

    def __init__(
        self,
        *,
        user_agent: str,
        url: str = ECB_DAILY,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        self._user_agent = user_agent
        self._url = url
        self._transport = transport
        self._now = clock
        self._cache: dict[str, tuple[FxRate, datetime]] = {}
        self._lock = asyncio.Lock()

    async def rate(self, currency: str) -> FxRate:
        """Aktueller Kurs; bei EZB-Ausfall der letzte bekannte (höchstens 7 Tage alt)."""
        async with self._lock:
            now = self._now()
            cached = self._cache.get(currency)
            if cached is not None and now - cached[1] < REFRESH:
                return cached[0]
            try:
                async with httpx.AsyncClient(
                    headers={"User-Agent": self._user_agent},
                    timeout=20,
                    transport=self._transport,
                ) as client:
                    response = await client.get(self._url)
                    response.raise_for_status()
                rate = parse_ecb(response.text, currency)
            except (httpx.HTTPError, FxError) as exc:
                if cached is not None and now - cached[1] < MAX_STALE:
                    return cached[0]
                raise FxError(f"EZB-Kurs nicht verfügbar: {exc}") from exc
            self._cache[currency] = (rate, now)
            return rate
