#!/usr/bin/env bash
# Quellen-Messung: Zielzahlen je Sprache aus verlässlichen Quellen gegen unseren Katalog.
# Nur lesend, kostenlos, ca. 15 Minuten (Japan: alle Seiten der offiziellen Kartensuche).
# Ergebnis: docs/phase5/quellen.md
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
out="docs/phase5/quellen.md"
mkdir -p docs/phase5
echo "Läuft ca. 15 Minuten – Zwischenstand: tail -f ${out}"
docker compose exec -T api python - < deploy/spikes/quellen.py > "${out}" 2>&1 \
  || echo "(Exit-Code $?)" >> "${out}"
echo >> "${out}"
echo "_Lauf: $(date -u '+%Y-%m-%d %H:%M UTC'), Stand $(git rev-parse --short HEAD)_" >> "${out}"
head -40 "${out}"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Quellen-Messung' && git push"
