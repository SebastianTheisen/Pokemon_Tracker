#!/usr/bin/env bash
# Preise für japanische Karten ohne Wert (v. a. Trainer): Namen → Cardmarket → Preise.
#   1. Englische Namen aus TCGplayer für vorhandene Karten (und fehlende Karten ergänzen)
#   2. Cardmarket-Zuordnung über die Namen neu laufen lassen
#   3. Englische Namen aus den nun verknüpften Cardmarket-Produkten
#   4. Preise aller Sammlungs-/Merklisten-Karten holen
# Ergebnis: docs/phase8/japanese_prices.md
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="docs/phase8/japanese_prices.md"
mkdir -p docs/phase8
run() { docker compose exec -T api python -m app.cli "$@" 2>&1 | grep -v -E '^\{|\[(info|debug) '; }
{
  echo "## 1) TCGplayer: Namen + Lücken"; run catalog-gaps-ja --apply | head -3
  echo; echo "## 2) Cardmarket-Zuordnung"; run cardmarket-match | head -25
  echo; echo "## 3) Namen aus Cardmarket"; run japanese-names
  echo; echo "## 4) Preise"; run refresh-prices
  echo; echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} | tee "${out}"
