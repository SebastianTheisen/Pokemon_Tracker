#!/usr/bin/env bash
# Fehlende Karten japanischer Sets (z. B. Secret Rares über der Setgröße wie „Rare Candy
# 086/076“) aus dem TCGplayer-Katalog (tcgcsv.com) ergänzen. Neue Sets werden nicht angelegt,
# vorhandene Karten nicht verändert. Ergebnis: docs/phase8/japanese_gaps.md
#
#   bash deploy/phase8_japanese_gaps.sh            # Probelauf: nur zeigen, was fehlt
#   bash deploy/phase8_japanese_gaps.sh --apply    # fehlende Karten anlegen
#   bash deploy/phase8_japanese_gaps.sh --apply --set BW9   # nur ein Set
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out="docs/phase8/japanese_gaps.md"
mkdir -p docs/phase8
{
  docker compose exec -T api python -m app.cli catalog-gaps-ja "$@" 2>&1 \
    | grep -v -E '^\{|\[(info|debug) ' || echo "(Exit-Code $?)"
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} > "${out}"
cat "${out}"
