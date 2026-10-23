"""Schemas für Katalog und Suche."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models import CardSource
from app.services.card_names import translate_card_name
from app.services.set_names import translated_set_name


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def translated_name(self) -> str | None:
        """Englischer Name japanischer (koreanischer, taiwanischer) Sets."""
        return translated_set_name(self.external_id, self.language, self.name)


class SetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    language: str
    name: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def translated_name(self) -> str | None:
        """Englischer Name japanischer (koreanischer, taiwanischer) Sets."""
        return translated_set_name(self.external_id, self.language, self.name)


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    language: str
    name: str
    number: str
    image_url: str | None
    image_language: str | None = None
    rarity: str | None
    variants: dict[str, bool] | None = Field(
        default=None, description="Welche Fassungen es gibt, z. B. {normal, reverse, holo}"
    )
    illustrator: str | None = None
    source: CardSource
    card_set: SetSummary

    @computed_field  # type: ignore[prop-decorator]
    @property
    def translated_name(self) -> str | None:
        """Deutscher Name bei japanischen, koreanischen und chinesischen Karten."""
        return translate_card_name(self.name, self.language)


class SearchHitOut(BaseModel):
    score: float
    card: CardOut
