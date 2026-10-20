"""Spike Apify, Stufe A (kostenlos): Konto, Guthaben und Eingabefelder der Kandidaten.

Startet **keinen** Lauf – es werden nur Beschreibungen abgefragt, das kostet kein Guthaben.
Mit den Eingabefeldern schreiben wir danach Stufe B (echte Testläufe mit kleinen Mengen).

    docker compose exec -T api python - < deploy/spikes/apify_probe.py

Der Token kommt aus ``PT_APIFY_TOKEN`` (.env) und wird nie ausgegeben.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

API = "https://api.apify.com/v2"
CANDIDATES = {
    "Cardmarket-Angebote": [
        "phantom_coder/cardmarket-listings-scraper",
        "crawloop/cardmarket-listings-scraper",
        "lowlanddata/cardmarket-deal-finder",
        "lulzasaur/cardmarket-scraper",
    ],
    "eBay verkauft": [
        "automation-lab/ebay-sold-scraper",
        "parsebird/ebay-sold-listings-scraper",
        "yumitori/ebay-sold-scraper",
        "tnodes/ebay-sold-scraper",
        "caffein.dev/ebay-sold-listings",
    ],
}


def emit(line: str = "") -> None:
    print(line, flush=True)


def short(value: object, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def get(client: httpx.Client, path: str) -> dict[str, Any] | None:
    response = client.get(f"{API}{path}")
    if response.status_code != 200:
        emit(
            f"  - ❌ `{path.split('?')[0]}` → HTTP {response.status_code}: {short(response.text, 200)}"
        )
        return None
    data = response.json().get("data")
    return data if isinstance(data, dict) else None


def input_schema(client: httpx.Client, actor: dict[str, Any]) -> dict[str, Any] | None:
    build_id = ((actor.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
    if not build_id:
        return None
    build = get(client, f"/actor-builds/{build_id}")
    if build is None:
        return None
    schema = (build.get("actorDefinition") or {}).get("input") or build.get("inputSchema")
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except ValueError:
            return None
    return schema if isinstance(schema, dict) else None


def describe_pricing(actor: dict[str, Any]) -> str:
    infos = actor.get("pricingInfos") or []
    if not infos:
        return "keine Angabe (nur Plattform-Nutzung)"
    info = infos[-1]
    model = info.get("pricingModel")
    if model == "PRICE_PER_DATASET_ITEM":
        return f"{info.get('pricePerUnitUsd')} $ je Ergebnis ({info.get('unitName')})"
    if model == "PAY_PER_EVENT":
        events = (info.get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
        parts = [
            f"{name}: {event.get('eventPriceUsd')} $ ({short(event.get('eventTitle'), 40)})"
            for name, event in events.items()
        ]
        return "je Ereignis – " + "; ".join(parts)
    if model == "FLAT_PRICE_PER_MONTH":
        return (
            f"{info.get('pricePerUnitUsd')} $ im Monat (Miete, Testtage {info.get('trialMinutes')})"
        )
    return short(info)


def main() -> None:
    emit("# Spike Apify, Stufe A: Kandidaten und Eingabefelder\n")
    token = os.environ.get("PT_APIFY_TOKEN", "").strip()
    if not token:
        emit("❌ `PT_APIFY_TOKEN` fehlt – zuerst `bash deploy/phase5_apify_token.sh`.")
        return
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=60) as client:
        me = get(client, "/users/me")
        if me is None:
            emit("❌ Token wird nicht akzeptiert.")
            return
        plan = (me.get("plan") or {}).get("id")
        emit(f"- Konto: {me.get('username')} · Tarif: {plan}")
        limits = get(client, "/users/me/limits")
        if limits:
            usage = (limits.get("current") or {}).get("monthlyUsageUsd")
            limit = (limits.get("limits") or {}).get("maxMonthlyUsageUsd")
            cycle = limits.get("monthlyUsageCycle") or {}
            emit(f"- Verbrauch diesen Monat: {usage} $ von {limit} $ (bis {cycle.get('endAt')})")
        emit()
        for group, actor_ids in CANDIDATES.items():
            emit(f"## {group}\n")
            for actor_id in actor_ids:
                emit(f"### `{actor_id}`\n")
                actor = get(client, f"/acts/{actor_id.replace('/', '~')}")
                if actor is None:
                    emit()
                    continue
                stats = actor.get("stats") or {}
                emit(f"- Titel: {actor.get('title')}")
                emit(f"- Preis: {describe_pricing(actor)}")
                emit(
                    f"- Nutzer gesamt / 30 Tage: {stats.get('totalUsers')} / "
                    f"{stats.get('totalUsers30Days')}, zuletzt geändert {actor.get('modifiedAt')}"
                )
                emit(f"- Beschreibung: {short(actor.get('description'), 300)}")
                schema = input_schema(client, actor)
                properties = (schema or {}).get("properties") or {}
                required = set((schema or {}).get("required") or [])
                emit(f"- Eingabefelder ({len(properties)}):")
                for name, prop in properties.items():
                    details = [str(prop.get("type"))]
                    if name in required:
                        details.append("Pflicht")
                    for key in ("enum", "default", "prefill", "example"):
                        if key in prop:
                            details.append(f"{key}={short(prop[key], 120)}")
                    emit(f"  - `{name}` ({', '.join(details)}): {short(prop.get('title'), 80)}")
                    if prop.get("description"):
                        emit(f"    - {short(prop['description'], 220)}")
                emit()


main()
