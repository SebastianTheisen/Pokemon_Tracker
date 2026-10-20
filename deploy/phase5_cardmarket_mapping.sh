#!/usr/bin/env bash
# Spike 2: TCGdex→Cardmarket-Verknüpfung mit dem offiziellen Katalog prüfen.
# Ergebnis: docs/phase5/cardmarket_mapping.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/cardmarket_mapping.py > docs/phase5/cardmarket_mapping.md 2>&1 || echo "(Exit-Code $?)" >> docs/phase5/cardmarket_mapping.md
echo >> docs/phase5/cardmarket_mapping.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/cardmarket_mapping.md
cat docs/phase5/cardmarket_mapping.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Cardmarket-Verknuepfung' && git push"
