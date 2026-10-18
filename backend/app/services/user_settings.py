"""Persönliche Einstellungen: Zustands- und Sprachfaktoren, Standardsprache."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CatalogLanguage
from app.models import User, UserSettings
from app.providers.pricing import Condition
from app.services.errors import InvalidInputError

# Startwerte relativ zu Near Mint (Plan 5.3). Offen angezeigt und je Nutzer änderbar.
DEFAULT_CONDITION_FACTORS: dict[Condition, Decimal] = {
    "MT": Decimal("1.05"),
    "NM": Decimal("1.00"),
    "EX": Decimal("0.85"),
    "GD": Decimal("0.70"),
    "LP": Decimal("0.55"),
    "PL": Decimal("0.40"),
    "PO": Decimal("0.25"),
}
MAX_FACTOR = Decimal("3")
FACTOR_STEP = Decimal("0.01")
# Sprachfaktoren: ohne eigene Angabe 1,00 – wir erfinden keinen Abschlag.
LANGUAGES: tuple[CatalogLanguage, ...] = ("de", "en", "ja", "ko", "zh-tw", "zh-cn")
DEFAULT_LANGUAGE_FACTOR = Decimal("1.00")


def effective_factors(settings: UserSettings | None) -> dict[str, Decimal]:
    """Standardfaktoren, überschrieben durch die eigenen Werte des Nutzers."""
    custom = settings.condition_factors if settings is not None else {}
    return {
        condition: Decimal(str(custom[condition])).quantize(FACTOR_STEP)
        if condition in custom
        else default
        for condition, default in DEFAULT_CONDITION_FACTORS.items()
    }


def effective_language_factors(settings: UserSettings | None) -> dict[str, Decimal]:
    """Faktor je Kartensprache (Standard 1,00), überschrieben durch eigene Werte."""
    custom = settings.language_factors if settings is not None else {}
    return {
        language: Decimal(str(custom[language])).quantize(FACTOR_STEP)
        if language in custom
        else DEFAULT_LANGUAGE_FACTOR
        for language in LANGUAGES
    }


def _merge_factors[K: str](
    current: Mapping[str, object],
    changes: Mapping[K, Decimal],
    defaults: Mapping[K, Decimal],
    label: str,
) -> dict[str, object]:
    """Neue Faktoren einarbeiten; Werte gleich dem Standard werden entfernt."""
    unknown = set(changes) - set(defaults)
    if unknown:
        raise InvalidInputError(f"Unbekannte {label}: {', '.join(sorted(unknown))}")
    merged = dict(current)
    for key, raw_factor in changes.items():
        factor = raw_factor.quantize(FACTOR_STEP)
        if not Decimal(0) < factor <= MAX_FACTOR:
            raise InvalidInputError(f"Faktor für {key} muss zwischen 0 und 3 liegen.")
        if factor == defaults[key]:
            merged.pop(key, None)
        else:
            merged[key] = str(factor)
    return merged


async def get_user_settings(session: AsyncSession, user: User) -> UserSettings | None:
    return await session.get(UserSettings, user.id)


async def update_user_settings(
    session: AsyncSession,
    user: User,
    *,
    condition_factors: Mapping[Condition, Decimal] | None = None,
    reset_condition_factors: bool = False,
    language_factors: Mapping[CatalogLanguage, Decimal] | None = None,
    reset_language_factors: bool = False,
    default_language: str | None = None,
) -> UserSettings:
    """Speichert Änderungen. Faktoren gleich dem Standard werden nicht gespeichert."""
    settings = await session.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id, condition_factors={}, language_factors={})
        session.add(settings)

    # Jeweils neue Zuweisung, damit SQLAlchemy die Änderung am JSON sieht.
    if reset_condition_factors:
        settings.condition_factors = {}
    if condition_factors:
        settings.condition_factors = _merge_factors(
            settings.condition_factors, condition_factors, DEFAULT_CONDITION_FACTORS, "Zustände"
        )
    if reset_language_factors:
        settings.language_factors = {}
    if language_factors:
        defaults: dict[CatalogLanguage, Decimal] = dict.fromkeys(LANGUAGES, DEFAULT_LANGUAGE_FACTOR)
        settings.language_factors = _merge_factors(
            settings.language_factors or {}, language_factors, defaults, "Sprachen"
        )
    if default_language is not None:
        settings.default_language = default_language
    await session.flush()
    return settings
