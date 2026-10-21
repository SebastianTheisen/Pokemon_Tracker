"""Quellen-Messung: Was gibt es laut verlässlicher Quelle – und was davon haben wir?

Je Sprache eine Zielzahl aus der verlässlichsten Quelle, verglichen mit unserem Katalog:

* Englisch: pokemontcg.io-Datensatz (GitHub, vollständige englische Sets mit Kartenzahl).
* Deutsch: englische Sets (TCGdex) ohne oder mit weniger deutschen Karten.
* Japanisch: offizielle Datenbank pokemon-card.com – alle Seiten der Kartensuche, Set-Code
  aus dem Bildpfad (dauert ~10–15 Minuten, 1 Anfrage pro Sekunde).
* Taiwan, Hongkong, Indonesien, Thailand: asia.pokemon-card.com – Gesamtzahl je Region.
* Korea, Festland-China: offizielle Seiten – gibt es eine Kartensuche, und wie ist sie
  aufgebaut? (Erkundung für den späteren Import.)

Nur lesend, kostenlos. ``JP_MAX_PAGES`` begrenzt die japanischen Seiten (Test).

    docker compose exec -T api python - < deploy/spikes/quellen.py
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import unicodedata
from collections import Counter
from html import unescape
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

UA = "Kartenkiste/0.1 (private Sammel-App, Quellen-Messung, 1 Anfrage/s)"
PTCG_SETS = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/sets/en.json"
JP_BASE = "https://www.pokemon-card.com"
ASIA_BASE = "https://asia.pokemon-card.com"
LIST_LIMIT = 40

OurSets = dict[str, dict[str, Any]]  # Sprache → {Set-ID klein: {name, cards, release}}


def emit(line: str = "") -> None:
    print(line, flush=True)


def key(name: str) -> str:
    """Vergleichsform eines Set-Namens (ohne Akzente, Satzzeichen, Groß/klein)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response | None:
    time.sleep(1)
    try:
        return client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        emit(f"- ❌ `{url}` → {type(exc).__name__}: {exc}")
        return None


def table(headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        emit("- keine\n")
        return
    emit("| " + " | ".join(headers) + " |")
    emit("|" + "---|" * len(headers))
    for row in rows:
        emit("| " + " | ".join("–" if v is None else str(v) for v in row) + " |")
    emit()


async def our_sets() -> OurSets:
    """Unsere Sets je Sprache mit Kartenzahl (ohne Pocket)."""
    engine = create_engine(get_settings().database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT s.language, s.external_id, s.name, s.release_date,
                           COALESCE(s.card_count_total, s.card_count_official) AS announced,
                           (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id) AS cards
                    FROM card_sets s
                    WHERE s.series_name IS NULL OR s.series_name NOT ILIKE '%pocket%'
                    """
                )
            )
        ).all()
    await engine.dispose()
    result: OurSets = {}
    for row in rows:
        result.setdefault(row.language, {})[row.external_id.casefold()] = {
            "id": row.external_id,
            "name": row.name,
            "release": row.release_date,
            "announced": row.announced,
            "cards": row.cards,
        }
    return result


def overview(ours: OurSets) -> None:
    emit("## Unser Katalog (ohne Pocket)\n")
    table(
        ["Sprache", "Sets", "Karten"],
        [
            (language, len(sets), sum(s["cards"] for s in sets.values()))
            for language, sets in sorted(ours.items())
        ],
    )


def english(client: httpx.Client, ours: OurSets) -> None:
    emit("## Englisch – pokemontcg.io-Datensatz\n")
    response = get(client, PTCG_SETS)
    if response is None or response.status_code != httpx.codes.OK:
        emit(f"- ❌ HTTP {response.status_code if response else '–'}\n")
        return
    reference = response.json()
    by_name = {key(s["name"]): s for s in ours.get("en", {}).values()}
    total = sum(int(s.get("total") or 0) for s in reference)
    ours_total = sum(s["cards"] for s in ours.get("en", {}).values())
    emit(f"- Sets laut Quelle: {len(reference)}, Karten: {total} · bei uns: {ours_total}")
    missing, gaps = [], []
    for ref in reference:
        mine = ours.get("en", {}).get(str(ref["id"]).casefold()) or by_name.get(key(ref["name"]))
        expected = int(ref.get("total") or 0)
        if mine is None:
            missing.append((ref["id"], ref["name"], ref.get("releaseDate"), expected))
        elif mine["cards"] < expected:
            gaps.append((ref["id"], ref["name"], mine["id"], expected, mine["cards"]))
    emit(
        f"- Sets ohne Gegenstück bei uns (ID/Name): {len(missing)}, Sets mit Lücken: {len(gaps)}\n"
    )
    emit("### Fehlende Sets\n")
    table(["ID", "Name", "Erschienen", "Karten"], missing[:LIST_LIMIT])
    emit("### Sets mit Lücken\n")
    gaps.sort(key=lambda g: g[3] - g[4], reverse=True)
    table(["ID", "Name", "unsere ID", "laut Quelle", "bei uns"], gaps[:LIST_LIMIT])


def german(ours: OurSets) -> None:
    emit("## Deutsch – gegenüber den englischen Sets\n")
    en, de = ours.get("en", {}), ours.get("de", {})
    missing = [
        (s["id"], s["name"], s["release"], s["cards"])
        for set_id, s in en.items()
        if set_id not in de and s["cards"]
    ]
    gaps = [
        (s["id"], de[set_id]["name"], s["cards"], de[set_id]["cards"])
        for set_id, s in en.items()
        if set_id in de and de[set_id]["cards"] < s["cards"]
    ]
    emit(
        f"- Englische Sets ohne deutsches Set: {len(missing)} "
        f"({sum(m[3] for m in missing)} Karten), deutsche Sets mit weniger Karten: {len(gaps)} "
        f"({sum(g[2] - g[3] for g in gaps)} Karten)\n"
    )
    emit("### Englische Sets ohne deutsches Set (neueste zuerst)\n")
    missing.sort(key=lambda m: str(m[2] or ""), reverse=True)
    table(["ID", "Name (EN)", "Erschienen", "Karten EN"], missing[:LIST_LIMIT])
    emit("### Deutsche Sets mit Lücken\n")
    gaps.sort(key=lambda g: g[2] - g[3], reverse=True)
    table(["ID", "Name (DE)", "Karten EN", "Karten DE"], gaps[:LIST_LIMIT])


def japanese(client: httpx.Client, ours: OurSets) -> None:
    emit("## Japanisch – pokemon-card.com (offiziell)\n")
    api = f"{JP_BASE}/card-search/resultAPI.php"
    limit = int(os.environ.get("JP_MAX_PAGES", "0"))
    counts: Counter[str] = Counter()
    page, max_page, hits = 1, 1, None
    started = time.monotonic()
    while page <= max_page and (not limit or page <= limit):
        response = get(client, api, params={"regulation_sidebar_form": "all", "page": page})
        if response is None:
            break
        try:
            data = response.json()
        except ValueError:
            emit(f"- ❌ Seite {page}: kein JSON (HTTP {response.status_code})")
            break
        hits = data.get("hitCnt", hits)
        max_page = int(data.get("maxPage") or max_page)
        for card in data.get("cardList") or []:
            match = re.search(r"/card_images/[^/]+/([^/]+)/", str(card.get("cardThumbFile")))
            counts[match.group(1) if match else "?"] += 1
        page += 1
    emit(
        f"- Karten laut Quelle: {hits}, gelesen: {sum(counts.values())} "
        f"({page - 1} von {max_page} Seiten, {time.monotonic() - started:.0f} s), "
        f"Set-Codes: {len(counts)}"
    )
    mine = ours.get("ja", {})
    ours_total = sum(s["cards"] for s in mine.values())
    emit(f"- Bei uns: {len(mine)} Sets, {ours_total} Karten\n")
    missing = [(code, count) for code, count in counts.most_common() if code.casefold() not in mine]
    gaps = [
        (code, mine[code.casefold()]["name"], count, mine[code.casefold()]["cards"])
        for code, count in counts.items()
        if code.casefold() in mine and mine[code.casefold()]["cards"] < count
    ]
    emit(
        f"- Set-Codes ohne Set bei uns: {len(missing)} ({sum(c for _, c in missing)} Karten), "
        f"Sets mit Lücken: {len(gaps)} ({sum(g[2] - g[3] for g in gaps)} Karten)\n"
    )
    emit("### Set-Codes ohne Set bei uns\n")
    table(["Set-Code", "Karten"], missing[:LIST_LIMIT])
    emit("### Sets mit Lücken\n")
    gaps.sort(key=lambda g: g[2] - g[3], reverse=True)
    table(["Set-Code", "Name", "laut Quelle", "bei uns"], gaps[:LIST_LIMIT])


def asia(client: httpx.Client, ours: OurSets) -> None:
    emit("## Asien – asia.pokemon-card.com (offiziell)\n")
    rows = []
    for region, language in (("tw", "zh-tw"), ("hk", "zh-hk"), ("id", "id"), ("th", "th")):
        response = get(client, f"{ASIA_BASE}/{region}/card-search/list/", params={"pageNo": 1})
        total = None
        if response is not None and response.status_code == httpx.codes.OK:
            match = re.search(r'class="resultNumber"[^>]*>(.*?)<', response.text, re.S)
            total = re.sub(r"\D", "", match.group(1)) if match else "?"
        status = response.status_code if response is not None else "–"
        mine = ours.get(language, {})
        rows.append(
            (region, status, total, len(mine), sum(s["cards"] for s in mine.values()) or None)
        )
    table(["Region", "HTTP", "Karten laut Quelle", "Sets bei uns", "Karten bei uns"], rows)


def explore(client: httpx.Client, title: str, urls: list[str]) -> None:
    """Seiten abrufen: Status, Titel, Links/Skripte rund um Karten und Schnittstellen."""
    emit(f"## {title} – Erkundung\n")
    for url in urls:
        response = get(client, url)
        if response is None:
            continue
        page_title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.S | re.I)
        emit(
            f"- `{url}` → HTTP {response.status_code}, "
            f"{response.headers.get('content-type', '').split(';')[0]}, {len(response.content)} B, "
            f"Titel: {unescape(page_title.group(1)).strip()[:80] if page_title else '–'}"
        )
        hints = sorted(
            {
                m
                for m in re.findall(
                    r"""(?:href|src|action|url)\s*[=:]\s*["']([^"']+)["']""", response.text
                )
                if re.search(r"card|ajax|api|search|json|\.php", m, re.I)
            }
        )
        for hint in hints[:25]:
            emit(f"  - `{hint[:160]}`")
    emit()


def main() -> None:
    emit("# Quellen-Messung: Zielzahlen je Sprache\n")
    ours = asyncio.run(our_sets())
    overview(ours)
    german(ours)
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as client:
        for section in (english, asia, japanese):
            try:
                section(client, ours)
            except Exception as exc:  # Messung: Fehler berichten, weitermachen
                emit(f"- ❌ Abbruch: {type(exc).__name__}: {exc}\n")
        explore(
            client,
            "Korea – pokemoncard.co.kr",
            [
                "https://pokemoncard.co.kr/cards",
                "https://pokemoncard.co.kr/cards/detail/BS2022017046",
                "https://new.pokemonkorea.co.kr/card",
            ],
        )
        explore(
            client,
            "Festland-China – pokemon.cn",
            ["https://www.pokemon.cn/tcg-home", "https://www.pokemon.cn/"],
        )


main()
