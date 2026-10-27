#!/usr/bin/env bash
# Phase 8: One Piece erstmals importieren (danach übernimmt der Worker: Cardmarket täglich,
# Kartenlisten wöchentlich).
#   1. Cardmarket-Downloads für One Piece (Spiel 18): Einzelkarten, Sealed, Preisführer.
#   2. Offizielle Kartenlisten EN + JP (ein Abruf je Set, 1,5 s Pause; ca. 4 Minuten),
#      danach Sets und Karten mit Cardmarket verknüpfen.
# Kostenlos, nur lesend bei den Quellen. Ergebnis: docs/phase8/onepiece_import.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase8/onepiece_import.md"
mkdir -p docs/phase8
{
  echo "# One Piece: erster Import"
  echo
  echo "## Cardmarket (Spiel 18)"
  echo
  echo '```'
  docker compose exec -T api python -m app.cli cardmarket-import --game onepiece --no-link 2>&1 \
    | grep -E '^\[onepiece\]|^Fehler|Bilder' || echo "(Exit-Code $?)"
  echo '```'
  echo
  docker compose exec -T api python -m app.cli onepiece-import 2>&1 | grep -v '^{' \
    || echo "(Exit-Code $?)"
  echo
  echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_"
} > "${out}"
cat "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase8 && git commit -m 'One Piece: erster Import' && git push"
