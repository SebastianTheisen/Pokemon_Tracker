"""Simuliertes TCGdex für Tests (httpx.MockTransport) – Struktur wie im Phase-0-Spike."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

import httpx

ASSETS = "https://assets.tcgdex.net"


def _card(lang: str, set_path: str, card_id: str, local_id: str, name: str) -> dict[str, Any]:
    return {
        "id": card_id,
        "localId": local_id,
        "name": name,
        "image": f"{ASSETS}/{lang}/{set_path}/{local_id}",
    }


def _set(
    set_id: str,
    name: str,
    serie: str,
    release: str,
    cards: list[dict[str, Any]],
    total: int | None = None,
) -> dict[str, Any]:
    return {
        "id": set_id,
        "name": name,
        "logo": f"{ASSETS}/logo/{set_id}",
        "symbol": f"{ASSETS}/symbol/{set_id}",
        "cardCount": {"total": total if total is not None else len(cards), "official": 203},
        "serie": {"id": "swsh", "name": serie},
        "releaseDate": release,
        "cards": cards,
    }


def default_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    """Kleiner Katalog: Drachenwandel/Evolving Skies (DE/EN) und ein japanisches Set."""
    return {
        "de": {
            "swsh7": _set(
                "swsh7",
                "Drachenwandel",
                "Schwert & Schild",
                "2021-08-27",
                [
                    _card("de", "swsh/swsh7", "swsh7-095", "095", "Nachtara V"),
                    _card("de", "swsh/swsh7", "swsh7-188", "188", "Nachtara V"),
                    _card("de", "swsh/swsh7", "swsh7-215", "215", "Nachtara VMAX"),
                    _card("de", "swsh/swsh7", "swsh7-007", "007", "Glurak"),
                ],
            ),
        },
        "en": {
            "swsh7": _set(
                "swsh7",
                "Evolving Skies",
                "Sword & Shield",
                "2021-08-27",
                [
                    _card("en", "swsh/swsh7", "swsh7-095", "095", "Umbreon V"),
                    _card("en", "swsh/swsh7", "swsh7-188", "188", "Umbreon V"),
                    _card("en", "swsh/swsh7", "swsh7-215", "215", "Umbreon VMAX"),
                    _card("en", "swsh/swsh7", "swsh7-007", "007", "Charizard"),
                ],
            ),
        },
        "ja": {
            "S12": _set(
                "S12",
                "パラダイムトリガー",
                "ソード&シールド",
                "2022-10-21",
                [
                    _card("ja", "S/S12", "S12-110", "110", "ルギアV"),
                    _card("ja", "S/S12", "S12-079", "079", "ルギアV"),
                ],
            ),
            # Set-ID mit Sonderzeichen wie im echten Katalog (Sun & Moon „+“-Sets).
            "SM1+": _set(
                "SM1+",
                "サン&ムーン 強化拡張パック",
                "サン&ムーン",
                "2017-02-03",
                [_card("ja", "SM/SM1+", "SM1+-001", "001", "モクロー")],
            ),
        },
    }


class FakeTcgdex:
    """Zählt Abrufe und kann einzelne Sets fehlschlagen lassen."""

    def __init__(self, catalog: dict[str, dict[str, dict[str, Any]]] | None = None) -> None:
        self.catalog = catalog or default_catalog()
        self.set_requests: list[str] = []
        self.failing_sets: set[str] = set()
        self.card_details: dict[tuple[str, str], dict[str, Any]] = {}  # (Sprache, Karten-ID)

    def handler(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        raw_path = request.url.raw_path.decode("ascii")
        if "+" in raw_path:
            # Wie der echte Server (VPS-Lauf Phase 1): unkodiertes „+“ → 404.
            return httpx.Response(404)
        parts = [unquote(part) for part in raw_path.strip("/").split("/")]  # v2/{lang}/sets[/{id}]
        if len(parts) == 4 and parts[0] == "v2" and parts[2] == "cards":
            details = self.card_details.get((parts[1], parts[3]))
            return httpx.Response(200, json=details) if details else httpx.Response(404)
        if len(parts) < 3 or parts[0] != "v2" or parts[2] != "sets":
            return httpx.Response(404)
        language = parts[1]
        sets = self.catalog.get(language, {})
        if len(parts) == 3:
            briefs = [
                {
                    k: v
                    for k, v in data.items()
                    if k in ("id", "name", "logo", "symbol", "cardCount")
                }
                for data in sets.values()
            ]
            return httpx.Response(200, json=briefs)
        set_id = parts[3]
        self.set_requests.append(f"{language}/{set_id}")
        if set_id in self.failing_sets:
            return httpx.Response(500)
        if set_id not in sets:
            return httpx.Response(404)
        return httpx.Response(200, json=sets[set_id])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
