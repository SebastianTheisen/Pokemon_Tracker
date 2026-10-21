#!/usr/bin/env bash
# Erkundung 2: Aufbau von PokéWiki, pokemon.com/de, pokemon-card.com (Japan) und
# asia.pokemon-card.com (Taiwan) für die Importe. Nur lesend, kostenlos, ca. 3 Minuten.
# Ergebnis: docs/phase5/quellen2.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/quellen2.md"
mkdir -p docs/phase5
docker compose exec -T api python - < deploy/spikes/quellen2.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
head -30 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Erkundung 2' && git push"
