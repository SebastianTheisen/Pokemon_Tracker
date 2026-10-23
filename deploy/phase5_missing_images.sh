#!/usr/bin/env bash
# Welche Karten haben (noch) kein Bild? Je Sprache die Sets mit den meisten Lücken.
# Ergebnis: docs/phase5/missing_images.md
#
#   bash deploy/phase5_missing_images.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a
OUT="docs/phase5/missing_images.md"
mkdir -p docs/phase5

sql() {
  docker compose exec -T db psql -U "${POSTGRES_USER:-tracker}" -d "${POSTGRES_DB:-tracker}" \
    -P pager=off -P footer=off --csv -c "$1"
}

{
  echo "# Karten ohne Bild ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo '```'
  sql "SELECT c.language, s.external_id, s.name, coalesce(s.code, '') AS code,
              count(*) FILTER (WHERE c.image_url IS NULL) AS ohne_bild, count(*) AS gesamt,
              min(c.number) AS beispiel_nr
       FROM cards c JOIN card_sets s ON s.id = c.set_id
       GROUP BY 1, 2, 3, 4
       HAVING count(*) FILTER (WHERE c.image_url IS NULL) > 0
       ORDER BY 1, 5 DESC"
  echo '```'
} > "${OUT}"

echo "Fertig: ${OUT}"
echo "Bitte pushen: git add docs/phase5 && git commit -m 'Karten ohne Bild' && git push"
