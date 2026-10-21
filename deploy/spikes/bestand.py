"""Bestandsaufnahme: Wo sind die Daten von Kartenkiste lückenhaft? (nur lesend, kostenlos)

Zahlen direkt aus der Datenbank, je Sprache:

1. Karten: vorhanden gegenüber der Set-Größe laut Quelle, ohne Bild, ohne Cardmarket-Ausgabe,
   ohne Preis.
2. Sets mit den größten Lücken und Sets ohne Cardmarket-Ausgabe.
3. Cardmarket-Einzelkarten, die zu keiner unserer Karten gehören (Karten, die uns fehlen),
   gruppiert nach Cardmarket-Ausgabe.
4. Versiegeltes: Katalog, Preise, Bilder, angelegte Produkte.
5. Scanner: Treffer, Unsicherheit, vom Nutzer korrigierte Erkennungen (falsche Karte,
   falsche Sprache), die neuesten Korrekturen als Beispiele.

    docker compose exec -T api python - < deploy/spikes/bestand.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory

SINGLE_CATEGORY = 51


def emit(line: str = "") -> None:
    print(line, flush=True)


def pct(part: int | None, total: int | None) -> str:
    return f"{(part or 0) * 100 // total} %" if total else "–"


def table(headers: list[str], rows: list[Any]) -> None:
    emit("| " + " | ".join(headers) + " |")
    emit("|" + "---|" * len(headers))
    for row in rows:
        emit("| " + " | ".join("–" if v is None else str(v) for v in row) + " |")
    emit()


QUERIES: dict[str, str] = {
    "cards": """
        SELECT s.language,
               COUNT(DISTINCT s.id) AS sets,
               COUNT(c.id) AS cards,
               COUNT(c.id) FILTER (WHERE c.image_url IS NULL) AS no_image,
               COUNT(c.id) FILTER (WHERE s.cardmarket_expansion_id IS NULL
                                     AND c.cardmarket_product_id IS NULL
                                     AND c.cardmarket_product_override IS NULL) AS no_cm,
               COUNT(c.id) FILTER (WHERE NOT EXISTS (
                   SELECT 1 FROM price_points p WHERE p.card_id = c.id)) AS no_price
        FROM card_sets s LEFT JOIN cards c ON c.set_id = s.id
        GROUP BY s.language ORDER BY cards DESC
    """,
    "expected": """
        SELECT s.language,
               SUM(GREATEST(COALESCE(s.card_count_total, s.card_count_official, 0)
                   - (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id), 0)) AS missing,
               COUNT(*) FILTER (WHERE s.card_count_total IS NULL
                                  AND s.card_count_official IS NULL) AS unknown_size
        FROM card_sets s GROUP BY s.language
    """,
    "gaps": """
        SELECT s.language, s.external_id, s.name, s.release_date,
               COALESCE(s.card_count_total, s.card_count_official) AS expected,
               (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id) AS present
        FROM card_sets s
        WHERE COALESCE(s.card_count_total, s.card_count_official, 0)
              > (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id)
        ORDER BY COALESCE(s.card_count_total, s.card_count_official, 0)
                 - (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id) DESC
        LIMIT 40
    """,
    "unlinked_sets": """
        SELECT s.language, s.external_id, s.name, s.release_date,
               (SELECT COUNT(*) FROM cards c WHERE c.set_id = s.id) AS cards
        FROM card_sets s WHERE s.cardmarket_expansion_id IS NULL
        ORDER BY s.release_date DESC NULLS LAST LIMIT 40
    """,
    "unlinked_by_language": """
        SELECT language, COUNT(*) AS sets FROM card_sets
        WHERE cardmarket_expansion_id IS NULL GROUP BY language ORDER BY sets DESC
    """,
    "cm_missing": """
        WITH used AS (
            SELECT cardmarket_product_id AS id FROM cards
            WHERE cardmarket_product_id IS NOT NULL
            UNION SELECT cardmarket_product_override FROM cards
            WHERE cardmarket_product_override IS NOT NULL
        ), linked AS (
            SELECT DISTINCT cardmarket_expansion_id AS id FROM card_sets
            WHERE cardmarket_expansion_id IS NOT NULL
        )
        SELECT p.id_expansion,
               COUNT(*) AS singles,
               COUNT(*) FILTER (WHERE u.id IS NULL) AS without_card,
               (p.id_expansion IN (SELECT id FROM linked)) AS set_linked,
               MIN(p.date_added) AS first_added,
               (ARRAY_AGG(p.name ORDER BY p.id_product))[1:3] AS examples
        FROM cm_products p LEFT JOIN used u ON u.id = p.id_product
        WHERE p.id_category = :single
        GROUP BY p.id_expansion
        HAVING COUNT(*) FILTER (WHERE u.id IS NULL) > 0
        ORDER BY MIN(p.date_added) DESC NULLS LAST
        LIMIT 40
    """,
    "cm_totals": """
        WITH used AS (
            SELECT cardmarket_product_id AS id FROM cards
            WHERE cardmarket_product_id IS NOT NULL
        ), linked AS (
            SELECT DISTINCT cardmarket_expansion_id AS id FROM card_sets
            WHERE cardmarket_expansion_id IS NOT NULL
        )
        SELECT COUNT(*) AS singles,
               COUNT(*) FILTER (WHERE p.id_product IN (SELECT id FROM used)) AS with_card_id,
               COUNT(DISTINCT p.id_expansion) AS expansions,
               COUNT(DISTINCT p.id_expansion)
                   FILTER (WHERE p.id_expansion IN (SELECT id FROM linked)) AS linked
        FROM cm_products p WHERE p.id_category = :single
    """,
    "sealed": """
        SELECT COUNT(*) AS catalog,
               COUNT(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM cm_prices x WHERE x.id_product = p.id_product)) AS priced,
               COUNT(*) FILTER (WHERE p.image_url IS NOT NULL) AS with_image
        FROM cm_products p
        WHERE p.id_category IS NOT NULL AND p.id_category <> :single
    """,
    "own_products": """
        SELECT COUNT(*) AS products,
               COUNT(*) FILTER (WHERE cardmarket_product_id IS NOT NULL) AS linked,
               COUNT(*) FILTER (WHERE image_url IS NOT NULL) AS with_image
        FROM products
    """,
    "scans": """
        SELECT mode, COUNT(*) AS scans,
               COUNT(*) FILTER (WHERE best_card_id IS NULL) AS no_hit,
               COUNT(*) FILTER (WHERE NOT confident) AS unsure,
               COUNT(*) FILTER (WHERE confirmed_card_id IS NOT NULL) AS confirmed,
               COUNT(*) FILTER (WHERE confirmed_card_id IS NOT NULL
                                  AND confirmed_card_id IS DISTINCT FROM best_card_id) AS corrected,
               ROUND(AVG(duration_ms)) AS avg_ms
        FROM scan_log GROUP BY mode
    """,
    "corrections": """
        SELECT l.created_at::date AS day,
               b.language AS best_lang, bs.external_id AS best_set, b.number AS best_no,
               b.name AS best_name,
               c.language AS ok_lang, cs.external_id AS ok_set, c.number AS ok_no,
               c.name AS ok_name,
               ROUND(l.confidence::numeric, 2) AS conf
        FROM scan_log l
        JOIN cards c ON c.id = l.confirmed_card_id
        JOIN card_sets cs ON cs.id = c.set_id
        LEFT JOIN cards b ON b.id = l.best_card_id
        LEFT JOIN card_sets bs ON bs.id = b.set_id
        WHERE l.confirmed_card_id IS DISTINCT FROM l.best_card_id
        ORDER BY l.created_at DESC LIMIT 30
    """,
    "correction_kinds": """
        SELECT CASE
                 WHEN l.best_card_id IS NULL THEN 'kein Vorschlag'
                 WHEN b.language <> c.language AND b.set_id = c.set_id THEN 'nur Sprache'
                 WHEN b.language <> c.language THEN 'andere Sprache'
                 WHEN b.set_id <> c.set_id AND b.number_norm = c.number_norm
                   THEN 'gleiche Nummer, anderes Set'
                 WHEN b.set_id <> c.set_id THEN 'anderes Set'
                 ELSE 'gleiches Set, andere Karte'
               END AS kind,
               COUNT(*) AS count
        FROM scan_log l
        JOIN cards c ON c.id = l.confirmed_card_id
        LEFT JOIN cards b ON b.id = l.best_card_id
        WHERE l.confirmed_card_id IS DISTINCT FROM l.best_card_id
        GROUP BY 1 ORDER BY 2 DESC
    """,
}


async def main() -> None:
    emit("# Bestandsaufnahme Kartenkiste\n")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    params = {"single": SINGLE_CATEGORY}
    async with factory() as session:

        async def rows(name: str) -> list[Any]:
            return list((await session.execute(text(QUERIES[name]), params)).all())

        emit("## 1. Karten je Sprache\n")
        expected = {r.language: r for r in await rows("expected")}
        table(
            [
                "Sprache",
                "Sets",
                "Karten",
                "fehlen laut Set-Größe",
                "Sets ohne Größe",
                "ohne Bild",
                "ohne Cardmarket",
                "ohne Preis",
            ],
            [
                (
                    r.language,
                    r.sets,
                    r.cards,
                    expected[r.language].missing if r.language in expected else None,
                    expected[r.language].unknown_size if r.language in expected else None,
                    f"{r.no_image} ({pct(r.no_image, r.cards)})",
                    f"{r.no_cm} ({pct(r.no_cm, r.cards)})",
                    f"{r.no_price} ({pct(r.no_price, r.cards)})",
                )
                for r in await rows("cards")
            ],
        )

        emit("## 2a. Sets mit den größten Lücken (Karten fehlen)\n")
        table(
            ["Sprache", "Set", "Name", "Erschienen", "erwartet", "vorhanden"],
            [tuple(r) for r in await rows("gaps")],
        )
        emit("## 2b. Sets ohne Cardmarket-Ausgabe (→ keine Preise)\n")
        emit(
            "Je Sprache: "
            + ", ".join(f"{r.language}: {r.sets}" for r in await rows("unlinked_by_language"))
            + "\n"
        )
        table(
            ["Sprache", "Set", "Name", "Erschienen", "Karten"],
            [tuple(r) for r in await rows("unlinked_sets")],
        )

        emit("## 3. Cardmarket-Einzelkarten ohne passende Karte bei uns\n")
        totals = (await rows("cm_totals"))[0]
        emit(
            f"- Einzelkarten bei Cardmarket: {totals.singles}, davon über Produkt-ID mit einer "
            f"unserer Karten verknüpft: {totals.with_card_id} "
            f"({pct(totals.with_card_id, totals.singles)})"
        )
        emit(
            f"- Cardmarket-Ausgaben: {totals.expansions}, davon einem unserer Sets zugeordnet: "
            f"{totals.linked} ({pct(totals.linked, totals.expansions)})\n"
        )
        emit("Neueste Ausgaben mit Einzelkarten ohne Gegenstück (Beispielnamen):\n")
        table(
            ["Ausgabe", "Einzelkarten", "ohne Karte", "Set verknüpft", "seit", "Beispiele"],
            [
                (
                    r.id_expansion,
                    r.singles,
                    r.without_card,
                    "ja" if r.set_linked else "nein",
                    r.first_added,
                    "; ".join(r.examples or []),
                )
                for r in await rows("cm_missing")
            ],
        )

        emit("## 4. Versiegeltes\n")
        sealed = (await rows("sealed"))[0]
        own = (await rows("own_products"))[0]
        emit(
            f"- Cardmarket-Katalog: {sealed.catalog}, mit Preis {sealed.priced} "
            f"({pct(sealed.priced, sealed.catalog)}), mit Bild {sealed.with_image} "
            f"({pct(sealed.with_image, sealed.catalog)})"
        )
        emit(
            f"- Angelegte Produkte: {own.products}, mit Cardmarket verknüpft {own.linked}, "
            f"mit Bild {own.with_image}"
        )
        emit("- Suche nur mit englischen Cardmarket-Namen (deutsche Namen finden nichts)\n")

        emit("## 5. Scanner\n")
        table(
            ["Modus", "Scans", "kein Treffer", "unsicher", "bestätigt", "korrigiert", "Ø ms"],
            [tuple(r) for r in await rows("scans")],
        )
        emit("Art der Korrekturen (Vorschlag ≠ bestätigte Karte):\n")
        table(["Art", "Anzahl"], [tuple(r) for r in await rows("correction_kinds")])
        emit("Neueste Korrekturen:\n")
        table(
            [
                "Tag",
                "Vorschlag Sprache",
                "Set",
                "Nr.",
                "Name",
                "richtig Sprache",
                "Set",
                "Nr.",
                "Name",
                "Sicherheit",
            ],
            [tuple(r) for r in await rows("corrections")],
        )
    await engine.dispose()


asyncio.run(main())
