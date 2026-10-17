"""Laden von Preisquellen-Plug-ins über ``PT_EXTRA_PRICE_PROVIDERS``."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.pricing import CardRef, PriceKind, PriceQuote
from app.providers.pricing.plugins import PluginConfigError, load_plugins


class ExamplePlugin:
    """So sieht eine minimale eigene Preisquelle aus."""

    kind: PriceKind = "external"

    def __init__(self, *, settings: Settings, name: str = "beispiel") -> None:
        self.settings = settings
        self.name = name

    async def fetch(self, card: CardRef) -> list[PriceQuote]:
        return []


class WrongKindPlugin(ExamplePlugin):
    kind: PriceKind = "verified"


def second_plugin(*, settings: Settings) -> ExamplePlugin:
    return ExamplePlugin(settings=settings, name="zweite")


def same_name_plugin(*, settings: Settings) -> ExamplePlugin:
    return ExamplePlugin(settings=settings, name="beispiel")


def not_a_provider(*, settings: Settings) -> object:
    return object()


MODULE = __name__


def test_loads_plugins_and_passes_settings() -> None:
    settings = Settings()

    providers = load_plugins([f"{MODULE}:ExamplePlugin", f"{MODULE}:second_plugin"], settings)

    assert [p.name for p in providers] == ["beispiel", "zweite"]
    assert isinstance(providers[0], ExamplePlugin)
    assert providers[0].settings is settings


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("ohne_doppelpunkt", "Format"),
        ("gibts.nicht:Klasse", "nicht gefunden"),
        (f"{MODULE}:GibtsNicht", "nicht gefunden"),
        (f"{MODULE}:not_a_provider", "Protokoll"),
        (f"{MODULE}:WrongKindPlugin", "external"),
    ],
)
def test_invalid_plugins_fail_fast(path: str, message: str) -> None:
    with pytest.raises(PluginConfigError, match=message):
        load_plugins([path], Settings())


def test_duplicate_or_reserved_names_are_rejected() -> None:
    with pytest.raises(PluginConfigError, match="Doppelte"):
        load_plugins([f"{MODULE}:ExamplePlugin", f"{MODULE}:same_name_plugin"], Settings())


def test_no_plugins_by_default() -> None:
    assert load_plugins(Settings().extra_price_providers, Settings()) == []
