#!/usr/bin/env bash
# Spike: offizielle Kartendatenbanken (JP/KO/TW) als Bildquelle prüfen.
# Ergebnis: docs/phase5/bildquellen.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
set -a; source .env; set +a
psql_db() { docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1"; }

if ! grep -q "def western" deploy/spikes/official_images.py; then
  echo "FEHLER: alter Stand – bitte zuerst 'git pull' ausführen." >&2
  exit 1
fi

echo "==> Neuen Stand bauen (Migration 0005: Ersatzbilder) und fehlende Bilder ergänzen"
docker compose up -d --build api worker
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && break; sleep 2; done
coverage_before="$(psql_db "SELECT language || ': ' || count(*) FILTER (WHERE image_url IS NOT NULL) || '/' || count(*) FROM cards GROUP BY language ORDER BY language")"
fill="$(docker compose exec -T api python -m app.cli fill-images 2>&1 | tail -1)"
coverage_after="$(psql_db "SELECT language || ': ' || count(*) FILTER (WHERE image_url IS NOT NULL) || '/' || count(*) FROM cards GROUP BY language ORDER BY language")"
samples="$(psql_db "SELECT coalesce(json_agg(t), '[]') FROM (
  (SELECT c.language, c.name, c.number, s.external_id AS set, s.logo_url AS logo FROM cards c JOIN card_sets s ON s.id = c.set_id
   WHERE c.image_url IS NULL AND c.language = 'de' ORDER BY random() LIMIT 8)
  UNION ALL
  (SELECT c.language, c.name, c.number, s.external_id, s.logo_url FROM cards c JOIN card_sets s ON s.id = c.set_id
   WHERE c.image_url IS NULL AND c.language = 'en' ORDER BY random() LIMIT 8)) t")"

echo "==> Bildquellen testen (ca. 2 Minuten)"
docker compose exec -T -e SAMPLES="${samples}" api python - < deploy/spikes/official_images.py > docs/phase5/bildquellen.md
{
  echo
  echo "## Abdeckung unseres Katalogs (mit Bild / gesamt)"
  echo
  echo "Vorher:"; echo '```'; echo "${coverage_before}"; echo '```'
  echo "Ersatzbilder aus anderer Sprachfassung: ${fill}"; echo
  echo "Nachher:"; echo '```'; echo "${coverage_after}"; echo '```'
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} >> docs/phase5/bildquellen.md
cat docs/phase5/bildquellen.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Bildquellen DE/EN' && git push"
