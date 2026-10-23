#!/usr/bin/env bash
# Japan nach dem Import der offiziellen Datenbank: Wo fehlen Bilder, was blieb unzugeordnet?
# Ergebnis: docs/phase5/jp_check.md
#
#   bash deploy/phase5_jp_check.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a
OUT="docs/phase5/jp_check.md"
mkdir -p docs/phase5

sql() {
  docker compose exec -T db psql -U "${POSTGRES_USER:-tracker}" -d "${POSTGRES_DB:-tracker}" \
    -P pager=off -P footer=off --csv -c "$1"
}

{
  echo "# Japan-Prüfung ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo "## Offizielle Datenbank (pokemon-card.com)"
  echo '```'
  sql "SELECT count(*) AS gelistet,
              count(*) FILTER (WHERE number IS NOT NULL) AS mit_nummer,
              count(*) FILTER (WHERE detail_fetched_at IS NOT NULL) AS detail_gelesen,
              count(*) FILTER (WHERE card_id IS NOT NULL) AS zugeordnet,
              count(*) FILTER (WHERE number IS NULL AND detail_fetched_at IS NOT NULL) AS ohne_nummer_trotz_detail,
              count(*) FILTER (WHERE number IS NULL AND detail_fetched_at IS NULL) AS detail_offen
       FROM official_cards WHERE source = 'pokemon-card.com'"
  echo '```'
  echo
  echo "### Beispiele ohne Nummer (trotz Detailseite)"
  echo '```'
  sql "SELECT official_id, set_code, name FROM official_cards
       WHERE source = 'pokemon-card.com' AND number IS NULL AND detail_fetched_at IS NOT NULL
       ORDER BY random() LIMIT 25"
  echo '```'
  echo
  echo "### Ohne Nummer nach Setcode (Top 30)"
  echo '```'
  sql "SELECT coalesce(set_code, '?') AS set_code, count(*) FROM official_cards
       WHERE source = 'pokemon-card.com' AND number IS NULL
       GROUP BY 1 ORDER BY 2 DESC LIMIT 30"
  echo '```'
  echo
  echo "## Japanische Karten ohne Bild nach Set (Top 40)"
  echo '```'
  sql "SELECT s.external_id, s.name, s.release_date,
              count(*) FILTER (WHERE c.image_url IS NULL) AS ohne_bild, count(*) AS gesamt
       FROM cards c JOIN card_sets s ON s.id = c.set_id
       WHERE c.language = 'ja'
       GROUP BY s.external_id, s.name, s.release_date
       HAVING count(*) FILTER (WHERE c.image_url IS NULL) > 0
       ORDER BY 4 DESC LIMIT 40"
  echo '```'
  echo
  echo "## Neu angelegte Sets (Offizielle Datenbank)"
  echo '```'
  sql "SELECT s.external_id, count(c.id) AS karten FROM card_sets s
       LEFT JOIN cards c ON c.set_id = s.id
       WHERE s.language = 'ja' AND s.series_name = 'Offizielle Datenbank'
       GROUP BY s.external_id ORDER BY 2 DESC"
  echo '```'
} > "${OUT}"

echo "Fertig: ${OUT}"
echo "Bitte pushen: git add docs/phase5 && git commit -m 'Japan-Pruefung' && git push"
