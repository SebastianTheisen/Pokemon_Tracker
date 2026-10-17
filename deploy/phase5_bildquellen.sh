#!/usr/bin/env bash
# Spike: offizielle Kartendatenbanken (JP/KO/TW) als Bildquelle prüfen.
# Ergebnis: docs/phase5/bildquellen.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/official_images.py > docs/phase5/bildquellen.md
cat docs/phase5/bildquellen.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Bildquellen' && git push"
