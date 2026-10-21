#!/usr/bin/env bash
# Ein Geheimnis (Token, Schlüssel) verdeckt abfragen und in die .env eintragen – nie ins Repo,
# nicht in die Shell-Historie. Danach starten API und Worker neu.
#   bash deploy/set_secret.sh PT_PSA_TOKEN
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
name="${1:-}"
if [[ ! "${name}" =~ ^PT_[A-Z0-9_]+$ ]]; then
  echo "Aufruf: bash deploy/set_secret.sh PT_NAME (z. B. PT_PSA_TOKEN)" >&2
  exit 1
fi
[[ -f .env ]] || { echo ".env fehlt – zuerst Phase 1 ausführen." >&2; exit 1; }

read -r -s -p "${name} einfügen (wird nicht angezeigt): " value
echo
value="$(printf '%s' "${value}" | tr -d '[:space:]')"
if [[ ${#value} -lt 16 ]]; then
  echo "Zu kurz für einen Token – nichts geändert." >&2
  exit 1
fi

tmp="$(mktemp)"
grep -v "^${name}=" .env > "${tmp}" || true
printf '%s=%s\n' "${name}" "${value}" >> "${tmp}"
cat "${tmp}" > .env
rm -f "${tmp}"
chmod 600 .env
echo "${name} in .env eingetragen (Ende: …${value: -4})."

docker compose up -d --force-recreate api worker
echo "API und Worker neu gestartet."
