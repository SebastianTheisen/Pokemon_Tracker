"""Laden zusätzlicher Preisquellen (Plug-ins) aus ``PT_EXTRA_PRICE_PROVIDERS``.

Format je Eintrag: ``"paket.modul:Name"``. ``Name`` ist eine Klasse oder Fabrikfunktion,
die mit dem Schlüsselwort ``settings`` aufgerufen wird und ein Objekt liefert, das
``PriceProvider`` erfüllt (``name``, ``kind == "external"``, ``async fetch``).

Fehlerhafte Einträge brechen den Start ab – eine falsch konfigurierte Quelle soll sofort
auffallen und nicht still fehlen.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable

from app.core.config import Settings
from app.providers.pricing import PriceProvider


class PluginConfigError(ValueError):
    """Ein Plug-in-Eintrag ist ungültig."""


def load_plugin(path: str, settings: Settings) -> PriceProvider:
    module_name, _, attribute = path.partition(":")
    if not module_name or not attribute:
        raise PluginConfigError(f"Preisquelle '{path}': Format 'paket.modul:Name' erwartet.")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise PluginConfigError(f"Preisquelle '{path}' nicht gefunden: {exc}") from exc
    provider = factory(settings=settings)
    if not isinstance(provider, PriceProvider):
        raise PluginConfigError(f"Preisquelle '{path}' erfüllt das PriceProvider-Protokoll nicht.")
    if provider.kind != "external":
        raise PluginConfigError(f"Preisquelle '{path}': kind muss 'external' sein.")
    return provider


def load_plugins(paths: Iterable[str], settings: Settings) -> list[PriceProvider]:
    providers = [load_plugin(path, settings) for path in paths]
    names = [provider.name for provider in providers]
    if len(names) != len(set(names)) or "tcgdex" in names:
        raise PluginConfigError(f"Doppelte oder reservierte Namen von Preisquellen: {names}")
    return providers
