#!/usr/bin/env bash
# Stand des Cardmarket-Katalogs: letzter Import, Ausgabe je Set, unsichere Sets.
# Der Worker importiert den Katalog ca. 2 Minuten nach dem Start und danach täglich.
# Mit --jetzt wird der Import sofort gestartet (dauert einige Minuten: Sets bei TCGdex).
# Ergebnis: docs/phase5/cardmarket_status.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
if [[ "${1:-}" == "--jetzt" ]]; then
  docker compose exec -T api python -m app.cli cardmarket-import > docs/phase5/cardmarket_status.md 2>&1 \
    || echo "(Exit-Code $?)" >> docs/phase5/cardmarket_status.md
else
  docker compose exec -T api python -m app.cli cardmarket-status > docs/phase5/cardmarket_status.md 2>&1 \
    || echo "(Exit-Code $?)" >> docs/phase5/cardmarket_status.md
fi
echo >> docs/phase5/cardmarket_status.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/cardmarket_status.md
cat docs/phase5/cardmarket_status.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Cardmarket-Status' && git push"
