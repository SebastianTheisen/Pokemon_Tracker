#!/usr/bin/env bash
# Spike: offizielle Cardmarket-Downloads prüfen (Produktkatalog + Preisführer).
# Ergebnis: docs/phase5/cardmarket_katalog.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/cardmarket_catalog.py > docs/phase5/cardmarket_katalog.md
echo >> docs/phase5/cardmarket_katalog.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/cardmarket_katalog.md
cat docs/phase5/cardmarket_katalog.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Cardmarket-Katalog' && git push"
