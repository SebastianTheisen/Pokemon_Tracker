"""Phase-0-Spike: prüft die Datenquellen und schreibt einen Markdown-Bericht.

Geprüft wird:

* **TCGdex** – Sprachabdeckung (Anzahl Sets je Sprache), Felder einer Beispielkarte,
  vorhandene Cardmarket-Preisfelder.
* **pokemontcg.io** – Felder und Cardmarket-Preise einer Beispielkarte (nur Englisch).
* **Cardmarket** – genau *eine* Anfrage an eine Übersichtsseite, um festzustellen, ob
  Seiten ohne Umgehung abrufbar sind oder ob eine Bot-Sperre (Captcha/Cloudflare) greift.

Aufruf (aus ``backend/``)::

    uv run python scripts/spike_datasources.py --out ../docs/spikes/datenquellen.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

TCGDEX_BASE = "https://api.tcgdex.net/v2"
POKEMONTCG_BASE = "https://api.pokemontcg.io/v2"
CARDMARKET_PROBE_URL = "https://www.cardmarket.com/de/Pokemon/Products/Singles"

TCGDEX_LANGUAGES = ("de", "en", "ja", "ko", "zh-cn", "zh-tw")
SAMPLE_CARD_ID = "swsh7-215"  # Nachtara VMAX, Drachenwandel/Evolving Skies 215
SAMPLE_IMAGE_BASE = "https://assets.tcgdex.net/de/swsh/swsh7/215"
ASIAN_LANGUAGES = ("ja", "ko", "zh-tw", "zh-cn")
ASIAN_SETS_PER_LANGUAGE = 2
ASIAN_CARDS_PER_SET = 2
USER_AGENT = "PokemonTracker-Spike/0.1 (private Sammel-App, geringe Last)"
BOT_WALL_MARKERS = ("cf-chl", "Just a moment", "captcha", "Attention Required")


@dataclass
class SpikeReport:
    """Gesammelte Ergebnisse, die am Ende als Markdown ausgegeben werden."""

    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    failed_probes: list[str] = field(default_factory=list)

    def add(self, title: str, lines: list[str]) -> None:
        self.sections.append((title, lines))

    def to_markdown(self) -> str:
        parts = ["# Spike: Datenquellen\n"]
        for title, lines in self.sections:
            parts.append(f"## {title}\n")
            parts.extend(lines)
            parts.append("")
        return "\n".join(parts) + "\n"


def _describe_keys(data: dict[str, Any], prefix: str = "") -> list[str]:
    """Listet verschachtelte Schlüssel flach auf (z. B. ``pricing.cardmarket.avg``)."""
    keys: list[str] = []
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            keys.extend(_describe_keys(value, prefix=f"{path}."))
        else:
            keys.append(path)
    return keys


async def probe_tcgdex(client: httpx.AsyncClient, report: SpikeReport) -> None:
    """Sprachabdeckung und Felder von TCGdex ermitteln."""
    coverage: list[str] = ["| Sprache | Sets | Beispielkarte vorhanden |", "|---|---|---|"]
    sample: dict[str, Any] | None = None
    for lang in TCGDEX_LANGUAGES:
        sets_resp = await client.get(f"{TCGDEX_BASE}/{lang}/sets")
        set_count = (
            len(sets_resp.json()) if sets_resp.is_success else f"HTTP {sets_resp.status_code}"
        )
        card_resp = await client.get(f"{TCGDEX_BASE}/{lang}/cards/{SAMPLE_CARD_ID}")
        coverage.append(f"| {lang} | {set_count} | {'ja' if card_resp.is_success else 'nein'} |")
        if lang == "de" and card_resp.is_success:
            sample = card_resp.json()
    report.add("TCGdex – Sprachabdeckung", coverage)

    if sample is None:
        report.add("TCGdex – Beispielkarte (de)", ["Nicht abrufbar."])
        return
    pricing = sample.get("pricing", {})
    report.add(
        "TCGdex – Beispielkarte (de)",
        [
            f"Name: **{sample.get('name')}**, Set: {sample.get('set', {}).get('name')}, "
            f"Nummer: {sample.get('localId')}",
            f"Bild-Basis-URL: `{sample.get('image')}`",
            "",
            "Felder:",
            "",
            *[f"- `{key}`" for key in _describe_keys(sample)],
            "",
            "Preisblock (Rohdaten):",
            "",
            "```json",
            json.dumps(pricing, indent=2, ensure_ascii=False),
            "```",
        ],
    )


async def probe_tcgdex_asian(client: httpx.AsyncClient, report: SpikeReport) -> None:
    """Haben JP/KO/ZH-Karten Preise und Bilder? Stichprobe: je Sprache die ersten Karten
    der zuletzt gelisteten Sets (asiatische Sets haben eigene IDs, z. B. ``S12``)."""
    rows = [
        "| Sprache | Set | Karte | Bild | Cardmarket-Preis | TCGplayer-Preis |",
        "|---|---|---|---|---|---|",
    ]
    for lang in ASIAN_LANGUAGES:
        sets_resp = await client.get(f"{TCGDEX_BASE}/{lang}/sets")
        if not sets_resp.is_success:
            rows.append(f"| {lang} | HTTP {sets_resp.status_code} | – | – | – | – |")
            continue
        for set_brief in sets_resp.json()[-ASIAN_SETS_PER_LANGUAGE:]:
            set_resp = await client.get(f"{TCGDEX_BASE}/{lang}/sets/{set_brief['id']}")
            cards = set_resp.json().get("cards", []) if set_resp.is_success else []
            for card_brief in cards[:ASIAN_CARDS_PER_SET]:
                card_resp = await client.get(f"{TCGDEX_BASE}/{lang}/cards/{card_brief['id']}")
                card = card_resp.json() if card_resp.is_success else {}
                pricing = card.get("pricing") or {}
                rows.append(
                    f"| {lang} | {set_brief['id']} ({set_brief.get('name', '')}) "
                    f"| {card.get('name', '–')} · {card.get('localId', '–')} "
                    f"| {'ja' if card.get('image') else 'nein'} "
                    f"| {_price_summary(pricing.get('cardmarket'))} "
                    f"| {_price_summary(pricing.get('tcgplayer'))} |"
                )
    report.add("TCGdex – asiatische Karten: Preise und Bilder (Stichprobe)", rows)


def _price_summary(block: dict[str, Any] | None) -> str:
    """Kurzfassung eines Preisblocks, z. B. ``trend 12.5 EUR``."""
    if not block:
        return "nein"
    for key in ("trend", "avg", "low"):
        if block.get(key) not in (None, 0):
            return f"{key} {block[key]} {block.get('unit', '')}".strip()
    return "leer"


async def probe_images(client: httpx.AsyncClient, report: SpikeReport) -> None:
    """Sind Katalogbilder abrufbar, und wie groß sind sie?"""
    rows = ["| Variante | HTTP | Größe | Typ |", "|---|---|---|---|"]
    for variant in ("low.webp", "high.webp", "high.png"):
        resp = await client.get(f"{SAMPLE_IMAGE_BASE}/{variant}")
        rows.append(
            f"| `{variant}` | {resp.status_code} | {len(resp.content) / 1024:.0f} KB "
            f"| {resp.headers.get('content-type', '-')} |"
        )
    report.add(f"TCGdex – Bildabruf (`{SAMPLE_IMAGE_BASE}`)", rows)


async def probe_pokemontcg(client: httpx.AsyncClient, report: SpikeReport) -> None:
    """Felder und Cardmarket-Preise von pokemontcg.io ermitteln."""
    resp = await client.get(f"{POKEMONTCG_BASE}/cards/{SAMPLE_CARD_ID}")
    if not resp.is_success:
        report.add("pokemontcg.io", [f"HTTP {resp.status_code}"])
        return
    card = resp.json()["data"]
    report.add(
        "pokemontcg.io – Beispielkarte (en)",
        [
            f"Name: **{card.get('name')}**, Set: {card.get('set', {}).get('name')}",
            f"Rate-Limit-Header: `{resp.headers.get('x-ratelimit-limit', 'keiner')}`",
            "",
            "Cardmarket-Block:",
            "",
            "```json",
            json.dumps(card.get("cardmarket", {}), indent=2, ensure_ascii=False),
            "```",
        ],
    )


async def probe_cardmarket(client: httpx.AsyncClient, report: SpikeReport) -> None:
    """Eine einzelne Anfrage: Ist Cardmarket ohne Umgehung abrufbar?"""
    resp = await client.get(CARDMARKET_PROBE_URL)
    body = resp.text[:20_000]
    walls = [marker for marker in BOT_WALL_MARKERS if marker.lower() in body.lower()]
    report.add(
        "Cardmarket – Erreichbarkeit (1 Anfrage)",
        [
            f"URL: `{CARDMARKET_PROBE_URL}`",
            f"HTTP-Status: {resp.status_code}",
            f"Server-Header: `{resp.headers.get('server', '-')}`",
            f"Hinweise auf Bot-Sperre: {', '.join(walls) if walls else 'keine gefunden'}",
        ],
    )


async def run() -> SpikeReport:
    """Führt alle Prüfungen nacheinander aus; ein Fehler bricht die übrigen nicht ab."""
    report = SpikeReport()
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        for probe in (
            probe_tcgdex,
            probe_tcgdex_asian,
            probe_images,
            probe_pokemontcg,
            probe_cardmarket,
        ):
            try:
                await probe(client, report)
            except httpx.HTTPError as exc:
                report.failed_probes.append(probe.__name__)
                report.add(probe.__name__, [f"Fehler: `{exc!r}`"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("../docs/spikes/datenquellen.md"))
    args = parser.parse_args()
    out_path: Path = args.out

    report = asyncio.run(run())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    print(f"Bericht geschrieben: {out_path}")
    if report.failed_probes:
        print(f"Fehlgeschlagene Prüfungen: {', '.join(report.failed_probes)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
