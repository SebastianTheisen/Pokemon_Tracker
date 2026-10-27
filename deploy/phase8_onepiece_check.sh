#!/usr/bin/env bash
# Prüfung nach dem One-Piece-Import: Führt Cardmarket eigene japanische Ausgaben? Welche
# Karten haben noch kein Produkt? Nur lesend (Datenbank), wenige Sekunden.
# Ergebnis: docs/phase8/onepiece_check.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase8/onepiece_check.md"
mkdir -p docs/phase8
docker compose exec -T api python - < deploy/spikes/onepiece_check.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
head -40 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase8 && git commit -m 'One Piece: Prüfung' && git push"
