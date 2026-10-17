#!/usr/bin/env bash
# Phase 3 auf dem VPS: Backend + Worker neu bauen (Migration 0003), Probe-Sammlung mit echten
# Preisen bewerten (wird NICHT gespeichert), Endpunkte prüfen.
# Ergebnis: docs/phase3/ergebnis.md
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase3_vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase3"
RESULT="${OUT_DIR}/ergebnis.md"
cd "${REPO_ROOT}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

[[ -f .env ]] || fail ".env fehlt – zuerst Phase 1 ausführen (bash deploy/phase1_vps.sh)."
mkdir -p "${OUT_DIR}"
set -a; source .env; set +a
psql_db() { docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1"; }

step "1/4 Backend und Worker bauen und starten (Migration 0003 läuft automatisch)"
docker compose up --build -d
health="keine Antwort"
for _ in $(seq 1 60); do
  if health_json="$(curl -fsS http://127.0.0.1:8000/api/v1/health 2>/dev/null)"; then
    health="${health_json}"
    break
  fi
  sleep 2
done
[[ "${health}" == *'"database":"ok"'* ]] || { docker compose logs --tail 60 api; fail "API nicht gesund: ${health}"; }
migration="$(docker compose exec -T api alembic current 2>/dev/null | tail -1)"
worker_state="$(docker compose ps --format '{{.Service}} {{.State}}' | grep '^worker' || echo 'worker fehlt')"
echo "Health: ${health}"
echo "Migration: ${migration}"
echo "${worker_state}"

step "2/4 Neue Tabellen"
tables="$(psql_db "SELECT string_agg(tablename, ', ' ORDER BY tablename) FROM pg_tables
                   WHERE schemaname = 'public' AND tablename IN
                   ('folders','collection_items','collection_events','portfolio_snapshots','wishlist_items','products')")"
echo "${tables}"

step "3/4 Probe-Sammlung mit echten Preisen (wird zurückgerollt)"
admin_email="$(psql_db "SELECT email FROM users WHERE role = 'admin' AND is_active ORDER BY created_at LIMIT 1")"
[[ -n "${admin_email}" ]] || fail "Kein aktiver Admin gefunden."
check_output="$(docker compose exec -T api python -m app.cli collection-check --email "${admin_email}" 2>&1 || true)"
echo "${check_output}"
leftovers="$(psql_db "SELECT count(*) FROM folders WHERE name = 'Phase-3-Probe'")"
echo "Übrig gebliebene Probe-Ordner: ${leftovers}"

step "4/4 Endpunkte ohne Anmeldung müssen 401 liefern"
endpoint_results=""
for path in folders collection/items collection/summary collection/history collection/export.csv wishlist dashboard products; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000/api/v1/${path}")"
  endpoint_results+="| /api/v1/${path} | ${code} |"$'\n'
  echo "/api/v1/${path} → ${code}"
done

{
  echo "# Phase 3 – Ergebnisse vom VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- Health: \`${health}\`"
  echo "- Migration: \`${migration}\`"
  echo "- Worker: \`${worker_state}\`"
  echo "- Neue Tabellen: ${tables}"
  echo "- Übrig gebliebene Probe-Ordner (Erwartung 0): ${leftovers}"
  echo
  echo "## Probe-Sammlung (echte Preise, zurückgerollt)"
  echo
  echo '```'
  echo "${check_output}"
  echo '```'
  echo
  echo "## Zugriffsschutz ohne Anmeldung (Erwartung 401)"
  echo
  echo "| Endpunkt | HTTP |"
  echo "|---|---|"
  printf '%s' "${endpoint_results}"
} > "${RESULT}"

step "Fertig"
echo "Ergebnis: ${RESULT}"
echo
echo "Ergebnisse zurückschicken:"
echo "  git add docs/phase3 && git commit -m 'Phase 3: Ergebnisse vom VPS' && git push"
