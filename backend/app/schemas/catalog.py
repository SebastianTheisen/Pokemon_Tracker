"""Schemas für Katalog und Suche."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models import CardSource


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    language: str
    name: str
    series_name: str | None
    release_date: date | None
    card_count_official: int | None
    card_count_total: int | None
    logo_url: str | None
    symbol_url: str | None


class SetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    language: str
    name: str


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    language: str
    name: str
    number: str
    image_url: str | None
    rarity: str | None
    source: CardSource
    card_set: SetSummary


class SearchHitOut(BaseModel):
    score: float
    card: CardOut
