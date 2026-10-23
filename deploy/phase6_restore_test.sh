#!/usr/bin/env bash
# Phase 6: Wiederherstellungstest – die letzte Sicherung in eine Test-Datenbank einspielen und
# mit der laufenden Datenbank vergleichen. Die laufende Datenbank wird nicht verändert.
# Ergebnis: docs/phase6/restore_test.md
#
#   bash deploy/phase6_restore_test.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="docs/phase6/restore_test.md"
TEST_DB="tracker_restore_test"
mkdir -p docs/phase6
stamp="$(cat backups/latest 2>/dev/null || true)"
[[ -n "${stamp}" ]] || { echo "Keine Sicherung gefunden – zuerst bash deploy/phase6_setup.sh" >&2; exit 1; }

in_backup() { docker compose exec -T backup sh -c "$1"; }
count() {  # $1 = Datenbank, $2 = Tabelle
  in_backup "psql -h db -U \"\$POSTGRES_USER\" -d $1 -tAc 'SELECT count(*) FROM $2'"
}

echo "Sicherung ${stamp} wird in ${TEST_DB} eingespielt …"
in_backup "dropdb -h db -U \"\$POSTGRES_USER\" --if-exists ${TEST_DB} && createdb -h db -U \"\$POSTGRES_USER\" ${TEST_DB}"
started=$(date +%s)
in_backup "pg_restore -h db -U \"\$POSTGRES_USER\" -d ${TEST_DB} --no-owner --exit-on-error /backups/db-${stamp}.dump"
seconds=$(( $(date +%s) - started ))

tables="users cards card_sets collection_items wishlist_items price_points portfolio_snapshots card_reference_images cm_products"
ok=true
{
  echo "# Wiederherstellungstest ($(date -u '+%Y-%m-%d %H:%M UTC'))"
  echo
  echo "Sicherung: \`${stamp}\`, eingespielt in ${seconds} s."
  echo
  echo "| Tabelle | laufend | aus Sicherung | |"
  echo "|---|---:|---:|---|"
  for table in ${tables}; do
    live="$(count "\$POSTGRES_DB" "${table}" | tr -d '[:space:]')"
    restored="$(count "${TEST_DB}" "${table}" | tr -d '[:space:]')"
    # Seit der Sicherung können Daten dazugekommen sein: weniger ist ok, 0 bei Bestand nicht.
    if [[ "${restored}" -le "${live}" && ( "${live}" -eq 0 || "${restored}" -gt 0 ) ]]; then
      mark="✅"
    else
      mark="❌"; ok=false
    fi
    echo "| ${table} | ${live} | ${restored} | ${mark} |"
  done
  echo
  files="$(in_backup "tar -tzf /backups/scanner-${stamp}.tar.gz 2>/dev/null | wc -l" | tr -d '[:space:]')"
  echo "Scanner-Daten: ${files} Einträge im Archiv."
  echo
  if ${ok}; then echo "**Ergebnis: Wiederherstellung funktioniert.**"; else echo "**Ergebnis: Abweichung – prüfen!**"; fi
} > "${OUT}"

in_backup "dropdb -h db -U \"\$POSTGRES_USER\" ${TEST_DB}"
cat "${OUT}"
echo
echo "Bitte pushen: git add docs/phase6 && git commit -m 'Wiederherstellungstest' && git push"
