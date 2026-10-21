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
import re
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

TURTOK_151_EN = TURTOK_151.replace("/de/", "/en/")
RunList = list[tuple[str, str, dict[str, Any]]]
RUNS: RunList = [
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


# Stufe C: Gegenprobe Cardmarket (überhaupt Treffer? mit Residential-Proxy?) und genauere
# eBay-Suche mit Kartennummer (Rohkarte und PSA 10).
RUNS_C: RunList = [
    (
        "Cardmarket · Turtok-ex 151 ohne Filter (englische Seite)",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": TURTOK_151_EN, "language": "any", "minCondition": "PO", "maxResults": 5},
    ),
    (
        "Cardmarket · Turtok-ex 151 deutsch NM, Residential-Proxy DE",
        "crawloop/cardmarket-listings-scraper",
        {
            "startUrls": [{"url": TURTOK_151_EN}],
            "language": "German",
            "minCondition": "NM",
            "maxItems": 10,
            "maxPages": 1,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "DE",
            },
        },
    ),
    (
        "Cardmarket · Suche „Blastoise ex“ deutsch NM (Deal-Finder im Angebotsmodus)",
        "lowlanddata/cardmarket-deal-finder",
        {
            "searchQuery": "Blastoise ex",
            "minDiscountPct": 0,
            "languages": ["German"],
            "minCondition": "NM",
            "maxProducts": 1,
            "maxItems": 10,
        },
    ),
    (
        "eBay.de verkauft · Glurak ex 183/165 PSA 10 (mit Nummer)",
        "caffein.dev/ebay-sold-listings",
        {
            "keywords": ["Glurak 183/165 PSA 10"],
            "ebaySite": "ebay.de",
            "daysToScrape": 90,
            "count": 20,
        },
    ),
    (
        "eBay.de verkauft · Glurak ex 183/165 Rohkarte",
        "caffein.dev/ebay-sold-listings",
        {
            "keywords": ["Glurak ex 183/165 -PSA -BGS -CGC"],
            "ebaySite": "ebay.de",
            "daysToScrape": 90,
            "count": 20,
        },
    ),
]


# Stufe D: beste Kandidaten aus der Store-Suche (docs/phase5/apify_store.md), alle ebay.de.
# Feldnamen laut Store-Bericht; Auswahlwerte (z. B. „ebay.de“ vs. „DE“) passt
# ``adapt_input`` anhand des Eingabeschemas automatisch an.
EBAY_GRADED = "Glurak 183/165 PSA 10"
GLURAK_JA_EN = GLURAK_JA.replace("/de/", "/en/")
RUNS_D: RunList = [
    (
        "eBay.de · epicscrapers (mit Ausschlusswörtern)",
        "epicscrapers/ebay-sold-listings-api",
        {"keywords": [EBAY_GRADED], "site": "ebay.de", "maxItems": 20, "days": 90},
    ),
    (
        "eBay.de · scrape.badger",
        "scrape.badger/ebay-sold-items-scraper",
        {"mode": "sold", "query": EBAY_GRADED, "domain": "ebay.de", "max_items": 20},
    ),
    (
        "eBay.de · astronomical_reception (Median, Empfehlung)",
        "astronomical_reception/ebay-sold-lite",
        {
            "searchQueries": [EBAY_GRADED],
            "maxItemsPerQuery": 20,
            "soldWithinDays": 90,
            "ebaySite": "ebay.de",
        },
    ),
    (
        "eBay.de · memo23 (Titel muss Begriffe enthalten)",
        "memo23/ebay-search-scraper-ppe",
        {
            "searchQueries": [EBAY_GRADED],
            "marketplace": "ebay.de",
            "mode": "sold",
            "soldWithinDays": 90,
            "titleMustInclude": ["183/165", "PSA 10"],
            "maxItems": 20,
        },
    ),
    (
        "eBay.de · harvestlab (nur verkauft)",
        "harvestlab/ebay-scraper",
        {"searchQuery": EBAY_GRADED, "ebaySite": "ebay.de", "soldOnly": True, "maxItems": 20},
    ),
    (
        "Cardmarket · Turtok-ex 151 deutsch NM (englische Seite)",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": TURTOK_151_EN, "language": "German", "minCondition": "NM", "maxResults": 10},
    ),
    (
        "Cardmarket · Turtok-ex 151 alle Sprachen ab NM (englische Seite)",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": TURTOK_151_EN, "language": "any", "minCondition": "NM", "maxResults": 10},
    ),
    (
        "Cardmarket · Glurak M6a per idProduct, englisch, ohne Filter",
        "phantom_coder/cardmarket-listings-scraper",
        {"productUrl": GLURAK_JA_EN, "language": "any", "minCondition": "PO", "maxResults": 5},
    ),
]
# Stufe E: echte Kosten je Lauf (nach Abschluss erneut abgefragt) für die eBay-Favoriten
# und: Liefert die Cardmarket-Suche Produkt-ID und Produktseite? (Der Angebots-Dienst braucht
# die Seite mit Namen, z. B. …/Singles/151/Blastoise-ex-V3-MEW200, nicht ?idProduct=…)
EBAY_RAW = "Glurak ex 183/165"
RUNS_E: RunList = [
    (
        "eBay.de · caffein.dev Rohkarte (Ausschluss im Suchbegriff)",
        "caffein.dev/ebay-sold-listings",
        {
            "keywords": [f"{EBAY_RAW} -PSA -BGS -CGC"],
            "ebaySite": "ebay.de",
            "daysToScrape": 90,
            "count": 20,
        },
    ),
    (
        "eBay.de · epicscrapers Rohkarte (Ausschlusswörter)",
        "epicscrapers/ebay-sold-listings-api",
        {
            "keywords": [EBAY_RAW],
            "excludeKeywords": ["PSA", "BGS", "CGC"],
            "site": "ebay.de",
            "maxItems": 20,
            "days": 90,
        },
    ),
    (
        "Cardmarket-Suche · „Blastoise ex“ (Produkt-ID und Seite?)",
        "lulzasaur/cardmarket-scraper",
        {"searchQueries": ["Blastoise ex"], "game": "Pokemon", "maxResults": 30},
    ),
    (
        "Cardmarket-Suche · „Charizard“ 30th (Produkt-ID und Seite?)",
        "lulzasaur/cardmarket-scraper",
        {"searchQueries": ["Charizard 30th"], "game": "Pokemon", "maxResults": 30},
    ),
]
# Stufe F: PSA-Zertifikat nachschlagen (Lugia V PSA 10 JPN aus Testfoto 04: 73270136).
PSA_CERT = os.environ.get("PSA_CERT", "73270136")
RUNS_F: RunList = [
    (
        f"PSA-Zertifikat {PSA_CERT} · fanndev (Note, Population, Verkäufe)",
        "fanndev/psa-card-cert-lookup-scraper",
        {"certNumber": PSA_CERT, "maxItems": 1},
    ),
    (
        f"PSA-Zertifikat {PSA_CERT} · lulzasaur (Population)",
        "lulzasaur/psa-pop-scraper",
        {"certNumber": PSA_CERT},
    ),
]
# Stufe G: Versiegeltes direkt von Cardmarket – mit Bild und Cardmarket-Produkt-ID?
# (Dann Bild exakt je Produkt statt Namensvergleich mit TCGplayer.)
SEALED_QUERIES = ["Prismatic Evolutions Elite Trainer Box", "Surging Sparks Booster Box"]
RUNS_G: RunList = [
    (
        "Versiegeltes · unfenced-group (Katalog, Sealed)",
        "unfenced-group/cardmarket-scraper",
        {
            "game": "pokemon",
            "searchQuery": "Elite Trainer Box",
            "productType": "sealed",
            "maxResults": 20,
        },
    ),
    (
        "Versiegeltes · lulzasaur (Suche)",
        "lulzasaur/cardmarket-scraper",
        {"searchQueries": SEALED_QUERIES, "game": "Pokemon", "maxResults": 10},
    ),
    (
        "Versiegeltes · ahmed_jasarevic (Suche)",
        "ahmed_jasarevic/cardmarket-scraper",
        {"searchQueries": SEALED_QUERIES, "game": "Pokemon", "maxResults": 10},
    ),
]
# Stufe H: parselab (vermutlich TCGdex-Wrapper) – hat er Karten, die uns fehlen?
# Koreanisch und Chinesisch fehlen bei uns fast ganz (Bestandsaufnahme), Japanisch teilweise.
RUNS_H: RunList = [
    # Namen in der Landessprache (TCGdex sucht im Namen der jeweiligen Sprache).
    *(
        (
            f"Karten · parselab · {language} · {name}",
            "parselab/pokemon-tcg-cards-scraper",
            {"language": language, "names": [name], "maxItems": 10},
        )
        for language, name in (("ko", "피카츄"), ("zh-cn", "皮卡丘"), ("ja", "ピカチュウ"))
    ),
    # Gegenprobe ohne Namen: liefert die Sprache überhaupt etwas?
    *(
        (
            f"Karten · parselab · {language} · ohne Filter",
            "parselab/pokemon-tcg-cards-scraper",
            {"language": language, "maxItems": 10},
        )
        for language in ("ko", "ja")
    ),
]
# Stufe I: PriceCharting (US-Preise, inkl. Japanisch/Gradings?) – welche Sprachen, Felder,
# Bilder? Suchbegriffe wie beim Scan: Name, Nummer, Set, Sprache.
PRICECHARTING_QUERIES = [
    "Charizard ex 199 151",  # Englisch
    "Lugia V Paradigm Trigger Japanese",  # Japanisch
    "Pikachu Korean",  # Koreanisch
    "Pikachu Chinese",  # Chinesisch
    "Glurak German",  # Deutsch
    "Prismatic Evolutions Elite Trainer Box",  # Sealed
]
RUNS_I: RunList = [
    *(
        (
            f"PriceCharting · gio21 · {query}",
            "gio21/pricecharting-scraper",
            {"searchQueries": [query], "maxItems": 5},
        )
        for query in PRICECHARTING_QUERIES
    ),
    (
        "PriceCharting · crawloop · Suche mit Bildern und Gradings",
        "crawloop/pricecharting-scraper",
        {
            "mode": "search",
            "searchQueries": PRICECHARTING_QUERIES[:3],
            "category": "pokemon",
            "maxItems": 6,
            "includeImages": True,
            "includeFullPrices": True,
        },
    ),
]
# Stufe J: komplette Sets von PriceCharting (Kartenliste mit Nummern, Bildern, Preisen) –
# Katalogquelle für Koreanisch und Chinesisch? Eingabe wird aus dem Schema gebaut.
SET_PAGES = [
    "https://www.pricecharting.com/console/pokemon-korean-electric-breaker",
    "https://www.pricecharting.com/console/pokemon-chinese-gem-pack",
]
RUNS_J: RunList = [
    (
        "Set-Seite · incognito_mode collection",
        "incognito_mode/pricecharting-collection-scraper",
        {},
    ),
    ("Set-Seite · crawloop", "crawloop/pricecharting-scraper", {}),
]
# Stufe K: Detail-Scraper je PriceCharting-Produkt – Firmen-genaue Noten, Verlauf, Bilder?
PRODUCT_PAGES = [
    "https://www.pricecharting.com/game/pokemon-scarlet-&-violet-151/charizard-ex-199",
    "https://www.pricecharting.com/game/pokemon-japanese-paradigm-trigger/lugia-v-110",
]
RUNS_K: RunList = [
    ("Produkt-Details · parsebird", "parsebird/pricecharting-product-scraper", {}),
    (
        "Produkt-Details · ecomscrape",
        "ecomscrape/pricecharting-product-details-page-scraper",
        {},
    ),
]
STAGES = {
    "B": RUNS,
    "C": RUNS_C,
    "D": RUNS_D,
    "E": RUNS_E,
    "F": RUNS_F,
    "G": RUNS_G,
    "H": RUNS_H,
    "I": RUNS_I,
    "J": RUNS_J,
    "K": RUNS_K,
}
RUN_IDS: list[tuple[str, str]] = []
# Stufe I: Produktseiten aus der günstigen Suche → danach Details über incognito_mode.
FOUND_URLS: list[str] = []
DETAIL_URLS = 2


def actor_properties(client: httpx.Client, actor: str) -> dict[str, Any]:
    """Eingabefelder laut Schema des neuesten Builds (leer, wenn nicht lesbar)."""
    data = client.get(f"{API}/acts/{actor.replace('/', '~')}").json().get("data") or {}
    build_id = ((data.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
    if not build_id:
        return {}
    build = client.get(f"{API}/actor-builds/{build_id}").json().get("data") or {}
    schema = (build.get("actorDefinition") or {}).get("input") or build.get("inputSchema")
    if isinstance(schema, str):
        schema = json.loads(schema)
    return (schema or {}).get("properties") or {}


def adapt_input(client: httpx.Client, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Auswahlwerte an das Schema anpassen (z. B. „ebay.de“ → „DE“), unbekannte Felder melden."""
    properties = actor_properties(client, actor)
    if not properties:
        return payload
    adapted = dict(payload)
    for key, value in payload.items():
        prop = properties.get(key)
        if prop is None:
            emit(f"- ⚠️ Feld `{key}` gibt es laut Schema nicht")
            continue
        enum = [str(e) for e in prop.get("enum") or []]
        if isinstance(value, str) and enum and value not in enum:
            wanted = value.lower().replace("ebay.", "")
            match = next(
                (
                    e
                    for e in enum
                    if e.lower() in (value.lower(), wanted, f"ebay_{wanted}", f"ebay-{wanted}")
                    or e.lower().endswith(f".{wanted}")
                    or (wanted == "de" and "german" in e.lower())
                ),
                None,
            )
            emit(f"- Auswahl `{key}`: „{value}“ → „{match}“ (möglich: {short(enum, 160)})")
            if match is not None:
                adapted[key] = match
    return adapted


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


def set_page_payload(
    client: httpx.Client, actor: str, urls: list[str] = SET_PAGES
) -> dict[str, Any]:
    """Stufe J/K: Eingabe aus dem Schema – erstes URL-/Sammlungsfeld bekommt die Seiten."""
    properties = actor_properties(client, actor)
    emit(f"- Eingabefelder: {short(sorted(properties), 400)}")
    for name, prop in properties.items():
        if prop.get("enum"):
            emit(f"  - `{name}`: {short(prop.get('enum'), 200)} (Standard {prop.get('default')})")
    payload: dict[str, Any] = {}
    target = next(
        (
            name
            for name in properties
            if re.search(r"url|collection|console|set|product", name, re.I)
            and properties[name].get("type") == "array"
        ),
        None,
    )
    if target is not None:
        editor = properties[target].get("editor")
        payload[target] = [{"url": url} for url in urls] if editor == "requestListSources" else urls
    if "mode" in properties:
        modes = [str(m) for m in properties["mode"].get("enum") or []]
        payload["mode"] = next((m for m in modes if re.search(r"set|console|collection", m)), None)
    for name in ("maxItems", "maxResults"):
        if name in properties:
            payload[name] = 400
    for name in (
        "includeImages",
        "includeFullPrices",
        "scrapeProductDetails",
        "includeRecentSales",
        "includePriceHistory",
        "includePopulation",
    ):
        if name in properties:
            payload[name] = True
    return {key: value for key, value in payload.items() if value is not None}


def prepare_payload(client: httpx.Client, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Eingabe für den Lauf: Stufe J aus dem Schema, ab Stufe D an das Schema angepasst."""
    stage = os.environ.get("APIFY_SPIKE_STAGE", "B").upper()
    if stage == "J":
        payload = set_page_payload(client, actor)
    elif stage == "K":
        payload = set_page_payload(client, actor, PRODUCT_PAGES)
        for name in ("maxItems", "maxResults"):
            if name in payload:
                payload[name] = len(PRODUCT_PAGES)
    emit(f"- Eingabe: `{short(payload, 400)}`")
    if stage in ("D", "E", "F", "G", "H", "I", "J", "K"):
        payload = adapt_input(client, actor, payload)
    return payload


def remember_product_url(actor: str, item: dict[str, Any]) -> None:
    """Stufe I: Produktseite des ersten Suchtreffers für den Detail-Abruf merken."""
    if actor != "gio21/pricecharting-scraper" or len(FOUND_URLS) >= DETAIL_URLS:
        return
    url = item.get("url") or item.get("productUrl") or item.get("link")
    if isinstance(url, str) and "pricecharting.com" in url:
        FOUND_URLS.append(url)


def report(client: httpx.Client, title: str, actor: str, payload: dict[str, Any]) -> None:
    emit(f"## {title}\n")
    emit(f"- Anbieter: `{actor}`")
    payload = prepare_payload(client, actor, payload)
    if os.environ.get("APIFY_SPIKE_STAGE", "B").upper() == "H":
        language = actor_properties(client, actor).get("language") or {}
        emit(
            f"- Sprachen laut Schema: {short(language.get('enum'), 200)} "
            f"(Standard {language.get('default')})"
        )

    started = time.monotonic()
    run = run_actor(client, actor, payload)
    if run is None:
        emit()
        return
    RUN_IDS.append((title, str(run.get("id"))))
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
    remember_product_url(actor, items[0])
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
    if os.environ.get("APIFY_SPIKE_STAGE", "B").upper() == "I":
        for item in items[:10]:
            emit(
                f"  - {short(field(item, 'name', 'title', 'product'), 70)} · "
                f"{short(field(item, 'console', 'set', 'category'), 50)} · "
                f"Preise {short(field(item, 'price', 'loose', 'ungraded'), 160)} · "
                f"Bild {short(field(item, 'image', 'img'), 80)}"
            )
    if os.environ.get("APIFY_SPIKE_STAGE", "B").upper() == "H":
        for item in items[:10]:
            emit(
                f"  - {short(field(item, 'name'), 60)} · Set {short(field(item, 'set'), 60)} · "
                f"Nr. {short(field(item, 'number', 'localid'), 20)} · "
                f"Bild {short(field(item, 'image'), 90)} · "
                f"Cardmarket {short(field(item, 'cardmarket'), 120)}"
            )
    if os.environ.get("APIFY_SPIKE_STAGE", "B").upper() == "G":
        with_image = [i for i in items if field(i, "image", "img", "picture", "photo")]
        emit(f"- Mit Bild: {len(with_image)} von {len(items)}")
        for item in items[:10]:
            emit(
                f"  - {short(field(item, 'name', 'title', 'product'), 80)} · "
                f"ID {short(field(item, 'idproduct', 'productid', 'product_id', 'id'), 30)} · "
                f"Bild {short(field(item, 'image', 'img', 'picture', 'photo'), 140)}"
            )
    full = (
        4000
        if os.environ.get("APIFY_SPIKE_STAGE", "B").upper() in ("F", "G", "H", "I", "J", "K")
        else 900
    )
    emit(f"- Erster Eintrag vollständig: `{short(items[0], full)}`")
    emit()


def main() -> None:
    stage = os.environ.get("APIFY_SPIKE_STAGE", "B").upper()
    runs = STAGES.get(stage, RUNS)
    emit(f"# Spike Apify, Stufe {stage}: Testläufe\n")
    token = os.environ.get("PT_APIFY_TOKEN", "").strip()
    if not token:
        emit("❌ `PT_APIFY_TOKEN` fehlt – zuerst `bash deploy/phase5_apify_token.sh`.")
        return
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Kartenkiste/0.1 (Spike)"}
    with httpx.Client(headers=headers, timeout=90) as client:
        me = client.get(f"{API}/users/me").json().get("data") or {}
        proxy = me.get("proxy") or {}
        groups = [g.get("name") for g in proxy.get("groups") or []]
        emit(f"- Verfügbare Proxy-Gruppen im Tarif: {groups or 'keine Angabe'}\n")
        for title, actor, payload in runs:
            try:
                report(client, title, actor, payload)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                emit(f"- ❌ {type(exc).__name__}: {short(str(exc), 300)}\n")
        if stage == "I":
            if FOUND_URLS:
                # Suche (günstig) → Details (Verlauf, Verkäufe, POP, große Bilder) per URL.
                report(
                    client,
                    "PriceCharting · incognito_mode · Details zu den ersten Suchtreffern",
                    "incognito_mode/pricecharting-product-scraper",
                    {
                        "products": FOUND_URLS,
                        "scrapeProductDetails": True,
                        "includeRecentSales": True,
                        "maxItems": DETAIL_URLS,
                    },
                )
            else:
                emit("- incognito_mode übersprungen: Suche lieferte keine Produkt-URL\n")
        # Kosten stehen erst nach einer Weile fest – deshalb am Ende erneut abfragen.
        time.sleep(30)
        emit("## Echte Kosten je Lauf (30 s nach dem letzten Lauf)\n")
        for title, run_id in RUN_IDS:
            run = client.get(f"{API}/actor-runs/{run_id}").json().get("data") or {}
            usage = {k: round(v, 5) for k, v in (run.get("usageUsd") or {}).items() if v}
            emit(f"- {title}: **{run.get('usageTotalUsd')} $** {short(usage, 300)}")
        emit()
        limits = client.get(f"{API}/users/me/limits").json().get("data") or {}
        usage = (limits.get("current") or {}).get("monthlyUsageUsd")
        limit = (limits.get("limits") or {}).get("maxMonthlyUsageUsd")
        emit(f"**Verbrauch diesen Monat danach: {usage} $ von {limit} $**")


main()
