#!/usr/bin/env bash
# Sammlungskarten ohne Wert reparieren – ein Durchgang, keine Handarbeit:
#   1. API und Worker mit dem aktuellen Stand neu bauen
#   2. PriceCharting-Prüfungen von Sammlungskarten ohne PriceCharting-Wert zurücksetzen
#      (bisher galten Fehlschläge als „ok“ und wurden erst nach Tagen neu versucht)
#   3. Preis-Runde (Cardmarket, PriceCharting für Slabs und Karten ohne Cardmarket-Wert)
#   4. Liste der Positionen, die danach noch keinen Wert haben – mit Grund
# Ergebnis: docs/phase8/missing_values.md
#
#   bash deploy/phase8_missing_values.sh
set -eu
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="docs/phase8/missing_values.md"
mkdir -p docs/phase8

wait_for_api() {
  for _ in $(seq 1 60); do
    if docker compose exec -T api python -c \
      "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "API antwortet nicht – Protokoll: docker compose logs --tail 50 api" >&2
  exit 1
}
run() { docker compose exec -T api python -m app.cli "$@" 2>&1 | grep -v -E '^\{|\[(info|debug) '; }

echo "== API und Worker bauen =="
docker compose up -d --build api worker
wait_for_api
{
  echo "## PriceCharting neu suchen"; run pricecharting-recheck --apply; echo
  echo "## Preise"; run refresh-prices; echo
  echo "## Noch ohne Wert"
  docker compose exec -T api python - < deploy/spikes/missing_values.py 2>&1 \
    | grep -v -E '^\{|\[(info|debug) '
  echo; echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} | tee "${out}"
