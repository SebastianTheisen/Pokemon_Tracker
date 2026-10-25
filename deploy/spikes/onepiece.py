"""Spike: Datenquellen für One Piece (Katalog, Bilder, Preise) – nur lesend, kostenlos.

Geprüft wird, ob One Piece über dieselben Wege wie Pokémon in die App kommen kann:

1. Cardmarket-Downloads: welche ``idGame`` ist One Piece? Größe, Ausgaben, Kategorien,
   Namensschema (steht die Kartennummer ``OP01-001`` im Namen?), Preisführer-Felder.
2. tcgcsv.com (TCGplayer-Spiegel): Kategorien für One Piece (englisch/japanisch),
   Sets, Felder je Karte (Nummer, Seltenheit, Bild).
3. Offizielle Kartenlisten (en./www.onepiece-cardgame.com): Set-Auswahl, Bild-URLs.
4. PriceCharting: gibt es One-Piece-Seiten?

    docker compose exec -T api python - < deploy/spikes/onepiece.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import httpx

UA = "Kartenkiste/0.1 (private Sammel-App, Test der Datenquellen)"
CM = "https://downloads.s3.cardmarket.com/productCatalog"
# Kandidaten für die Spiel-ID; 6 = Pokémon zum Vergleich.
GAME_IDS = range(1, 26)
OP_HINTS = ("luffy", "zoro", "nami", "roronoa", "monkey.d", "shanks", "romance dawn")
out: list[str] = ["# Spike: Datenquellen für One Piece\n"]


def rows_of(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return [row for row in data[key] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def head_names(client: httpx.Client, game: int) -> tuple[int, list[str]]:
    """Status und erste Produktnamen – nur die ersten 8 KB, nicht die ganze Datei."""
    url = f"{CM}/productList/products_singles_{game}.json"
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                return response.status_code, []
            chunk = b""
            for part in response.iter_bytes():
                chunk += part
                if len(chunk) > 8192:
                    break
    except httpx.HTTPError as exc:
        out.append(f"- Spiel {game}: ❌ {type(exc).__name__}")
        return 0, []
    names = re.findall(rb'"name"\s*:\s*"([^"]{1,80})"', chunk)[:4]
    return 200, [n.decode("utf-8", "replace") for n in names]


def cardmarket(client: httpx.Client) -> int | None:
    out.append("## 1. Cardmarket-Downloads\n")
    found: int | None = None
    for game in GAME_IDS:
        status, names = head_names(client, game)
        if status == 200:
            out.append(f"- Spiel {game}: {names}")
            if found is None and any(h in " ".join(names).lower() for h in OP_HINTS):
                found = game
        elif status not in (0, 403, 404):
            out.append(f"- Spiel {game}: HTTP {status}")
    out.append(f"\n**One Piece = Spiel {found}**\n" if found else "\n**One Piece nicht erkannt**\n")
    if found is None:
        return None

    files = {
        "singles": f"{CM}/productList/products_singles_{found}.json",
        "nonsingles": f"{CM}/productList/products_nonsingles_{found}.json",
        "guide": f"{CM}/priceGuide/price_guide_{found}.json",
    }
    data: dict[str, Any] = {}
    for label, url in files.items():
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            out.append(f"- {label}: ❌ {type(exc).__name__}")
            continue
        out.append(f"- {label}: HTTP {response.status_code}, {len(response.content) // 1024} KB")
        if response.status_code == 200:
            data[label] = response.json()
            top = data[label]
            if isinstance(top, dict):
                out.append(f"  - Schlüssel: {sorted(top)[:8]}, createdAt={top.get('createdAt')}")

    singles = rows_of(data.get("singles"), "products")
    if singles:
        out.append(f"\n### Einzelkarten: {len(singles)}")
        out.append(f"- Felder: {sorted(singles[0])}")
        expansions = Counter(row.get("idExpansion") for row in singles)
        out.append(f"- Ausgaben: {len(expansions)}, größte: {expansions.most_common(5)}")
        out.append(
            f"- Kategorien: {Counter(row.get('categoryName') for row in singles).most_common(5)}"
        )
        with_code = sum(
            bool(re.search(r"[A-Z]{2,4}\d{0,2}-\d{3}", str(row.get("name")))) for row in singles
        )
        with_version = sum("(V." in str(row.get("name")) for row in singles)
        out.append(
            f"- Name enthält Kartennummer (OP01-001): {with_code}, mit „(V.x)“: {with_version}"
        )
        for row in singles[:3] + singles[len(singles) // 2 : len(singles) // 2 + 4] + singles[-4:]:
            out.append(f"  - `{json.dumps(row, ensure_ascii=False)[:220]}`")
        meta = Counter(row.get("idMetacard") for row in singles)
        out.append(
            f"- idMetacard mehrfach (Sprachen/Varianten): {sum(1 for v in meta.values() if v > 1)}"
        )

    sealed = rows_of(data.get("nonsingles"), "products")
    if sealed:
        out.append(f"\n### Versiegelt: {len(sealed)}")
        out.append(
            f"- Kategorien: {Counter(row.get('categoryName') for row in sealed).most_common(8)}"
        )
        for row in sealed[:4]:
            out.append(f"  - `{json.dumps(row, ensure_ascii=False)[:200]}`")

    guide = rows_of(data.get("guide"), "priceGuides")
    if guide:
        out.append(f"\n### Preisführer: {len(guide)} Einträge")
        out.append(f"- Felder: {sorted(guide[0])}")
        with_trend = sum(bool(row.get("trend")) for row in guide)
        out.append(f"- mit Trend: {with_trend}")
        out.append(f"  - Beispiel: `{json.dumps(guide[0])[:300]}`")
    return found


def tcgcsv(client: httpx.Client) -> None:
    out.append("\n## 2. tcgcsv.com (TCGplayer)\n")
    try:
        categories = rows_of(
            client.get("https://tcgcsv.com/tcgplayer/categories").json(), "results"
        )
    except (httpx.HTTPError, ValueError) as exc:
        out.append(f"- ❌ {type(exc).__name__}: {exc}")
        return
    hits = [
        c
        for c in categories
        if "one piece" in str(c.get("name", "")).lower()
        or "one piece" in str(c.get("displayName", "")).lower()
    ]
    for category in hits:
        cid = category.get("categoryId")
        groups = rows_of(client.get(f"https://tcgcsv.com/tcgplayer/{cid}/groups").json(), "results")
        out.append(
            f"- Kategorie {cid} „{category.get('displayName') or category.get('name')}“: "
            f"{len(groups)} Sets"
        )
        for group in groups[:3] + groups[-3:]:
            out.append(
                f"  - {group.get('groupId')} {group.get('abbreviation')!r} {group.get('name')}"
            )
        if not groups:
            continue
        sample = max(groups, key=lambda g: str(g.get("publishedOn") or ""))
        sample = next(
            (g for g in groups if str(g.get("abbreviation", "")).upper() == "OP01"), sample
        )
        products = rows_of(
            client.get(f"https://tcgcsv.com/tcgplayer/{cid}/{sample['groupId']}/products").json(),
            "results",
        )
        prices = rows_of(
            client.get(f"https://tcgcsv.com/tcgplayer/{cid}/{sample['groupId']}/prices").json(),
            "results",
        )
        out.append(
            f"  - Set {sample.get('abbreviation')}: {len(products)} Produkte, {len(prices)} Preise"
        )
        for product in products[:3]:
            ext = {e.get("name"): e.get("value") for e in product.get("extendedData") or []}
            out.append(
                f"    - {product.get('name')!r} | {product.get('imageUrl')} | "
                f"{ {k: ext.get(k) for k in ('Number', 'Rarity', 'Color', 'CardType')} }"
            )
        if prices:
            out.append(f"    - Preis-Beispiel: `{json.dumps(prices[0])[:200]}`")


def official(client: httpx.Client) -> None:
    out.append("\n## 3. Offizielle Kartenlisten\n")
    for base in (
        "https://en.onepiece-cardgame.com",
        "https://www.onepiece-cardgame.com",
        "https://asia-en.onepiece-cardgame.com",
    ):
        url = f"{base}/cardlist/"
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            out.append(f"- {url}: ❌ {type(exc).__name__}")
            continue
        html = response.text
        series = re.findall(r'<option value="(\d{6})"[^>]*>([^<]+)</option>', html)
        out.append(
            f"- {url}: HTTP {response.status_code}, {len(html) // 1024} KB, "
            f"{len(series)} Sets in der Auswahl, z. B. {series[:3]}"
        )
        if not series:
            continue
        sid = series[-1][0]
        page = client.get(url, params={"series": sid})
        cards = re.findall(r'id="([A-Z]{1,4}\d{0,2}-\d{3}(?:_p\d+)?)"', page.text)
        images = re.findall(r'data-src="([^"]+cardlist/card/[^"]+)"', page.text)
        out.append(
            f"  - Set {sid}: HTTP {page.status_code}, {len(set(cards))} Karten-IDs, "
            f"z. B. {cards[:4]}, Bild z. B. {images[:1]}"
        )
        robots = client.get(f"{base}/robots.txt")
        out.append(f"  - robots.txt: HTTP {robots.status_code} `{robots.text[:160]!r}`")


def pricecharting(client: httpx.Client) -> None:
    out.append("\n## 4. PriceCharting\n")
    for url in (
        "https://www.pricecharting.com/category/one-piece-cards",
        "https://www.pricecharting.com/console/one-piece-romance-dawn",
    ):
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            out.append(f"- {url}: ❌ {type(exc).__name__}")
            continue
        rows = len(re.findall(r'<tr id="product-\d+"', response.text))
        out.append(f"- {url}: HTTP {response.status_code}, {rows} Produktzeilen")


def main() -> None:
    headers = {"User-Agent": UA}
    with httpx.Client(headers=headers, timeout=180, follow_redirects=True) as client:
        for step in (cardmarket, tcgcsv, official, pricecharting):
            try:
                step(client)
            except Exception as exc:  # Spike: jeden Schritt einzeln berichten
                out.append(f"- ❌ {step.__name__}: {type(exc).__name__}: {exc}")
    print("\n".join(out))


main()
