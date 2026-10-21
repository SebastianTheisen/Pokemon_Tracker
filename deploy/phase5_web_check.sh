#!/usr/bin/env bash
# Phase 5: Prüft, ob die Web-App vollständig ausgeliefert wird („Load failed“ am Handy).
#   - liefert die API alle Dateien der Web-App ganz aus (Größe auf der Platte = geliefert)?
#   - Laufzeit und Neustarts von api/worker, freier Speicher, Fehler im API-Protokoll
# Ergebnis: docs/phase5/web_check.md
#
#   bash deploy/phase5_web_check.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase5"
RESULT="${OUT_DIR}/web_check.md"
cd "${REPO_ROOT}"
mkdir -p "${OUT_DIR}"

mask() { sed -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g'; }
WEB="app/build/web"
BASE="http://127.0.0.1:8000"

{
  echo "# Phase 5 – Prüfung Web-App"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- Gebauter App-Stand: $(cat "${WEB}/.app-revision" 2>/dev/null || echo unbekannt)" \
    "· App-Stand im Git: $(git rev-parse HEAD:app 2>/dev/null || echo unbekannt)"
  echo
  echo "## Dateien (Platte → ausgeliefert)"
  echo
  echo "| Datei | Platte (Bytes) | HTTP | geliefert (Bytes) | Cache-Control |"
  echo "|---|---|---|---|---|"
  for file in index.html flutter_bootstrap.js flutter.js main.dart.js flutter_service_worker.js \
      version.json manifest.json canvaskit/canvaskit.js canvaskit/canvaskit.wasm \
      assets/AssetManifest.bin.json assets/FontManifest.json; do
    disk="$(stat -c %s "${WEB}/${file}" 2>/dev/null || echo fehlt)"
    headers="$(mktemp)"
    result="$(curl -sS -o /dev/null -D "${headers}" -w '%{http_code} %{size_download}' \
      --max-time 60 "${BASE}/${file}" 2>&1 || echo "Fehler")"
    cache="$(grep -i '^cache-control:' "${headers}" | cut -d' ' -f2- | tr -d '\r' || true)"
    rm -f "${headers}"
    echo "| ${file} | ${disk} | ${result% *} | ${result#* } | ${cache:-–} |"
  done
  echo
  echo "## Über Tailscale (wie das Handy)"
  echo
  dns_name="$(docker compose exec -T tailscale tailscale status --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' \
    2>/dev/null || true)"
  if [[ -n "${dns_name}" ]]; then
    for file in index.html main.dart.js canvaskit/canvaskit.wasm; do
      result="$(docker compose exec -T tailscale wget -q -O /dev/null -S \
        "https://${dns_name}/${file}" 2>&1 | grep -m1 'HTTP/' | tr -d '\r' || echo 'Fehler')"
      echo "- \`${file}\`: ${result:-Fehler}"
    done
  else
    echo "- Tailscale-Adresse nicht ermittelbar"
  fi
  echo
  echo "## Container"
  echo
  echo '```'
  docker compose ps --format 'table {{.Service}}\t{{.Status}}' 2>&1 || true
  for service in api worker tailscale; do
    id="$(docker compose ps -q "${service}" 2>/dev/null || true)"
    [[ -n "${id}" ]] && docker inspect -f "${service}: gestartet {{.State.StartedAt}}, Neustarts {{.RestartCount}}, OOM {{.State.OOMKilled}}" "${id}"
  done
  echo '```'
  echo
  echo "## Speicher"
  echo
  echo '```'
  free -m
  df -h / | tail -1
  echo '```'
  echo
  echo "## API-Protokoll (Fehler, letzte 2 Stunden)"
  echo
  echo '```'
  docker compose logs --since 2h api 2>&1 | grep -iE 'error|exception|traceback|killed' \
    | tail -40 || echo "keine"
  echo '```'
} 2>&1 | mask | tee "${RESULT}"

echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Pruefung Web-App' && git push"
