#!/usr/bin/env bash
# Letzte Collectr-Vorschau anzeigen (Rohzeilen vom Lesezeichen + Vorschläge). Nur lesend.
#
#   bash deploy/phase8_collectr_last.sh            # alle Kacheln
#   bash deploy/phase8_collectr_last.sh Kahili     # nur Kacheln mit „Kahili“
#   bash deploy/phase8_collectr_last.sh check      # nur „bitte prüfen“ (auch: missing, unlesbar)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose exec -T -e FILTER="${1:-}" api python - < deploy/spikes/collectr_last.py
