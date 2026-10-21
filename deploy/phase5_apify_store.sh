#!/usr/bin/env bash
# Spike Apify, Store-Suche (kostenlos, startet nichts): alle Cardmarket- und eBay-Dienste bewerten.
# Ergebnis: docs/phase5/apify_store.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/apify_store.py > docs/phase5/apify_store.md 2>&1 \
  || echo "(Exit-Code $?)" >> docs/phase5/apify_store.md
echo >> docs/phase5/apify_store.md
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> docs/phase5/apify_store.md
if grep -q "apify_api_" docs/phase5/apify_store.md; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
cat docs/phase5/apify_store.md
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Apify Store' && git push"
