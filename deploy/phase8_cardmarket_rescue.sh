#!/usr/bin/env bash
# Sammlungskarten ohne Cardmarket-Verknüpfung nachträglich zuordnen (Name mehrfach in der
# Ausgabe, kleine Sets ohne Ausgabe) und danach Preise holen. Läuft künftig auch automatisch
# nach jedem Cardmarket-Import. Ergebnis: docs/phase8/cardmarket_rescue.md
#
#   bash deploy/phase8_cardmarket_rescue.sh          # Probelauf: nur zeigen
#   bash deploy/phase8_cardmarket_rescue.sh --apply  # speichern + Preise holen
set -eu
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="docs/phase8/cardmarket_rescue.md"
mkdir -p docs/phase8
run() { docker compose exec -T api python -m app.cli "$@" 2>&1 | grep -v -E '^\{|\[(info|debug) '; }
{
  run cardmarket-rescue --owned "$@"
  if [[ "${1:-}" == "--apply" ]]; then echo; echo "## Preise"; run refresh-prices; fi
  echo; echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} | tee "${out}"
