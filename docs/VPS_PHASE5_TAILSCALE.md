# Phase 5, Schritt 1: Tailscale-Gerät „kartenkiste“ (Container)

Kartenkiste bekommt ein **eigenes Tailscale-Gerät** in einem Docker-Container. Dadurch ist die App unter `https://kartenkiste.<dein-tailnet>.ts.net` erreichbar. Das Tailscale, das direkt auf dem VPS für deine andere App läuft, wird **nicht verändert**. Teilst du später „kartenkiste“ mit Freunden, sehen sie nur diese App.

## Vorher

Das VPS-Gerät muss wieder seinen alten Namen haben (falls noch nicht geschehen):

```bash
tailscale set --hostname=gtcha
```

## Befehle

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase5_tailscale.sh
```

Beim ersten Start erscheint ein **Login-Link**. Öffne ihn am Handy und bestätige mit deinem Tailscale-Konto. Das Skript wartet bis zu 10 Minuten und läuft dann allein weiter.

**Danach im Tailscale-Admin** (<https://login.tailscale.com/admin/machines>) beim Gerät „kartenkiste“ über das Menü **„Disable key expiry“** wählen. Sonst muss es sich nach 180 Tagen neu anmelden.

Am Handy, mit verbundener Tailscale-App, im Browser öffnen:

```
https://kartenkiste.<dein-tailnet>.ts.net/api/v1/health
```

Erwartet wird: `{"status":"ok","version":"0.1.0","database":"ok"}`

Wenn das klappt:

```bash
git add docs/phase5
```

```bash
git commit -m "Phase 5: Tailscale-Container"
```

```bash
git push
```

Hinweis: In der Weiterleitungsliste des VPS-Tailscale steht evtl. noch ein alter Eintrag „kartenkiste“ vom ersten Versuch. Er ist ohne Wirkung, weil das VPS-Gerät wieder anders heißt.
