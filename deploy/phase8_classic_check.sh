#!/usr/bin/env bash
# Prüft, ob die japanische Classic Collection (2023: CLL Glurak-, CLF Bisaflor-, CLK Turtok-Deck,
# je 32 Karten) im Katalog steckt – und woher die beim Binder-Scan gewählten Grundset-Karten
# stammen. Nur Lesen, nichts wird geändert. Ausgabe bitte komplett zurückschicken.
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase8_classic_check.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
[[ -f .env ]] || { echo ".env fehlt"; exit 1; }
set -a; source .env; set +a

psql_db() { docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "$1"; }

echo "== 1) Sets mit Kürzel CL*, „Classic“ oder „クラシック“"
psql_db "SELECT s.external_id, s.language, s.name, s.card_count_official AS offiziell,
       count(c.id) AS karten, s.release_date
FROM card_sets s LEFT JOIN cards c ON c.set_id = s.id
WHERE s.game = 'pokemon' AND (s.external_id ILIKE 'CL%' OR s.name ILIKE '%classic%'
      OR s.name LIKE '%クラシック%' OR s.code ILIKE 'CL%')
GROUP BY s.id ORDER BY s.language, s.external_id;"

echo "== 2) Japanische Karten mit Setgröße 32 (Classic Collection hat 001/032 … 032/032)"
psql_db "SELECT s.external_id, s.name, s.card_count_official, count(c.id) AS karten
FROM card_sets s JOIN cards c ON c.set_id = s.id
WHERE s.language = 'ja' AND s.card_count_official = 32
GROUP BY s.id ORDER BY s.external_id;"

echo "== 3) Woher stammt „Glumanda“ (ヒトカゲ) auf Japanisch?"
psql_db "SELECT s.external_id, s.name, s.card_count_official AS offiziell, c.number,
       c.external_id AS karte, c.image_source
FROM cards c JOIN card_sets s ON s.id = c.set_id
WHERE c.language = 'ja' AND c.name LIKE 'ヒトカゲ%' ORDER BY s.release_date NULLS FIRST;"

echo "== 4) Letzte Binder-Scans: gelesene Nummern/Namen je Zelle"
psql_db "SELECT to_char(l.created_at, 'HH24:MI:SS') AS zeit, l.duration_ms,
       l.detected->'numbers' AS nummern, l.detected->'names' AS namen, l.confident,
       c.name AS treffer, s.external_id AS set_
FROM scan_log l LEFT JOIN cards c ON c.id = l.best_card_id LEFT JOIN card_sets s ON s.id = c.set_id
WHERE l.mode = 'binder' ORDER BY l.created_at DESC LIMIT 9;"
