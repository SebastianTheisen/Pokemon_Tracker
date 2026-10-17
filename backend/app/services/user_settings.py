"""Persönliche Einstellungen: Zustandsfaktoren und Standardsprache."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserSettings
from app.providers.pricing import CONDITIONS, Condition
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


def effective_factors(settings: UserSettings | None) -> dict[str, Decimal]:
    """Standardfaktoren, überschrieben durch die eigenen Werte des Nutzers."""
    custom = settings.condition_factors if settings is not None else {}
    return {
        condition: Decimal(str(custom[condition])).quantize(FACTOR_STEP)
        if condition in custom
        else default
        for condition, default in DEFAULT_CONDITION_FACTORS.items()
    }


async def get_user_settings(session: AsyncSession, user: User) -> UserSettings | None:
    return await session.get(UserSettings, user.id)


async def update_user_settings(
    session: AsyncSession,
    user: User,
    *,
    condition_factors: Mapping[Condition, Decimal] | None = None,
    reset_condition_factors: bool = False,
    default_language: str | None = None,
) -> UserSettings:
    """Speichert Änderungen. Faktoren gleich dem Standard werden nicht gespeichert."""
    settings = await session.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id, condition_factors={})
        session.add(settings)

    if reset_condition_factors:
        settings.condition_factors = {}
    if condition_factors:
        unknown = set(condition_factors) - set(CONDITIONS)
        if unknown:
            raise InvalidInputError(f"Unbekannte Zustände: {', '.join(sorted(unknown))}")
        merged = dict(settings.condition_factors)
        for condition, raw_factor in condition_factors.items():
            factor = raw_factor.quantize(FACTOR_STEP)
            if not Decimal(0) < factor <= MAX_FACTOR:
                raise InvalidInputError(f"Faktor für {condition} muss zwischen 0 und 3 liegen.")
            if factor == DEFAULT_CONDITION_FACTORS[condition]:
                merged.pop(condition, None)
            else:
                merged[condition] = str(factor)
        settings.condition_factors = merged  # neue Zuweisung, damit SQLAlchemy die Änderung sieht
    if default_language is not None:
        settings.default_language = default_language
    await session.flush()
    return settings
