#!/usr/bin/env bash
# Phase 2 auf dem VPS: Backend + Preis-Worker neu bauen, echte Preise abrufen, prüfen.
# Ergebnis: docs/phase2/ergebnis.md
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase2_vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase2"
RESULT="${OUT_DIR}/ergebnis.md"
cd "${REPO_ROOT}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

[[ -f .env ]] || fail ".env fehlt – zuerst Phase 1 ausführen (bash deploy/phase1_vps.sh)."
mkdir -p "${OUT_DIR}"
set -a; source .env; set +a

step "1/4 Backend und Preis-Worker bauen und starten (Migration 0002 läuft automatisch)"
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
echo "Health: ${health}"

step "2/4 Migrationsstand und Worker"
migration="$(docker compose exec -T api alembic current 2>/dev/null | tail -1)"
echo "Migration: ${migration}"
sleep 3
worker_state="$(docker compose ps --format '{{.Service}} {{.State}}' | grep '^worker' || echo 'worker fehlt')"
worker_log="$(docker compose logs --tail 5 worker 2>&1 | grep -E 'worker\.|pricing\.' | tail -2 || true)"
echo "${worker_state}"
echo "${worker_log}"

step "3/4 Echte Preise abrufen"
queries=(
  "nachtara 215|de"
  "umbreon 215|en"
  "Team Rockets Mewtu ex 231|de"
  "ルギアV 110|ja"
  "ブラッキーex 217|ja"
  "洛奇亞V 110|zh-tw"
  "glurak 4|de"
)
price_output=""
for entry in "${queries[@]}"; do
  query="${entry%%|*}"; language="${entry##*|}"
  result="$(docker compose exec -T api python -m app.cli prices "${query}" --language "${language}" 2>&1 || true)"
  price_output+=$'\n'"### \`${query}\` (${language})"$'\n\n```\n'"${result}"$'\n```\n'
  printf '\n> %s (%s)\n%s\n' "${query}" "${language}" "${result}"
done

step "4/4 Preis-Historie in der Datenbank"
psql_db() { docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1"; }
history="$(psql_db "SELECT source, currency, count(*), count(DISTINCT card_id), min(source_updated_at)::date, max(source_updated_at)::date
                    FROM price_points GROUP BY source, currency ORDER BY source" | tr '|' ' ')"
echo "${history}"

{
  echo "# Phase 2 – Ergebnisse vom VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- Health: \`${health}\`"
  echo "- Migration: \`${migration}\`"
  echo "- Worker: \`${worker_state}\`"
  echo
  echo '```'
  echo "${worker_log}"
  echo '```'
  echo
  echo "## Gespeicherte Preiswerte"
  echo
  echo "| Quelle | Währung | Werte | Karten | ältester Stand | neuester Stand |"
  echo "|---|---|---|---|---|---|"
  while read -r source currency values cards first last; do
    [[ -n "${source}" ]] && echo "| ${source} | ${currency} | ${values} | ${cards} | ${first} | ${last} |"
  done <<< "${history}"
  echo
  echo "## Preisabrufe"
  echo "${price_output}"
} > "${RESULT}"

step "Fertig"
echo "Ergebnis: ${RESULT}"
echo
echo "Ergebnisse zurückschicken:"
echo "  git add docs/phase2 && git commit -m 'Phase 2: Ergebnisse vom VPS' && git push"
