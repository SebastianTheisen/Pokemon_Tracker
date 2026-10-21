"""Erkundung 2: Aufbau der Quellen für die Importe (Deutsch, Japan, Taiwan).

* PokéWiki (pokewiki.de, MediaWiki-API): deutsche Setlisten inkl. Promos – Suche nach
  Set-Seiten, Wikitext-Ausschnitt (Tabellen-/Vorlagenaufbau), Bildinfo.
* pokemon.com/de: offizielle Kartendatenbank – Detailseite einer deutschen Promo.
* pokemon-card.com (Japan): verträgliches Tempo (3 s, Wiederholung bei 503), Aufbau der
  Detailseite (Name, Nummer, Set, Bild).
* asia.pokemon-card.com/tw: Gesamtzahl (Seitenaufbau), Detailseite mit Set-Angabe.

Nur lesend, kostenlos, ~3 Minuten.

    docker compose exec -T api python - < deploy/spikes/quellen2.py
"""

from __future__ import annotations

import json
import re
import time
from html import unescape
from typing import Any

import httpx

UA = "Kartenkiste/0.1 (private Sammel-App, Quellen-Erkundung, langsam)"
WIKI_API = "https://www.pokewiki.de/api.php"
PAUSE = 3.0


def emit(line: str = "") -> None:
    print(line, flush=True)


def snippet(text: str, limit: int = 1500) -> str:
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[:limit] + " …"


def get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response | None:
    """Abruf mit Pause; bei 429/503 bis zu zweimal länger warten und wiederholen."""
    for attempt in range(3):
        time.sleep(PAUSE * (attempt * 3 + 1))
        try:
            response = client.get(url, **kwargs)
        except httpx.HTTPError as exc:
            emit(f"- ❌ `{url}` → {type(exc).__name__}: {exc}")
            return None
        if response.status_code not in (429, 503):
            return response
        emit(f"- ⏳ `{url}` → HTTP {response.status_code}, Versuch {attempt + 1}")
    return response


def around(text: str, pattern: str, width: int = 400) -> list[str]:
    """Textausschnitte rund um ein Muster (für unbekannten Seitenaufbau)."""
    found = []
    for match in list(re.finditer(pattern, text, re.I))[:3]:
        start = max(match.start() - width // 2, 0)
        found.append(snippet(text[start : match.end() + width // 2], width + 100))
    return found


def wiki(client: httpx.Client) -> None:
    emit("## PokéWiki (MediaWiki-API)\n")
    info = get(client, WIKI_API, params={"action": "query", "meta": "siteinfo", "format": "json"})
    if info is None:
        return
    emit(f"- API: HTTP {info.status_code}, {info.headers.get('content-type')}")
    if info.status_code != httpx.codes.OK:
        emit(f"  - `{snippet(info.text, 300)}`\n")
        return
    titles: list[str] = []
    for term in ("Black Star Promos", "McDonald's Kollektion", "Trainer-Kit", "Drachengruft"):
        result = get(
            client,
            WIKI_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{term} (TCG)",
                "srlimit": 8,
                "format": "json",
            },
        )
        hits = [] if result is None else (result.json().get("query") or {}).get("search") or []
        names = [hit["title"] for hit in hits]
        emit(f"- Suche „{term}“: {names}")
        titles.extend(name for name in names[:1] if name not in titles)
    emit()
    for title in titles[:3]:
        page = get(
            client,
            WIKI_API,
            params={"action": "parse", "page": title, "prop": "wikitext", "format": "json"},
        )
        if page is None:
            continue
        text = ((page.json().get("parse") or {}).get("wikitext") or {}).get("*", "")
        templates = sorted(set(re.findall(r"\{\{\s*([^|}\n]+)", text)))[:25]
        rows = [line for line in text.splitlines() if re.search(r"\|\s*\d{1,3}\s*[|}]", line)]
        emit(f"### {title}\n")
        emit(f"- Wikitext: {len(text)} Zeichen, Vorlagen: {templates}")
        emit(f"- Beispielzeilen mit Nummern ({len(rows)}):")
        for row in rows[:8]:
            emit(f"  - `{row[:200]}`")
        files = re.findall(r"(?:Datei|File):([^|\]\n]+\.(?:png|jpg|jpeg|webp))", text, re.I)
        emit(f"- Bilder im Text: {len(files)}, z. B. {files[:3]}")
        emit(f"- Anfang: `{snippet(text, 1200)}`\n")
        if files:
            image = get(
                client,
                WIKI_API,
                params={
                    "action": "query",
                    "titles": f"Datei:{files[0]}",
                    "prop": "imageinfo",
                    "iiprop": "url|size",
                    "format": "json",
                },
            )
            if image is not None:
                emit(
                    f"- Bildinfo: `{snippet(json.dumps(image.json(), ensure_ascii=False), 500)}`\n"
                )


GERMAN_CHECK = [
    "Base Set 2 (TCG)",
    "Legendary Collection (TCG)",
    "Southern Islands (TCG)",
    "Pokémon Rumble (TCG)",
    "Poké Card Creator Pack (TCG)",
    "Best of Game (TCG)",
    "Double Crisis (TCG)",
    "Legendary Treasures (TCG)",
    "Gym Heroes (TCG)",
    "Drachengruft (TCG)",
    "XY Black Star Promos (TCG)",
    "McDonald's Kollektion 2015 (TCG)",
]


def wiki_release(client: httpx.Client) -> None:
    """Infobox je Set: Steht drin, ob/wann es auf Deutsch erschienen ist?"""
    emit("## PokéWiki – deutsche Veröffentlichung je Set (Infobox)\n")
    for title in GERMAN_CHECK:
        page = get(
            client,
            WIKI_API,
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            },
        )
        if page is None:
            continue
        text = (page.json().get("parse") or {}).get("wikitext") or ""
        infobox = re.search(r"\{\{\s*Infobox[^\n]*(?:\n\s*\|[^\n]*)*", text)
        fields = (
            re.findall(r"\|\s*([^=|\n]+?)\s*=\s*([^|\n]*)", infobox.group(0)) if infobox else []
        )
        release = [
            f"{key}={value.strip()[:40]}"
            for key, value in fields
            if re.search(
                r"datum|erschien|deutsch|release|ver(ö|oe)ffentlich|land|sprache", key, re.I
            )
        ]
        hints = around(
            text, r"nicht auf Deutsch|nur auf Englisch|nicht in Deutschland|nie auf Deutsch", 160
        )
        emit(f"- **{title}**: Felder {release or [k for k, _ in fields][:12]}")
        for hint in hints[:2]:
            emit(f"  - Hinweis: `{hint}`")
    emit()


def pokemon_de(client: httpx.Client) -> None:
    emit("## pokemon.com/de – offizielle Kartendatenbank\n")
    base = "https://www.pokemon.com"
    robots = get(client, f"{base}/robots.txt")
    if robots is not None:
        rules = [
            line
            for line in robots.text.splitlines()
            if "karten" in line.lower() or "cards" in line.lower()
        ]
        emit(f"- robots.txt HTTP {robots.status_code}, Regeln zu Karten: {rules[:6]}")
    for path in (
        "/de/pokemon-sammelkartenspiel/pokemon-karten/series/xyp/xy1/",
        "/de/pokemon-sammelkartenspiel/pokemon-karten/series/bwp/bw1/",
        "/de/pokemon-sammelkartenspiel/pokemon-karten/?cardName=&set=xyp",
    ):
        response = get(client, base + path)
        if response is None:
            continue
        title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.S | re.I)
        images = sorted(set(re.findall(r'src="([^"]+/cards/[^"]+)"', response.text)))[:3]
        emit(
            f"- `{path}` → HTTP {response.status_code}, Titel: "
            f"{unescape(title.group(1)).strip()[:90] if title else '–'}, Bilder: {images}"
        )
    emit()


def japan(client: httpx.Client) -> None:
    emit("## Japan – Tempo und Detailseite\n")
    base = "https://www.pokemon-card.com"
    started, ok, card_id = time.monotonic(), 0, None
    for page in range(1, 6):
        response = get(
            client,
            f"{base}/card-search/resultAPI.php",
            params={"regulation_sidebar_form": "all", "page": page},
        )
        if response is None or response.status_code != httpx.codes.OK:
            emit(f"- Seite {page}: HTTP {response.status_code if response else '–'}")
            break
        ok += 1
        cards = response.json().get("cardList") or []
        card_id = card_id or (cards[0].get("cardID") if cards else None)
    emit(f"- {ok} von 5 Seiten ok in {time.monotonic() - started:.0f} s (Pause {PAUSE} s)")
    if card_id:
        detail = get(client, f"{base}/card-search/details.php/card/{card_id}")
        if detail is not None:
            emit(f"- Detail {card_id}: HTTP {detail.status_code}")
            for pattern in (
                r"<h1",
                r"subtext",
                r"img-regulation",
                r"拡張パック|商品|収録",
                r'class="fit"',
            ):
                for part in around(detail.text, pattern):
                    emit(f"  - `{pattern}`: `{part}`")
    emit()


def taiwan(client: httpx.Client) -> None:
    emit("## Taiwan – Zählung und Detailseite\n")
    base = "https://asia.pokemon-card.com"
    listing = get(client, f"{base}/tw/card-search/list/", params={"pageNo": 1})
    if listing is None:
        return
    emit(f"- Liste HTTP {listing.status_code}")
    for pattern in (r"resultNumber", r"張|件", r"pageNo="):
        for part in around(listing.text, pattern, 300):
            emit(f"  - `{pattern}`: `{part}`")
    ids = re.findall(r"/tw/card-search/detail/(\d+)/", listing.text)
    emit(f"- Karten-Links auf Seite 1: {len(set(ids))}")
    if not ids:
        scripts = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', listing.text)))[:10]
        emit(f"- Skripte (Liste per JavaScript geladen?): {scripts}")
        emit(f"- Seitenanfang: `{snippet(listing.text, 2500)}`")
    if ids:
        detail = get(client, f"{base}/tw/card-search/detail/{ids[0]}/")
        if detail is not None:
            emit(f"- Detail {ids[0]}: HTTP {detail.status_code}")
            for pattern in (
                r"collectorNumber",
                r"expansion|系列|擴充|商品",
                r"cardImage",
                r"pageHeader",
            ):
                for part in around(detail.text, pattern):
                    emit(f"  - `{pattern}`: `{part}`")
    emit()


def main() -> None:
    emit("# Erkundung 2: Aufbau der Quellen für die Importe\n")
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        for section in (wiki_release, wiki, pokemon_de, japan, taiwan):
            try:
                section(client)
            except Exception as exc:  # Erkundung: Fehler berichten, weitermachen
                emit(f"- ❌ Abbruch: {type(exc).__name__}: {exc}\n")


main()
