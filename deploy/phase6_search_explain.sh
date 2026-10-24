#!/usr/bin/env bash
# Spike: Abfrageplan der Kartensuche (liest nur). Ergebnis: docs/phase6/search_explain.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase6
docker compose exec -T api python - < deploy/spikes/search_explain.py > docs/phase6/search_explain.md 2>&1 || true
cat docs/phase6/search_explain.md
echo
echo "Bitte pushen: git add docs/phase6 && git commit -m 'Suche: Abfrageplan' && git push"
