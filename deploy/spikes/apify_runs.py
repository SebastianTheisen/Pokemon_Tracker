"""Spike Apify, Stufe B: echte Testläufe mit kleinen Mengen und Kostendeckel je Lauf.

Kandidaten und Eingaben aus Stufe A (``docs/phase5/apify_probe.md``):

* Cardmarket-Angebote über die Produktseite, gefiltert nach Sprache und Mindestzustand –
  Glurak 30th Celebration (japanisch, 907902) und Turtok-ex 151 (deutsch).
* eBay.de-Verkäufe für eine gegradete Karte („PSA 10“).

Je Lauf höchstens :data:`MAX_CHARGE_USD` – insgesamt deutlich unter einem Dollar.

    docker compose exec -T api python - < deploy/spikes/apify_runs.py
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from typing import Any

import httpx

API = "https://api.apify.com/v2"
MAX_CHARGE_USD = 0.10
RUN_TIMEOUT_SECONDS = 300
GLURAK_JA = "https://www.cardmarket.com/de/Pokemon/Products?idProduct=907902"
TURTOK_151 = "https://www.cardmarket.com/de/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200"
EBAY_QUERY = "Glurak ex 151 PSA 10"

RUNS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "Cardmarket · Glurak M6a japanisch NM (Link per idProduct)",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": GLURAK_JA, "language": "Japanese", "minCondition": "NM", "maxResults": 10},
    ),
    (
        "Cardmarket · Turtok-ex 151 deutsch NM",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": TURTOK_151, "language": "German", "minCondition": "NM", "maxResults": 10},
    ),
    (
        "Cardmarket · Turtok-ex 151 deutsch NM (zweiter Anbieter)",
        "crawloop/cardmarket-listings-scraper",
        {
            "startUrls": [{"url": TURTOK_151}],
            "language": "German",
            "minCondition": "NM",
            "locale": "de",
            "maxItems": 10,
            "maxPages": 1,
        },
    ),
    (
        "eBay.de verkauft · PSA 10 (meistgenutzt)",
        "caffein.dev/ebay-sold-listings",
        {"keywords": [EBAY_QUERY], "ebaySite": "ebay.de", "daysToScrape": 90, "count": 20},
    ),
    (
        "eBay.de verkauft · PSA 10 (kostenloser Anbieter, Preisführer je Note)",
        "yumitori/ebay-sold-scraper",
        {"queries": [EBAY_QUERY], "marketplace": "DE", "days": "90", "maxComps": 20},
    ),
]


def emit(line: str = "") -> None:
    print(line, flush=True)


def short(value: object, limit: int = 200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def field(item: dict[str, Any], *needles: str) -> Any:
    """Erster Wert, dessen Schlüssel eines der Stichworte enthält (Felder je Anbieter anders)."""
    for key, value in item.items():
        if any(needle in key.lower() for needle in needles):
            return value
    return None


def run_actor(client: httpx.Client, actor: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    response = client.post(
        f"{API}/acts/{actor.replace('/', '~')}/runs",
        params={
            "timeout": RUN_TIMEOUT_SECONDS,
            "maxTotalChargeUsd": MAX_CHARGE_USD,
            "waitForFinish": 60,
        },
        json=payload,
    )
    if response.status_code not in (httpx.codes.OK, httpx.codes.CREATED):
        emit(f"- ❌ Start: HTTP {response.status_code}: {short(response.text, 300)}")
        return None
    run: dict[str, Any] = response.json()["data"]
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS + 60
    while run.get("status") in ("READY", "RUNNING") and time.monotonic() < deadline:
        response = client.get(f"{API}/actor-runs/{run['id']}", params={"waitForFinish": 60})
        run = response.json()["data"]
    return run


def report(client: httpx.Client, title: str, actor: str, payload: dict[str, Any]) -> None:
    emit(f"## {title}\n")
    emit(f"- Anbieter: `{actor}`")
    emit(f"- Eingabe: `{short(payload, 400)}`")
    started = time.monotonic()
    run = run_actor(client, actor, payload)
    if run is None:
        emit()
        return
    emit(
        f"- Status: {run.get('status')} {short(run.get('statusMessage') or '', 200)} · "
        f"Dauer {time.monotonic() - started:.0f} s"
    )
    emit(
        f"- Kosten: {run.get('usageTotalUsd')} $ "
        f"(Ereignisse: {short(run.get('chargedEventCounts') or {}, 200)})"
    )
    dataset = run.get("defaultDatasetId")
    if not dataset:
        emit()
        return
    items = client.get(
        f"{API}/datasets/{dataset}/items", params={"clean": "true", "limit": 50}
    ).json()
    emit(f"- Ergebnisse: {len(items)}")
    if not items:
        emit()
        return
    emit(f"- Felder: {short(sorted(items[0]), 600)}")
    languages = Counter(str(field(i, "language", "lang")) for i in items)
    conditions = Counter(str(field(i, "condition")) for i in items)
    emit(f"- Sprachen: {dict(languages)} · Zustände: {dict(conditions)}")
    for item in items[:6]:
        emit(
            "  - "
            + " · ".join(
                short(value, 90)
                for value in (
                    field(item, "title", "name", "product"),
                    field(item, "price", "sold"),
                    field(item, "condition"),
                    field(item, "language"),
                    field(item, "date", "ended", "sold_at"),
                    field(item, "seller", "country", "location"),
                )
                if value not in (None, "")
            )
        )
    emit(f"- Erster Eintrag vollständig: `{short(items[0], 900)}`")
    emit()


def main() -> None:
    emit("# Spike Apify, Stufe B: Testläufe\n")
    token = os.environ.get("PT_APIFY_TOKEN", "").strip()
    if not token:
        emit("❌ `PT_APIFY_TOKEN` fehlt – zuerst `bash deploy/phase5_apify_token.sh`.")
        return
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=90) as client:
        for title, actor, payload in RUNS:
            try:
                report(client, title, actor, payload)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                emit(f"- ❌ {type(exc).__name__}: {short(str(exc), 300)}\n")
        limits = client.get(f"{API}/users/me/limits").json().get("data") or {}
        usage = (limits.get("current") or {}).get("monthlyUsageUsd")
        limit = (limits.get("limits") or {}).get("maxMonthlyUsageUsd")
        emit(f"**Verbrauch diesen Monat danach: {usage} $ von {limit} $**")


main()
