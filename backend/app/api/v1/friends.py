"""Freunde: freigegebene Sammlungen (Showcase) und Tausch-Rechner."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import CurrentUser, PriceServiceDep, SessionDep
from app.models import GradingCompany, Trade
from app.providers.pricing import Condition
from app.schemas.collection import FolderOut, ItemOut, public_item
from app.services.friends import FriendsService, Showcase
from app.services.trades import TradeLine, TradeResult, TradeService

router = APIRouter(tags=["friends"])


def get_friends(session: SessionDep, user: CurrentUser, prices: PriceServiceDep) -> FriendsService:
    return FriendsService(session, user, prices)


def get_trades(session: SessionDep, user: CurrentUser, prices: PriceServiceDep) -> TradeService:
    return TradeService(session, user, prices)


Friends = Annotated[FriendsService, Depends(get_friends)]
Trades = Annotated[TradeService, Depends(get_trades)]


# ----------------------------------------------------------------- Showcase


class FriendOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    folders: int
    items: int
    total_value: Decimal


class ShowcaseOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    folders: list[FolderOut]
    items: list[ItemOut] = Field(description="Ohne Kaufpreise, Eigenpreise, Notizen, Gewinn")
    total_value: Decimal

    @classmethod
    def build(cls, showcase: Showcase) -> ShowcaseOut:
        return cls(
            user_id=showcase.owner.id,
            display_name=showcase.owner.display_name,
            folders=[FolderOut.model_validate(f) for f in showcase.folders],
            items=[public_item(v) for v in showcase.items],
            total_value=showcase.total_value,
        )


@router.get("/friends")
async def list_friends(friends: Friends) -> list[FriendOut]:
    """Freunde mit freigegebenen Ordnern (Showcase)."""
    return [
        FriendOut(
            user_id=s.owner.id,
            display_name=s.owner.display_name,
            folders=len(s.folders),
            items=s.item_count,
            total_value=s.total_value,
        )
        for s in await friends.friends()
    ]


@router.get("/friends/{user_id}")
async def friend_showcase(
    user_id: uuid.UUID, friends: Friends, folder_id: uuid.UUID | None = None
) -> ShowcaseOut:
    return ShowcaseOut.build(await friends.showcase(user_id, folder_id))


# ------------------------------------------------------------------- Tausch


class TradeLineIn(BaseModel):
    side: Literal["give", "get"]
    item_id: uuid.UUID | None = Field(
        default=None, description="Eigene Position oder aus dem Showcase eines Freundes"
    )
    card_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant: Literal["normal", "reverse"] = "normal"
    condition: Condition | None = "NM"
    grading_company: GradingCompany | None = None
    grade: Annotated[str, Field(max_length=8)] | None = None
    quantity: Annotated[int, Field(ge=1, le=999)] = 1

    @model_validator(mode="after")
    def _one_source(self) -> TradeLineIn:
        if sum(x is not None for x in (self.item_id, self.card_id, self.product_id)) != 1:
            raise ValueError("Genau eines von item_id, card_id, product_id angeben.")
        return self


class TradeIn(BaseModel):
    lines: Annotated[list[TradeLineIn], Field(max_length=100)]


class TradeSave(TradeIn):
    partner: Annotated[str, Field(max_length=80)] | None = None
    note: Annotated[str, Field(max_length=500)] | None = None


class TradeLineOut(BaseModel):
    side: Literal["give", "get"]
    card_id: uuid.UUID | None
    product_id: uuid.UUID | None
    label: str
    image_url: str | None
    variant: str
    condition: str | None
    grading_company: str | None
    grade: str | None
    quantity: int
    unit_value: Decimal | None
    total: Decimal | None


class TradeValueOut(BaseModel):
    lines: list[TradeLineOut]
    give_value: Decimal
    get_value: Decimal
    difference: Decimal = Field(description="Bekomme minus gebe (positiv = gut für mich)")
    unvalued: int = Field(description="Zeilen ohne bekannten Wert")

    @classmethod
    def build(cls, result: TradeResult) -> TradeValueOut:
        give, get = result.value("give"), result.value("get")
        return cls(
            lines=[
                TradeLineOut(
                    side=v.line.side,
                    card_id=v.line.card_id,
                    product_id=v.line.product_id,
                    label=v.label,
                    image_url=v.image_url,
                    variant=v.line.variant,
                    condition=v.line.condition,
                    grading_company=v.line.grading_company,
                    grade=v.line.grade,
                    quantity=v.line.quantity,
                    unit_value=v.unit_value,
                    total=v.total,
                )
                for v in result.lines
            ],
            give_value=give,
            get_value=get,
            difference=get - give,
            unvalued=result.unvalued,
        )


class TradeOut(BaseModel):
    id: uuid.UUID
    partner: str | None
    note: str | None
    created_at: datetime
    give_value: Decimal = Field(description="Damals")
    get_value: Decimal = Field(description="Damals")
    now: TradeValueOut = Field(description="Dieselben Karten heute bewertet")

    @classmethod
    def build(cls, trade: Trade, now: TradeResult) -> TradeOut:
        return cls(
            id=trade.id,
            partner=trade.partner,
            note=trade.note,
            created_at=trade.created_at,
            give_value=trade.give_value,
            get_value=trade.get_value,
            now=TradeValueOut.build(now),
        )


async def _lines(trades: TradeService, body: TradeIn) -> list[TradeLine]:
    lines = []
    for line in body.lines:
        if line.item_id is not None:
            lines.append(await trades.line_from_item(line.side, line.item_id, line.quantity))
        else:
            lines.append(
                TradeLine(
                    side=line.side,
                    card_id=line.card_id,
                    product_id=line.product_id,
                    variant=line.variant,
                    condition=line.condition,
                    grading_company=line.grading_company.value if line.grading_company else None,
                    grade=line.grade,
                    quantity=line.quantity,
                )
            )
    return lines


@router.post("/trades/evaluate")
async def evaluate_trade(body: TradeIn, trades: Trades) -> TradeValueOut:
    """Tausch bewerten, ohne zu speichern (für die Live-Anzeige im Rechner)."""
    return TradeValueOut.build(await trades.evaluate(await _lines(trades, body)))


@router.post("/trades", status_code=status.HTTP_201_CREATED)
async def save_trade(body: TradeSave, trades: Trades) -> TradeOut:
    """Tausch mit den heutigen Werten speichern (die Sammlung bleibt unverändert)."""
    lines = await _lines(trades, body)
    trade = await trades.save(lines, partner=body.partner, note=body.note)
    return TradeOut.build(trade, await trades.evaluate(lines))


@router.get("/trades")
async def list_trades(trades: Trades) -> list[TradeOut]:
    return [TradeOut.build(trade, now) for trade, now in await trades.trades()]


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trade(trade_id: uuid.UUID, trades: Trades) -> None:
    await trades.delete(trade_id)
