#!/usr/bin/env bash
# Phase 4 auf dem VPS: Backend + Worker neu bauen (Migration 0004, OCR-Modelle inkl.
# Koreanisch), Scanner mit dem Testsatz messen (speichert keine Scans), Schutz prüfen.
# Ergebnis: docs/phase4/ergebnis.md (+ Evaluationsberichte)
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash deploy/phase4_vps.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase4"
RESULT="${OUT_DIR}/ergebnis.md"
cd "${REPO_ROOT}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }

[[ -f .env ]] || fail ".env fehlt – zuerst Phase 1 ausführen (bash deploy/phase1_vps.sh)."
[[ -f scanner_testset/soll.csv ]] || fail "scanner_testset/soll.csv fehlt."
mkdir -p "${OUT_DIR}"
set -a; source .env; set +a
psql_db() { docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1"; }

step "1/6 Backend und Worker bauen und starten (Migration 0004, OCR-Modelle werden geladen)"
build_log="${OUT_DIR}/docker_build.log"
if ! BUILDKIT_PROGRESS=plain docker compose build > "${build_log}" 2>&1; then
  tail -40 "${build_log}"
  fail "Docker-Build fehlgeschlagen (Protokoll: ${build_log})."
fi
grep -E "WARNUNG|Zeilen erkannt" "${build_log}" || true
docker compose up -d
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

step "2/6 OCR-Modelle im Container (Standard + Koreanisch)"
models="$(docker compose exec -T api python -m app.cli scanner-warmup --korean 2>&1 | tail -3 || true)"
echo "${models}"
volume_owner="$(docker compose exec -T api sh -c 'touch /data/scanner/.probe && rm /data/scanner/.probe && echo beschreibbar' 2>&1 || echo 'NICHT beschreibbar')"
echo "Scanner-Volume: ${volume_owner}"

step "3/6 Neue Tabellen"
tables="$(psql_db "SELECT string_agg(tablename, ', ' ORDER BY tablename) FROM pg_tables
                   WHERE schemaname = 'public' AND tablename IN ('scan_log','card_reference_images')")"
echo "${tables}"

step "4/6 Scanner mit dem Testsatz messen (zweimal: kalt mit Bild-Downloads, dann warm)"
admin_email="$(psql_db "SELECT email FROM users WHERE role = 'admin' AND is_active ORDER BY created_at LIMIT 1")"
[[ -n "${admin_email}" ]] || fail "Kein aktiver Admin gefunden."
docker compose exec -T api rm -rf /tmp/scanner_testset
docker compose cp scanner_testset api:/tmp/scanner_testset
for run in kalt warm; do
  docker compose exec -T api python -m app.cli scan-eval \
    --photos /tmp/scanner_testset --expected /tmp/scanner_testset/soll.csv \
    --email "${admin_email}" --out "/tmp/scan_eval_${run}.md"
  docker compose cp "api:/tmp/scan_eval_${run}.md" "${OUT_DIR}/scan_eval_${run}.md"
  echo "--- Lauf ${run} ---"
  sed -n '/## Kennzahlen/,/## Einzelergebnisse/p' "${OUT_DIR}/scan_eval_${run}.md" | grep '^-' || true
done
leftover_scans="$(psql_db "SELECT count(*) FROM scan_log")"
cache_files="$(docker compose exec -T api sh -c 'ls /data/scanner/catalog 2>/dev/null | wc -l')"
echo "Scan-Protokoll-Einträge (Erwartung 0, Evaluation speichert nichts): ${leftover_scans}"
echo "Merkmal-Cache-Dateien (Katalogbilder): ${cache_files}"
memory="$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep -E 'api|worker' || true)"
echo "${memory}"

step "5/6 Zugriffsschutz und Upload-Grenze"
endpoint_results=""
for entry in "POST scan" "POST scan/batch" "POST scan/binder" "GET scan/references"; do
  method="${entry%% *}"; path="${entry#* }"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X "${method}" "http://127.0.0.1:8000/api/v1/${path}")"
  endpoint_results+="| ${method} /api/v1/${path} | ${code} | 401 |"$'\n'
  echo "${method} /api/v1/${path} → ${code}"
done
# curl bricht nach der 413-Antwort ab – der Abbruch von „head“ ist dabei gewollt.
big_code="$( (head -c 40000000 /dev/zero | curl -s -o /dev/null -w '%{http_code}' -X POST \
  -H 'Content-Type: multipart/form-data; boundary=x' --data-binary @- \
  http://127.0.0.1:8000/api/v1/scan) || true)"
endpoint_results+="| POST /api/v1/scan mit 40 MB | ${big_code} | 413 |"$'\n'
echo "Upload 40 MB → ${big_code}"

step "6/6 Ergebnis schreiben"
{
  echo "# Phase 4 – Ergebnisse vom VPS"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- Health: \`${health}\`"
  echo "- Migration: \`${migration}\`"
  echo "- Worker: \`${worker_state}\`"
  echo "- Neue Tabellen: ${tables}"
  echo "- Scanner-Volume: ${volume_owner}"
  echo "- Scan-Protokoll nach der Evaluation (Erwartung 0): ${leftover_scans}"
  echo "- Merkmal-Cache-Dateien: ${cache_files}"
  echo
  echo "## OCR-Modelle"
  echo
  echo '```'
  echo "${models}"
  grep -E "WARNUNG|Zeilen erkannt" "${build_log}" || echo "(keine Hinweise im Build-Log)"
  echo '```'
  echo
  echo "## Speicher"
  echo
  echo '```'
  echo "${memory}"
  echo '```'
  echo
  echo "## Evaluation"
  echo
  echo "- Kalt (erste Messung, lädt Katalogbilder): [\`scan_eval_kalt.md\`](scan_eval_kalt.md)"
  echo "- Warm (mit Cache, entspricht dem Alltag): [\`scan_eval_warm.md\`](scan_eval_warm.md)"
  echo
  sed -n '/## Kennzahlen/,/## Einzelergebnisse/p' "${OUT_DIR}/scan_eval_warm.md" | sed '$d'
  echo
  echo "## Zugriffsschutz und Upload-Grenze"
  echo
  echo "| Anfrage | HTTP | Erwartung |"
  echo "|---|---|---|"
  printf '%s' "${endpoint_results}"
} > "${RESULT}"
docker compose exec -T api rm -rf /tmp/scanner_testset /tmp/scan_eval_kalt.md /tmp/scan_eval_warm.md

step "Fertig"
echo "Ergebnis: ${RESULT}"
echo
echo "Ergebnisse zurückschicken:"
echo "  git add docs/phase4 && git commit -m 'Phase 4: Ergebnisse vom VPS' && git push"
