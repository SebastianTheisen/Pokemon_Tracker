"""Preisalarme: Zielpreis für eine Karte oder ein versiegeltes Produkt.

* **Wert einer Karte** = Zustandspreis der gewählten Variante (wie in der Sammlung: belegt
  oder geschätzt, Basis Cardmarket bzw. umgerechneter US-Preis).
* **Wert eines Produkts** = Cardmarket-Preisführer (nur verknüpfte Produkte).
* Geprüft wird nach der täglichen Preisrunde (:func:`check_price_alerts`). Ein Alarm löst
  **einmal** aus (``active = False``) und muss dann neu scharf gestellt werden.

Mandantentrennung wie in der Sammlung: Jede Abfrage filtert ``user_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import AlertDirection, Card, PriceAlert, Product, User
from app.providers.pricing import CONDITIONS, PriceProvider
from app.services.display_names import card_display_name
from app.services.errors import InvalidInputError, NotFoundError
from app.services.price_health import SourceHealth
from app.services.pricing import CardPrices, PriceService
from app.services.push import PushMessage, notify_user
from app.services.sealed import sealed_prices

log = structlog.get_logger(__name__)

MAX_ALERTS_PER_USER = 200
CENT = Decimal("0.01")
VARIANTS = ("normal", "reverse")


@dataclass(frozen=True)
class AlertWithValue:
    alert: PriceAlert
    current: Decimal | None
    """Aktueller Wert (``None``: noch kein Preis bekannt)."""


def reached(direction: AlertDirection, current: Decimal, target: Decimal) -> bool:
    return current >= target if direction is AlertDirection.ABOVE else current <= target


def card_value(prices: CardPrices | None, variant: str, condition: str) -> Decimal | None:
    if prices is None:
        return None
    return next(
        (
            price.value
            for price in prices.conditions
            if price.variant == variant and price.condition == condition
        ),
        None,
    )


def _euro(value: Decimal) -> str:
    """„1.234,50 €“ – für die Nachricht (das Handy formatiert nichts mehr)."""
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def alert_message(alert: PriceAlert, current: Decimal) -> PushMessage:
    if alert.card is not None:
        name = card_display_name(alert.card)
        extra = [] if alert.variant == "normal" else ["Reverse Holo"]
        if alert.condition != "NM":
            extra.append(alert.condition)
        if extra:
            name += f" ({', '.join(extra)})"
        url = f"/card/{alert.card.id}"
    else:
        name = alert.product.name if alert.product else "Produkt"
        url = "/alerts"
    verb = "gestiegen" if alert.direction is AlertDirection.ABOVE else "gefallen"
    return PushMessage(
        title=f"Preisalarm: {name}",
        body=f"Jetzt {_euro(current)} – {verb} auf dein Ziel {_euro(alert.target)}.",
        url=url,
        tag=f"alert-{alert.id}",
    )


class AlertService:
    def __init__(self, session: AsyncSession, owner: User, prices: PriceService) -> None:
        self._session = session
        self._owner = owner
        self._prices = prices

    async def alerts(self, *, active_only: bool = False) -> list[AlertWithValue]:
        statement = (
            select(PriceAlert)
            .where(PriceAlert.user_id == self._owner.id)
            .order_by(PriceAlert.active.desc(), PriceAlert.created_at.desc())
        )
        if active_only:
            statement = statement.where(PriceAlert.active)
        alerts = list((await self._session.scalars(statement)).unique().all())
        return await self.with_values(alerts)

    async def with_values(self, alerts: Sequence[PriceAlert]) -> list[AlertWithValue]:
        card_prices = await self._prices.prices_for_cards(
            [a.card_id for a in alerts if a.card_id is not None], self._owner
        )
        sealed = await sealed_prices(
            self._session, [a.product_id for a in alerts if a.product_id is not None]
        )
        result = []
        for alert in alerts:
            if alert.card_id is not None:
                current = card_value(card_prices.get(alert.card_id), alert.variant, alert.condition)
            else:
                price = sealed.get(alert.product_id) if alert.product_id else None
                current = price.value if price else None
            result.append(AlertWithValue(alert, current))
        return result

    async def get(self, alert_id: uuid.UUID) -> PriceAlert:
        alert = await self._session.scalar(
            select(PriceAlert).where(
                PriceAlert.id == alert_id, PriceAlert.user_id == self._owner.id
            )
        )
        if alert is None:
            raise NotFoundError("Preisalarm nicht gefunden.")
        return alert

    async def create(
        self,
        *,
        card_id: uuid.UUID | None,
        product_id: uuid.UUID | None,
        direction: AlertDirection,
        target: Decimal,
        variant: str = "normal",
        condition: str = "NM",
    ) -> PriceAlert:
        if (card_id is None) == (product_id is None):
            raise InvalidInputError("Bitte genau eine Karte oder ein Produkt angeben.")
        if variant not in VARIANTS or condition not in CONDITIONS:
            raise InvalidInputError("Unbekannte Variante oder unbekannter Zustand.")
        if card_id is not None and await self._session.get(Card, card_id) is None:
            raise NotFoundError("Karte nicht gefunden.")
        if product_id is not None and await self._session.get(Product, product_id) is None:
            raise NotFoundError("Produkt nicht gefunden.")
        count = await self._session.scalar(
            select(func.count()).where(PriceAlert.user_id == self._owner.id)
        )
        if (count or 0) >= MAX_ALERTS_PER_USER:
            raise InvalidInputError(f"Höchstens {MAX_ALERTS_PER_USER} Preisalarme.")
        alert = PriceAlert(
            user_id=self._owner.id,
            card_id=card_id,
            product_id=product_id,
            variant=variant if card_id else "normal",
            condition=condition if card_id else "NM",
            direction=direction,
            target=target.quantize(CENT),
            active=True,
        )
        self._session.add(alert)
        await self._session.flush()
        await self._session.refresh(alert, ["card", "product"])
        return alert

    async def update(
        self,
        alert_id: uuid.UUID,
        *,
        target: Decimal | None = None,
        direction: AlertDirection | None = None,
        active: bool | None = None,
    ) -> PriceAlert:
        """Ziel ändern oder (wieder) scharf stellen – dann zählt die nächste Prüfung neu."""
        alert = await self.get(alert_id)
        if target is not None:
            alert.target = target.quantize(CENT)
        if direction is not None:
            alert.direction = direction
        if active is not None:
            alert.active = active
        if active or target is not None or direction is not None:
            alert.triggered_at = None
            alert.triggered_value = None
            alert.active = True if active is None else active
        await self._session.flush()
        return alert

    async def delete(self, alert_id: uuid.UUID) -> None:
        await self._session.delete(await self.get(alert_id))
        await self._session.flush()

    async def evaluate(self, now: datetime) -> list[AlertWithValue]:
        """Aktive Alarme prüfen; erreichte werden ausgelöst (inaktiv) und zurückgegeben."""
        fired = []
        for entry in await self.alerts(active_only=True):
            alert, current = entry.alert, entry.current
            if current is None or not reached(alert.direction, current, alert.target):
                continue
            alert.active = False
            alert.triggered_at = now
            alert.triggered_value = current
            fired.append(entry)
        await self._session.flush()
        return fired


@dataclass
class AlertRunSummary:
    users: int = 0
    triggered: int = 0
    pushed: int = 0


async def check_price_alerts(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    providers: Sequence[PriceProvider],
    health: SourceHealth,
    *,
    client: httpx.AsyncClient | None = None,
) -> AlertRunSummary:
    """Alle aktiven Alarme prüfen und Ausgelöste per Push melden (nach der Preisrunde)."""
    summary = AlertRunSummary()
    now = datetime.now(UTC)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=20)
    try:
        async with session_factory() as session:
            owners = (
                await session.scalars(
                    select(User).where(
                        User.is_active,
                        select(PriceAlert.id)
                        .where(PriceAlert.user_id == User.id, PriceAlert.active)
                        .exists(),
                    )
                )
            ).all()
            for owner in owners:
                summary.users += 1
                service = PriceService(session, settings, providers, health)
                fired = await AlertService(session, owner, service).evaluate(now)
                summary.triggered += len(fired)
                for entry in fired:
                    assert entry.current is not None  # noqa: S101 – nur mit Wert ausgelöst
                    summary.pushed += await notify_user(
                        session, http, settings, owner.id, alert_message(entry.alert, entry.current)
                    )
                await session.commit()
    finally:
        if own_client:
            await http.aclose()
    log.info(
        "alerts.checked",
        users=summary.users,
        triggered=summary.triggered,
        pushed=summary.pushed,
    )
    return summary
