"""Spike Apify, Store-Suche (kostenlos, startet nichts): alle Cardmarket- und eBay-Dienste.

Durchsucht den Apify-Store mit mehreren Suchbegriffen, liest von jedem Treffer die
Eingabefelder und bewertet automatisch:

* eBay: Kann er **ebay.de** (Deutschland)? Kann er **verkaufte** Artikel?
* Cardmarket: Filter nach **Sprache** und **Zustand**? Produktseite oder Suchbegriff?

    docker compose exec -T api python - < deploy/spikes/apify_store.py

Der Token kommt aus ``PT_APIFY_TOKEN`` (.env) und wird nie ausgegeben.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import httpx

API = "https://api.apify.com/v2"
SEARCHES = {
    "cardmarket": ["cardmarket", "cardmarket pokemon", "mkm", "pokemon card price", "tcg price"],
    "ebay": [
        "ebay sold",
        "ebay sold listings",
        "ebay completed listings",
        "ebay scraper",
        "ebay germany",
        "ebay price",
        "pokemon card ebay",
    ],
}
PAGE_SIZE = 100
MAX_DETAILS = 120


def emit(line: str = "") -> None:
    print(line, flush=True)


def short(value: object, limit: int = 140) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Candidate:
    actor_id: str
    kind: str
    title: str
    description: str
    users: int
    users_30_days: int
    modified: str
    pricing: str
    schema_text: str = ""
    fields: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    score: int = 0


def pricing_text(info: dict[str, Any] | None) -> str:
    if not info:
        return "?"
    model = info.get("pricingModel")
    if model == "FREE":
        return "kostenlos (nur Plattform)"
    if model == "PRICE_PER_DATASET_ITEM":
        return f"{info.get('pricePerUnitUsd')} $/Ergebnis"
    if model == "FLAT_PRICE_PER_MONTH":
        return f"Miete {info.get('pricePerUnitUsd')} $/Monat"
    if model == "PAY_PER_EVENT":
        events = (info.get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
        parts = []
        for name, event in events.items():
            price = event.get("eventPriceUsd")
            if price is None:
                tiers = event.get("eventTieredPricingUsd") or {}
                price = (tiers.get("FREE") or {}).get("tieredEventPriceUsd")
            parts.append(f"{name}={price}")
        return "je Ereignis: " + ", ".join(parts)
    return str(model)


def store_search(client: httpx.Client, term: str) -> list[dict[str, Any]]:
    response = client.get(f"{API}/store", params={"search": term, "limit": PAGE_SIZE})
    if response.status_code != httpx.codes.OK:
        emit(f"- ❌ Suche „{term}“: HTTP {response.status_code}")
        return []
    data = response.json().get("data") or {}
    items = data.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def load_schema(client: httpx.Client, candidate: Candidate) -> None:
    response = client.get(f"{API}/acts/{candidate.actor_id.replace('/', '~')}")
    if response.status_code != httpx.codes.OK:
        return
    actor = response.json().get("data") or {}
    build_id = ((actor.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
    if not build_id:
        return
    build = client.get(f"{API}/actor-builds/{build_id}").json().get("data") or {}
    schema = (build.get("actorDefinition") or {}).get("input") or build.get("inputSchema")
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except ValueError:
            schema = {}
    if isinstance(schema, dict):
        candidate.schema_text = json.dumps(schema, ensure_ascii=False).lower()
        candidate.fields = list((schema.get("properties") or {}).keys())


def judge_ebay(c: Candidate) -> None:
    text = f"{c.schema_text} {c.description.lower()} {c.title.lower()}"
    germany = bool(
        re.search(r"ebay\.de\b|\"de\"|germany|deutschland|ebay_de|\"ebay-de\"", c.schema_text)
    )
    sold = "sold" in text or "completed" in text or "verkauft" in text
    if germany:
        c.notes.append("✅ ebay.de")
        c.score += 3
    elif re.search(r"ebay\.de|germany", text):
        c.notes.append("❔ ebay.de nur in Beschreibung")
        c.score += 1
    else:
        c.notes.append("❌ kein ebay.de")
    if sold:
        c.notes.append("✅ verkauft")
        c.score += 2
    if "pokemon" in text or "trading card" in text or "graded" in text or "psa" in text:
        c.notes.append("🃏 Karten-Bezug")
        c.score += 1


def judge_cardmarket(c: Candidate) -> None:
    text = f"{c.schema_text} {c.description.lower()}"
    if "cardmarket" not in text:
        c.notes.append("❌ kein Cardmarket")
        c.score -= 5
        return
    language = "german" in c.schema_text or '"language' in c.schema_text
    condition = "mincondition" in c.schema_text or "condition" in c.schema_text
    listings = "listing" in text or "offer" in text or "seller" in text
    if language:
        c.notes.append("✅ Sprache")
        c.score += 2
    if condition:
        c.notes.append("✅ Zustand")
        c.score += 2
    if listings:
        c.notes.append("✅ Angebote")
        c.score += 1
    if "pokemon" in text:
        c.notes.append("🃏 Pokémon")
        c.score += 1


def main() -> None:
    emit("# Spike Apify: Store-Suche Cardmarket und eBay\n")
    token = os.environ.get("PT_APIFY_TOKEN", "").strip()
    if not token:
        emit("❌ `PT_APIFY_TOKEN` fehlt – zuerst `bash deploy/phase5_apify_token.sh`.")
        return
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=60) as client:
        candidates: dict[str, Candidate] = {}
        for kind, terms in SEARCHES.items():
            for term in terms:
                for item in store_search(client, term):
                    actor_id = f"{item.get('username')}/{item.get('name')}"
                    if actor_id in candidates:
                        continue
                    stats = item.get("stats") or {}
                    candidates[actor_id] = Candidate(
                        actor_id=actor_id,
                        kind=kind,
                        title=str(item.get("title") or ""),
                        description=str(item.get("description") or ""),
                        users=int(stats.get("totalUsers") or 0),
                        users_30_days=int(stats.get("totalUsers30Days") or 0),
                        modified=str(item.get("modifiedAt") or "")[:10],
                        pricing=pricing_text(item.get("currentPricingInfo")),
                    )
        # Nur thematisch passende Treffer genauer ansehen.
        relevant = [
            c
            for c in candidates.values()
            if ("cardmarket" in f"{c.title} {c.description}".lower())
            or ("ebay" in f"{c.title} {c.description}".lower())
        ]
        relevant.sort(key=lambda c: c.users_30_days, reverse=True)
        relevant = relevant[:MAX_DETAILS]
        emit(f"- Treffer gesamt: {len(candidates)}, davon zu Cardmarket/eBay: {len(relevant)}\n")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda c: load_schema(client, c), relevant))
        for c in relevant:
            is_cardmarket = "cardmarket" in f"{c.title} {c.description}".lower()
            c.kind = "cardmarket" if is_cardmarket else "ebay"
            (judge_cardmarket if is_cardmarket else judge_ebay)(c)

        for kind, title in (("cardmarket", "Cardmarket"), ("ebay", "eBay")):
            group = sorted(
                (c for c in relevant if c.kind == kind),
                key=lambda c: (c.score, c.users_30_days),
                reverse=True,
            )
            emit(f"## {title} ({len(group)})\n")
            emit("| Dienst | Bewertung | Nutzer 30 T. / ges. | Preis | geändert |")
            emit("|---|---|---|---|---|")
            for c in group:
                emit(
                    f"| `{c.actor_id}` | {' '.join(c.notes)} | {c.users_30_days} / {c.users} | "
                    f"{short(c.pricing, 60)} | {c.modified} |"
                )
            emit()
            emit(f"### Details der besten {min(12, len(group))}\n")
            for c in group[:12]:
                emit(f"- `{c.actor_id}` – {short(c.title, 80)}")
                emit(f"  - {short(c.description, 260)}")
                emit(f"  - Eingabefelder: {short(', '.join(c.fields), 400)}")
            emit()


POKEMON_SEARCHES = [
    "pokemon",
    "pokemon card",
    "pokemon tcg",
    "pokemon price",
    "pokemon japanese",
    "pokemon sealed",
    "psa",
    "psa population",
    "graded card",
    "trading card",
    "tcg",
    "card grading",
    "card scanner",
    "collectibles price",
    "pricecharting",
    "tcgplayer",
    "snkrdunk",
    "mercari japan",
    "yuyu tei",
    "card rush",
]
POKEMON_WORDS = re.compile(r"pok[eé]mon|\btcg\b|trading card|\bpsa\b|graded|collectible", re.I)
# Wofür ein Dienst taugen könnte – Stichworte in Titel/Beschreibung.
TOPICS = {
    "💶 Preise": r"price|preis|sold|market|value|comps|trend",
    "🏅 Grading/PSA": r"\bpsa\b|bgs|cgc|grad|population|\bpop\b|cert",
    "🇯🇵 Japan": r"japan|snkrdunk|mercari|yuyu|card ?rush|surugaya|jp\b",
    "📦 Sealed": r"sealed|booster|display|etb|box",
    "🗂 Katalog/Bilder": r"database|catalog|card list|set list|image|scan",
    "🛒 Marktplatz": r"ebay|cardmarket|tcgplayer|vinted|kleinanzeigen|mercari|pricecharting",
}


def main_pokemon() -> None:
    emit("# Spike Apify: Store-Suche Pokémon\n")
    token = os.environ.get("PT_APIFY_TOKEN", "").strip()
    if not token:
        emit("❌ `PT_APIFY_TOKEN` fehlt – zuerst `bash deploy/phase5_apify_token.sh`.")
        return
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=60) as client:
        candidates: dict[str, Candidate] = {}
        for term in POKEMON_SEARCHES:
            for item in store_search(client, term):
                actor_id = f"{item.get('username')}/{item.get('name')}"
                text = f"{item.get('title')} {item.get('description')}"
                if actor_id in candidates or not POKEMON_WORDS.search(text):
                    continue
                stats = item.get("stats") or {}
                candidates[actor_id] = Candidate(
                    actor_id=actor_id,
                    kind="pokemon",
                    title=str(item.get("title") or ""),
                    description=str(item.get("description") or ""),
                    users=int(stats.get("totalUsers") or 0),
                    users_30_days=int(stats.get("totalUsers30Days") or 0),
                    modified=str(item.get("modifiedAt") or "")[:10],
                    pricing=pricing_text(item.get("currentPricingInfo")),
                )
        ranked = sorted(candidates.values(), key=lambda c: c.users_30_days, reverse=True)
        emit(f"- Passende Dienste: {len(ranked)} (Suchbegriffe: {', '.join(POKEMON_SEARCHES)})\n")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda c: load_schema(client, c), ranked[:MAX_DETAILS]))
        for c in ranked:
            text = f"{c.title} {c.description}"
            c.notes = [label for label, pattern in TOPICS.items() if re.search(pattern, text, re.I)]
            if re.search(r"ebay\.de|germany|deutsch|\"de\"", c.schema_text):
                c.notes.append("🇩🇪 DE")
        for label in TOPICS:
            group = [c for c in ranked if label in c.notes]
            emit(f"## {label} ({len(group)})\n")
            emit("| Dienst | Themen | Nutzer 30 T. / ges. | Preis |")
            emit("|---|---|---|---|")
            for c in group[:40]:
                emit(
                    f"| `{c.actor_id}` | {' '.join(c.notes)} | {c.users_30_days} / {c.users} | "
                    f"{short(c.pricing, 50)} |"
                )
            emit()
        emit("## Beschreibungen (alle, nach Nutzern)\n")
        for c in ranked:
            emit(f"- `{c.actor_id}` ({c.users_30_days} Nutzer/30 T.) – {short(c.title, 90)}")
            emit(f"  - {short(c.description, 300)}")
            if c.fields:
                emit(f"  - Eingabe: {short(', '.join(c.fields), 250)}")


if os.environ.get("APIFY_STORE_TOPIC") == "pokemon":
    main_pokemon()
else:
    main()
