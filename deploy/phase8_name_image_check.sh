#!/usr/bin/env bash
# Binder-Scan prüfen: Katalogfassungen einer Karte und Bildabgleich gegen ein eigenes Foto.
# Nur lesend. Optional: das Foto/den Screenshot als ~/scan.jpg auf den VPS legen (z. B. per
# SFTP in Termius) – dann wird es in den api-Container kopiert und Feld für Feld abgeglichen.
#
#   bash deploy/phase8_name_image_check.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -f "${HOME}/scan.jpg" ]]; then
  docker compose cp "${HOME}/scan.jpg" api:/tmp/scan.jpg
  echo "Foto ~/scan.jpg wird abgeglichen."
else
  docker compose exec -T -u root api rm -f /tmp/scan.jpg || true
  echo "Kein ~/scan.jpg – nur Katalog und letzte Scans."
fi
docker compose exec -T api python - < deploy/spikes/name_image_check.py
