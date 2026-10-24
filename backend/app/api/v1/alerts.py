"""Preisalarme und Web-Push-Geräte des angemeldeten Nutzers."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep, SettingsDep
from app.models import AlertDirection, UserSettings
from app.providers.pricing import Condition
from app.schemas.catalog import CardOut
from app.schemas.collection import ProductOut
from app.services import push
from app.services.alerts import AlertService, AlertWithValue
from app.services.errors import InvalidInputError

router = APIRouter(tags=["alerts"])

Target = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


def get_alerts(session: SessionDep, user: CurrentUser, prices: PriceServiceDep) -> AlertService:
    return AlertService(session, user, prices)


Alerts = Annotated[AlertService, Depends(get_alerts)]


# ------------------------------------------------------------------ Schemas


class AlertCreate(BaseModel):
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant: Literal["normal", "reverse"] = "normal"
    condition: Condition = "NM"
    direction: AlertDirection
    target: Target


class AlertUpdate(BaseModel):
    target: Target | None = None
    direction: AlertDirection | None = None
    active: bool | None = Field(default=None, description="true = wieder scharf stellen")


class AlertOut(BaseModel):
    id: uuid.UUID
    card: CardOut | None
    product: ProductOut | None
    variant: str
    condition: str
    direction: AlertDirection
    target: Decimal
    active: bool
    current_value: Decimal | None
    created_at: datetime
    triggered_at: datetime | None
    triggered_value: Decimal | None

    @classmethod
    def build(cls, entry: AlertWithValue) -> AlertOut:
        alert = entry.alert
        return cls(
            id=alert.id,
            card=CardOut.model_validate(alert.card) if alert.card else None,
            product=ProductOut.model_validate(alert.product) if alert.product else None,
            variant=alert.variant,
            condition=alert.condition,
            direction=alert.direction,
            target=alert.target,
            active=alert.active,
            current_value=entry.current,
            created_at=alert.created_at,
            triggered_at=alert.triggered_at,
            triggered_value=alert.triggered_value,
        )


class PushKeys(BaseModel):
    p256dh: Annotated[str, Field(min_length=20, max_length=200)]
    auth: Annotated[str, Field(min_length=10, max_length=100)]


class PushSubscriptionIn(BaseModel):
    """Wie ``PushSubscription.toJSON()`` im Browser."""

    endpoint: Annotated[str, Field(min_length=10, max_length=2000)]
    keys: PushKeys


class PushConfigOut(BaseModel):
    public_key: str | None = Field(description="VAPID-Schlüssel; null = Push nicht eingerichtet")
    devices: int = Field(description="Angemeldete Geräte dieses Nutzers")
    weekly_summary: bool = Field(default=True, description="Sonntags „Deine Woche“")


class PushPreferences(BaseModel):
    weekly_summary: bool


async def _weekly_summary(session: SessionDep, user: CurrentUser) -> bool:
    settings = await session.get(UserSettings, user.id)
    return settings.weekly_summary if settings is not None else True


class PushTestOut(BaseModel):
    sent: int


# ------------------------------------------------------------------- Alarme


@router.get("/alerts")
async def list_alerts(alerts: Alerts) -> list[AlertOut]:
    """Eigene Preisalarme mit aktuellem Wert – aktive zuerst."""
    return [AlertOut.build(entry) for entry in await alerts.alerts()]


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(body: AlertCreate, alerts: Alerts) -> AlertOut:
    alert = await alerts.create(**body.model_dump())
    return AlertOut.build((await alerts.with_values([alert]))[0])


@router.patch("/alerts/{alert_id}")
async def update_alert(alert_id: uuid.UUID, body: AlertUpdate, alerts: Alerts) -> AlertOut:
    alert = await alerts.update(alert_id, **body.model_dump(exclude_unset=True))
    return AlertOut.build((await alerts.with_values([alert]))[0])


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: uuid.UUID, alerts: Alerts) -> None:
    await alerts.delete(alert_id)


# --------------------------------------------------------------------- Push


@router.get("/push/config")
async def push_config(
    session: SessionDep, user: CurrentUser, settings: SettingsDep
) -> PushConfigOut:
    return PushConfigOut(
        public_key=push.public_key(settings),
        devices=await push.device_count(session, user),
        weekly_summary=await _weekly_summary(session, user),
    )


@router.patch("/push/preferences")
async def push_preferences(
    body: PushPreferences, session: SessionDep, user: CurrentUser, settings: SettingsDep
) -> PushConfigOut:
    """Wochenrückblick an/aus."""
    stored = await session.get(UserSettings, user.id)
    if stored is None:
        stored = UserSettings(user_id=user.id, condition_factors={}, language_factors={})
        session.add(stored)
    stored.weekly_summary = body.weekly_summary
    await session.flush()
    return PushConfigOut(
        public_key=push.public_key(settings),
        devices=await push.device_count(session, user),
        weekly_summary=stored.weekly_summary,
    )


@router.post("/push/subscriptions", status_code=status.HTTP_201_CREATED)
async def add_subscription(
    body: PushSubscriptionIn,
    session: SessionDep,
    user: CurrentUser,
    user_agent: Annotated[str | None, Header()] = None,
) -> PushConfigOut:
    """Dieses Gerät für Benachrichtigungen anmelden (erneutes Anmelden ist harmlos)."""
    await push.subscribe(
        session,
        user,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=user_agent,
    )
    return PushConfigOut(public_key=None, devices=await push.device_count(session, user))


@router.delete("/push/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_subscription(
    session: SessionDep,
    user: CurrentUser,
    endpoint: Annotated[str, Query(min_length=10, max_length=2000)],
) -> None:
    await push.unsubscribe(session, user, endpoint)


@router.post("/push/test")
async def push_test(session: SessionDep, user: CurrentUser, settings: SettingsDep) -> PushTestOut:
    """Probe-Nachricht an alle eigenen Geräte."""
    if push.public_key(settings) is None:
        raise InvalidInputError("Push ist auf dem Server noch nicht eingerichtet.", code="push_off")
    if await push.device_count(session, user) == 0:
        raise InvalidInputError("Kein Gerät angemeldet.", code="push_no_device")
    async with httpx.AsyncClient(timeout=20) as client:
        sent = await push.notify_user(
            session,
            client,
            settings,
            user.id,
            push.PushMessage(
                title="Kartenkiste",
                body="Benachrichtigungen funktionieren 👍",
                url="/alerts",
                tag="test",
            ),
        )
    return PushTestOut(sent=sent)
