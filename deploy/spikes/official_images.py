"""Spike: Bildquellen für fehlende Kartenbilder – alle Sprachen.

* DE/EN: TCGdex-Bild trotzdem vorhanden? Offizielle Bilder von pokemon.com, pokemontcg.io.
* JP/KO/TW: offizielle Kartendatenbanken.

Läuft im API-Container (dort ist httpx installiert) und gibt einen Markdown-Bericht aus.
Prüft je Quelle: Suche/Liste, Detailseite, Bild-URL, ob das Bild auch mit fremdem
„Referer“ ausgeliefert wird (Einbinden in unsere App) und robots.txt. Sanft: 1 s Pause.

    docker compose exec -T api python - < deploy/spikes/official_images.py
"""

from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from typing import Any

import httpx

UA = "Kartenkiste/0.1 (private Sammel-App, Test der Bildquellen, 1 Anfrage/s)"
FOREIGN_REFERER = "https://kartenkiste.example.ts.net/"
lines: list[str] = ["# Spike: offizielle Kartendatenbanken als Bildquelle\n"]


def out(text: str = "") -> None:
    lines.append(text)


def get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response | None:
    time.sleep(1)
    try:
        return client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        out(f"- ❌ `{url}` → {type(exc).__name__}: {exc}")
        return None


def check_image(client: httpx.Client, url: str) -> None:
    """Bild ohne Referer, mit fremdem Referer und mit Origin laden."""
    for label, headers in (
        ("ohne Referer", {}),
        ("fremder Referer", {"Referer": FOREIGN_REFERER}),
        ("fremder Origin", {"Origin": FOREIGN_REFERER.rstrip("/")}),
    ):
        response = get(client, url, headers=headers)
        if response is not None:
            out(
                f"  - Bild {label}: HTTP {response.status_code}, "
                f"{response.headers.get('content-type')}, {len(response.content)} Bytes, "
                f"CORS: {response.headers.get('access-control-allow-origin') or '–'}"
            )


def robots(client: httpx.Client, base: str) -> None:
    response = get(client, f"{base}/robots.txt")
    if response is not None and response.status_code == 200:
        relevant = [
            line for line in response.text.splitlines()
            if line.lower().startswith(("disallow", "user-agent", "crawl-delay"))
        ][:12]
        out(f"- robots.txt: `{' | '.join(relevant) or 'leer'}`")
    else:
        out(f"- robots.txt: {response.status_code if response else 'nicht erreichbar'}")


def japan(client: httpx.Client) -> None:
    out("## Japan – pokemon-card.com\n")
    base = "https://www.pokemon-card.com"
    robots(client, base)
    api = f"{base}/card-search/resultAPI.php"
    for keyword in ("", "ピカチュウex", "ルギア", "コイキング"):
        response = get(client, api, params={"keyword": keyword, "regulation_sidebar_form": "all", "page": 1})
        if response is None:
            continue
        try:
            data = response.json()
        except ValueError:
            out(f"- Suche `{keyword or '(alle)'}`: HTTP {response.status_code}, kein JSON: {response.text[:120]!r}")
            continue
        cards = data.get("cardList") or []
        out(
            f"- Suche `{keyword or '(alle)'}`: HTTP {response.status_code}, Treffer {data.get('hitCnt')}, "
            f"Seiten {data.get('maxPage')}, Felder: {sorted(cards[0]) if cards else '–'}"
        )
        if keyword == "ピカチュウex" and cards:
            out(f"  - Beispiel: `{ {k: cards[0][k] for k in list(cards[0])[:6]} }`")
            card_id = cards[0].get("cardID")
            detail = get(client, f"{base}/card-search/details.php/card/{card_id}")
            if detail is not None:
                html = detail.text
                name = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
                image = re.search(r'<img[^>]*class="fit"[^>]*src="([^"]+)"', html) or re.search(
                    r'src="([^"]+)"[^>]*class="fit"', html
                )
                number = re.search(r'class="subtext[^"]*"[^>]*>(.*?)</div>', html, re.S)
                regulation = re.search(r'class="img-regulation"[^>]*alt="([^"]*)"', html)
                out(f"  - Detail HTTP {detail.status_code}: Name {unescape(name.group(1)).strip() if name else '?'}, "
                    f"Nummer {re.sub(r'<[^>]+>|\\s+', ' ', number.group(1)).strip() if number else '?'}, "
                    f"Regulierung/Set {regulation.group(1) if regulation else '?'}")
                if image:
                    url = base + image.group(1) if image.group(1).startswith("/") else image.group(1)
                    out(f"  - Bild-URL: `{url}`")
                    check_image(client, url)


def korea(client: httpx.Client) -> None:
    out("\n## Korea – pokemoncard.co.kr\n")
    base = "https://pokemoncard.co.kr"
    robots(client, base)
    time.sleep(1)
    try:
        response = client.post(
            f"{base}/v2/ajax2_dev2",
            data={"action": "search_text_cards", "search_text": "피카츄", "search_params": "", "limit": 0},
            headers={"Referer": f"{base}/cards"},
        )
    except httpx.HTTPError as exc:
        out(f"- ❌ Suche: {exc}")
        return
    try:
        data = response.json()
    except ValueError:
        out(f"- Suche: HTTP {response.status_code}, kein JSON: {response.text[:160]!r}")
        return
    result = data.get("result") if isinstance(data, dict) else None
    sample = result[0] if isinstance(result, list) and result else result
    out(f"- Suche `피카츄`: HTTP {response.status_code}, Typ {type(result).__name__}, "
        f"Anzahl {len(result) if isinstance(result, list) else '?'}, Beispiel: `{str(sample)[:200]}`")
    card_num = None
    if isinstance(sample, dict):
        card_num = sample.get("CardNum") or sample.get("cardnum")
    if card_num:
        detail = get(client, f"{base}/cards/detail/{card_num}")
        if detail is not None:
            image = re.search(r'<img[^>]*class="[^"]*feature_image[^"]*"[^>]*src="([^"]+)"', detail.text) or re.search(
                r'src="([^"]+)"[^>]*class="[^"]*feature_image', detail.text
            )
            out(f"  - Detail HTTP {detail.status_code}, Bild: `{image.group(1) if image else '?'}`")
            if image:
                check_image(client, image.group(1).split("?")[0])


def taiwan(client: httpx.Client) -> None:
    out("\n## Taiwan (traditionelles Chinesisch) – asia.pokemon-card.com/tw\n")
    base = "https://asia.pokemon-card.com"
    robots(client, base)
    listing = get(client, f"{base}/tw/card-search/list/", params={"pageNo": 1})
    if listing is None:
        return
    ids = re.findall(r"/tw/card-search/detail/(\d+)/", listing.text)
    total = re.search(r'class="resultNumber"[^>]*>(.*?)<', listing.text, re.S)
    out(f"- Liste HTTP {listing.status_code}: {len(set(ids))} Karten auf Seite 1, "
        f"Gesamt: {total.group(1).strip() if total else '?'}")
    if ids:
        detail = get(client, f"{base}/tw/card-search/detail/{ids[0]}/")
        if detail is not None:
            name = re.search(r'<h1 class="pageHeader cardDetail"[^>]*>(.*?)</h1>', detail.text, re.S)
            image = re.search(r'class="cardImage".*?<img[^>]*src="([^"]+)"', detail.text, re.S)
            number = re.search(r'class="collectorNumber"[^>]*>(.*?)<', detail.text, re.S)
            out(f"  - Detail HTTP {detail.status_code}: {re.sub(r'<[^>]+>|\\s+', ' ', name.group(1)).strip() if name else '?'}, "
                f"Nummer {number.group(1).strip() if number else '?'}")
            if image:
                url = image.group(1) if image.group(1).startswith("http") else base + image.group(1)
                out(f"  - Bild-URL: `{url}`")
                check_image(client, url)


def status(client: httpx.Client, url: str) -> str:
    time.sleep(1)
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return f"Fehler ({type(exc).__name__})"
    kind = response.headers.get("content-type", "")
    return f"{response.status_code} {kind.split(';')[0]} {len(response.content)} B"


def western(client: httpx.Client) -> None:
    """Deutsch/Englisch: Lücken bei TCGdex und mögliche Ersatzquellen."""
    out("## Deutsch und Englisch\n")
    samples = json.loads(os.environ.get("SAMPLES", "[]"))
    out("### Karten ohne Bild in unserem Katalog (Stichprobe)\n")
    out("| Sprache | Karte | Set | TCGdex-Bild direkt | pokemontcg.io | pokemon.com |")
    out("|---|---|---|---|---|---|")
    for sample in samples[:16]:
        base = (sample.get("logo") or "").rsplit("/logo", 1)[0]
        tcgdex = status(client, f"{base}/{sample['number']}/high.webp") if base else "–"
        number = str(sample["number"]).lstrip("0") or "0"
        ptcg = status(client, f"https://images.pokemontcg.io/{sample['set']}/{number}_hires.png")
        lang = sample["language"].upper()
        code = sample["set"].upper()
        official = status(
            client,
            f"https://assets.pokemon.com/assets/cms2{'' if lang == 'EN' else '-de-de'}/img/cards/web/"
            f"{code}/{code}_{lang}_{number}.png",
        )
        out(f"| {sample['language']} | {sample['name']} {sample['number']} | {sample['set']} "
            f"| {tcgdex} | {ptcg} | {official} |")

    out("\n### Offizielle Bild-Adressen von pokemon.com (bekannte Karten)\n")
    for label, url in (
        ("Nachtara VMAX DE (alt)", "https://assets.pokemon.com/assets/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png"),
        ("Nachtara VMAX DE (neu)", "https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png"),
        ("Umbreon VMAX EN (alt)", "https://assets.pokemon.com/assets/cms2/img/cards/web/SWSH7/SWSH7_EN_215.png"),
        ("Umbreon VMAX EN (neu)", "https://assets.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SWSH7/SWSH7_EN_215.png"),
        ("SV08 162 DE", "https://assets.pokemon.com/static-assets/content-assets/cms2-de-de/img/cards/web/SV08/SV08_DE_162.png"),
        ("SV08 162 EN", "https://assets.pokemon.com/static-assets/content-assets/cms2/img/cards/web/SV08/SV08_EN_162.png"),
        ("Grundset Glurak EN", "https://assets.pokemon.com/assets/cms2/img/cards/web/BS/BS_EN_4.png"),
    ):
        out(f"- {label}: {status(client, url)} – `{url}`")
    out(f"- Kartendatenbank DE: {status(client, 'https://www.pokemon.com/de/pokemon-sammelkartenspiel/pokemon-karten/')}")
    out(f"- pokemontcg.io API (swsh7 215): {status(client, 'https://api.pokemontcg.io/v2/cards/swsh7-215')}")
    out(f"- pokemontcg.io Bild (swsh7 215): {status(client, 'https://images.pokemontcg.io/swsh7/215_hires.png')}\n")


def main() -> None:
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        for source in (western, japan, korea, taiwan):
            try:
                source(client)
            except Exception as exc:  # Spike: Fehler nur berichten
                out(f"- ❌ Abbruch: {type(exc).__name__}: {exc}")
    print("\n".join(lines))


main()
