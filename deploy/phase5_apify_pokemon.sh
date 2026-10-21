#!/usr/bin/env bash
# Spike Apify: Store nach allem rund um Pokémon durchsuchen (kostenlos, startet nichts).
# Ergebnis: docs/phase5/apify_pokemon.md (enthält keinen Token)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/apify_pokemon.md"
mkdir -p docs/phase5
docker compose exec -T -e APIFY_STORE_TOPIC=pokemon api python - < deploy/spikes/apify_store.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
if grep -q "apify_api_" "${out}"; then
  echo "Achtung: Der Bericht enthält etwas Token-Ähnliches – nicht pushen!" >&2
  exit 1
fi
head -60 "${out}"
echo "… (vollständig in ${out})"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Spike Apify Pokemon' && git push"
