#!/usr/bin/env bash
# Phase 6: Lasttest gegen die echte Datenbank (liest nur). Ergebnis: docs/phase6/loadtest.md
#
#   bash deploy/phase6_loadtest.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase6
docker compose exec -T api python - < deploy/spikes/loadtest.py 2>&1 | grep -v '^\s*$\|\[info' \
  > docs/phase6/loadtest.md || true
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase6/loadtest.md
cat docs/phase6/loadtest.md
echo
echo "Bitte pushen: git add docs/phase6 && git commit -m 'Lasttest' && git push"
