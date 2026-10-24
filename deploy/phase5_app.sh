#!/usr/bin/env bash
# Phase 5: App „Kartenkiste“ auf dem VPS bauen und ausliefern.
#   1. Build-Container (Flutter + Android-SDK) bauen – beim ersten Mal ca. 10–20 min
#   2. Web-App (PWA) bauen → wird von der API unter https://kartenkiste.<tailnet>.ts.net/ ausgeliefert
#   3. Android-APK bauen (nur mit --apk; fest auf die Tailscale-Adresse eingestellt) →
#      Download unter …/kartenkiste.apk. Ohne --apk bleibt die zuletzt gebaute APK erhalten.
#   4. API neu starten und prüfen
# Ergebnis: docs/phase5/app_build.md
#
#   bash deploy/phase5_app.sh          # nur Web-App; übersprungen, wenn sich app/ nicht geändert hat
#   bash deploy/phase5_app.sh --apk    # zusätzlich Android-APK (dauert deutlich länger)
#   bash deploy/phase5_app.sh --force  # Web-App auf jeden Fall neu bauen
set -euo pipefail
build_apk=false
force=false
for arg in "$@"; do
  case "${arg}" in
    --apk) build_apk=true ;;
    --force) force=true ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/phase5"
RESULT="${OUT_DIR}/app_build.md"
cd "${REPO_ROOT}"
mkdir -p "${OUT_DIR}"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m[Fehler]\033[0m %s\n' "$*"; exit 1; }
mask() { sed -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g'; }

[[ -f .env ]] || fail ".env fehlt – zuerst Phase 1 ausführen."
free_gb="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"
[[ "${free_gb}" -ge 15 ]] || fail "Zu wenig Speicherplatz (${free_gb} GB frei, nötig ca. 15 GB)."

step "1/5 Adresse im Tailnet ermitteln"
dns_name="$(docker compose exec -T tailscale tailscale status --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')" \
  || fail "Tailscale-Container läuft nicht – zuerst: bash deploy/phase5_tailscale.sh"
api_url="https://${dns_name}"
echo "App-Adresse: ${api_url}" | mask

step "2/5 Build-Container bauen (beim ersten Mal dauert das)"
build_log="${OUT_DIR}/app_builder_build.log"
if ! BUILDKIT_PROGRESS=plain docker compose --profile build build app-builder > "${build_log}" 2>&1; then
  tail -40 "${build_log}"
  fail "Build-Container fehlgeschlagen (Protokoll: ${build_log})."
fi
# Erst ganz lesen, dann die erste Zeile nehmen: „| head -1“ beendet die Pipe vorzeitig
# (SIGPIPE) – mit pipefail bricht set -e das Skript dann ohne Meldung ab.
flutter_version="$(docker compose --profile build run --rm -T app-builder flutter --version \
  2>&1 || true)"
echo "${flutter_version%%$'\n'*}"

app_log="${OUT_DIR}/app_flutter_build.log"
# Stand des Ordners app/ (Git-Baum): unverändert → Web-App nicht neu bauen.
app_rev="$(git rev-parse HEAD:app 2>/dev/null || echo unbekannt)"
stamp="app/build/web/.app-revision"
start=$(date +%s)
if ! ${build_apk} && ! ${force} && [[ -f app/build/web/index.html && -f "${stamp}" ]] \
    && [[ "$(cat "${stamp}")" == "${app_rev}" ]]; then
  step "3/5 Web-App unverändert – kein neuer Build (erzwingen mit --force)"
else
  if ${build_apk}; then
    step "3/5 Web-App und Android-APK bauen"
  else
    step "3/5 Web-App bauen (APK nur mit --apk)"
  fi
  # „flutter build web“ leert build/web – die vorhandene APK vorher sichern.
  kept_apk="$(mktemp)"
  if [[ -f app/build/web/kartenkiste.apk ]]; then cp app/build/web/kartenkiste.apk "${kept_apk}"; fi
  apk_commands=""
  if ${build_apk}; then
    apk_commands="flutter build apk --release --dart-define=API_BASE_URL=${api_url}
      cp build/app/outputs/flutter-apk/app-release.apk build/web/kartenkiste.apk"
  fi
  # --no-wasm-dry-run: kein zusätzlicher WebAssembly-Probelauf (halbiert die Bauzeit).
  if ! docker compose --profile build run --rm -T app-builder sh -ec "
      flutter pub get
      flutter build web --release --no-web-resources-cdn --no-wasm-dry-run
      ${apk_commands}
    " > "${app_log}" 2>&1; then
    tail -60 "${app_log}" | mask
    rm -f "${kept_apk}"
    fail "App-Build fehlgeschlagen (Protokoll: ${app_log})."
  fi
  if ! ${build_apk} && [[ -s "${kept_apk}" ]]; then
    cp "${kept_apk}" app/build/web/kartenkiste.apk
  fi
  rm -f "${kept_apk}"
  echo "${app_rev}" > "${stamp}"
fi
duration=$(( $(date +%s) - start ))
[[ -f "${app_log}" ]] && sed -i -E 's/\.[a-z0-9-]+\.ts\.net/.<tailnet>.ts.net/g' "${app_log}"
apk_size="$(du -h app/build/web/kartenkiste.apk 2>/dev/null | cut -f1 || true)"
apk_size="${apk_size:-keine}"
${build_apk} || apk_size="${apk_size} (nicht neu gebaut)"
web_size="$(du -sh --exclude=kartenkiste.apk app/build/web | cut -f1)"
echo "Fertig in ${duration} s – APK ${apk_size}, Web ${web_size}"

step "4/5 Backend neu bauen und starten (liefert die Web-App aus)"
# --build: Das Backend-Image muss den aktuellen Code enthalten. Neu gestartet werden api und
# worker nur, wenn sich das Image geändert hat – die Web-App liegt in einem eingebundenen
# Ordner und wird ohne Neustart ausgeliefert (laufender Bild-Import wird nicht unterbrochen).
docker compose up -d --build api worker
health="keine Antwort"
for _ in $(seq 1 60); do
  if health="$(curl -fsS http://127.0.0.1:8000/api/v1/health 2>/dev/null)"; then break; fi
  sleep 2
done
[[ "${health}" == *'"database":"ok"'* ]] || fail "API nicht gesund: ${health}"

step "5/5 Prüfen"
index_check="$(curl -fsS http://127.0.0.1:8000/ | grep -o '<title>[^<]*</title>' || echo 'fehlt')"
deep_link="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/card/irgendwas)"
manifest="$(curl -fsS http://127.0.0.1:8000/manifest.json | python3 -c 'import json,sys; m=json.load(sys.stdin); print(m["name"], m["display"])' || echo 'fehlt')"
apk_check="$(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:8000/kartenkiste.apk)"
echo "Startseite: ${index_check} · Deep-Link: ${deep_link} · Manifest: ${manifest} · APK: ${apk_check}"
if [[ "${index_check}" == "fehlt" ]]; then
  docker compose logs --tail 40 api | grep -iE "web|error" || true
  fail "Die API liefert die Web-App nicht aus (siehe Protokoll oben)."
fi

{
  echo "# Phase 5 – App gebaut und ausgeliefert"
  echo
  echo "- Datum: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Git-Stand: $(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  echo "- ${flutter_version}"
  echo "- Build-Dauer (Web + APK): ${duration} s"
  echo "- APK: ${apk_size} · Web-App: ${web_size}"
  echo "- Adresse: \`${api_url}\`" | mask
  echo "- Startseite: \`${index_check}\` · Deep-Link-Status: ${deep_link} (Erwartung 200)"
  echo "- Manifest: ${manifest}"
  echo "- APK-Download (Status, Bytes): ${apk_check}"
  echo "- Health: \`${health}\`"
} > "${RESULT}"

step "Fertig"
echo "Am Handy (Tailscale verbunden) öffnen:"
echo "  App (iPhone/Android):  ${api_url}/"
echo "  APK (nur Android):     ${api_url}/kartenkiste.apk"
echo
echo "Ergebnis zurückschicken:"
echo "  git add docs/phase5 && git commit -m 'Phase 5: App gebaut' && git push"
