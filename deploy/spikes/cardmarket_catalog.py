"""Spike: offizielle Cardmarket-Downloads (Produktkatalog + Preisführer) für Pokémon.

Cardmarket bietet Preisführer und Produktkatalog als Datei zum Download an. Geprüft wird:
erreichbar? Format? Gibt es Setcode + Nummer im Produktnamen? Wo steht Produkt 908315
(TCGdex: Glurak M6a 137 – laut Nutzer die vereinfacht-chinesische Ausgabe)?

    docker compose exec -T api python - < deploy/spikes/cardmarket_catalog.py
"""

from __future__ import annotations

import json
from typing import Any

import httpx

UA = "Kartenkiste/0.1 (private Sammel-App, Test der offiziellen Downloads)"
BASE = "https://downloads.s3.cardmarket.com/productCatalog"
CANDIDATES = {
    "Produkte (Einzelkarten)": f"{BASE}/productList/products_singles_6.json",
    "Produkte (versiegelt)": f"{BASE}/productList/products_nonsingles_6.json",
    "Preisführer": f"{BASE}/priceGuide/price_guide_6.json",
}
out: list[str] = ["# Spike: offizielle Cardmarket-Downloads (Pokémon)\n"]


def rows_of(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def main() -> None:
    with httpx.Client(headers={"User-Agent": UA}, timeout=120, follow_redirects=True) as client:
        products: list[dict[str, Any]] = []
        for label, url in CANDIDATES.items():
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                out.append(f"## {label}\n\n- ❌ {type(exc).__name__}: {exc}\n")
                continue
            out.append(f"## {label}\n\n- `{url}` → HTTP {response.status_code}, "
                       f"{len(response.content)} Bytes, {response.headers.get('content-type')}")
            if response.status_code != 200:
                out.append(f"- Antwort: `{response.text[:200]!r}`\n")
                continue
            try:
                data = response.json()
            except ValueError:
                out.append("- kein JSON\n")
                continue
            if isinstance(data, dict):
                out.append(f"- Schlüssel oben: {sorted(data)[:10]}")
                for key in ("version", "createdAt"):
                    if key in data:
                        out.append(f"- {key}: {data[key]}")
            rows = rows_of(data)
            out.append(f"- Einträge: {len(rows)}; Felder: {sorted(rows[0]) if rows else '–'}")
            for row in rows[:3]:
                out.append(f"  - Beispiel: `{json.dumps(row, ensure_ascii=False)[:300]}`")
            hit = next((r for r in rows if r.get("idProduct") == 908315), None)
            out.append(f"- Produkt 908315: `{json.dumps(hit, ensure_ascii=False)[:300] if hit else 'nicht gefunden'}`")
            if "Einzelkarten" in label:
                products = rows
            out.append("")
        if products:
            out.append("## Suche „137“ in Produkten mit „30“ oder „M6a“ im Namen\n")
            for row in products:
                name = str(row.get("name", ""))
                if "137" in name and ("30" in name or "M6a" in name.replace(" ", "")):
                    out.append(f"- `{json.dumps(row, ensure_ascii=False)[:300]}`")
    print("\n".join(out))


main()
