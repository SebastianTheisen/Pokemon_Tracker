#!/bin/sh
# Tägliche Sicherung (Dienst „backup“ in docker-compose.yml):
#   - Datenbank als pg_dump (Custom-Format, komprimiert): db-JJJJMMTT-HHMMSS.dump
#   - Scanner-Daten (eigene Referenzbilder, Merkmal-Cache): scanner-JJJJMMTT-HHMMSS.tar.gz
# Aufbewahrung BACKUP_KEEP_DAYS Tage (Standard 14). Uhrzeit BACKUP_TIME (UTC, Standard 02:30).
# „latest“ enthält den Zeitstempel der letzten vollständigen Sicherung (für die Überwachung).
#
#   sh backup.sh now     # sofort einmal sichern (Test)
#   sh backup.sh         # Dauerbetrieb: täglich zur Uhrzeit
set -eu
DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
AT="${BACKUP_TIME:-02:30}"
mkdir -p "${DIR}"

run() {
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  echo "$(date -u +%FT%TZ) Sicherung ${stamp} startet"
  pg_dump -h db -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc -Z 6 \
    -f "${DIR}/db-${stamp}.dump.part"
  mv "${DIR}/db-${stamp}.dump.part" "${DIR}/db-${stamp}.dump"
  if [ -d /data/scanner ]; then
    tar -czf "${DIR}/scanner-${stamp}.tar.gz.part" -C /data scanner
    mv "${DIR}/scanner-${stamp}.tar.gz.part" "${DIR}/scanner-${stamp}.tar.gz"
  fi
  printf '%s\n' "${stamp}" > "${DIR}/latest"
  find "${DIR}" -maxdepth 1 \( -name 'db-*.dump' -o -name 'scanner-*.tar.gz' \) \
    -mtime "+${KEEP_DAYS}" -delete
  rm -f "${DIR}"/*.part
  echo "$(date -u +%FT%TZ) Sicherung ${stamp} fertig: $(du -sh "${DIR}" | cut -f1) belegt"
}

if [ "${1:-}" = "now" ]; then
  run
  exit 0
fi

echo "Sicherung täglich um ${AT} UTC, Aufbewahrung ${KEEP_DAYS} Tage"
while true; do
  if [ "$(date -u +%H:%M)" = "${AT}" ]; then
    run || echo "$(date -u +%FT%TZ) Sicherung fehlgeschlagen"
    sleep 61
  fi
  sleep 30
done
