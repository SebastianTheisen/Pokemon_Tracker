# Phase 5, Schritt 1: Tailscale auf dem VPS

Danach ist die API **nur in deinem Tailnet** per HTTPS erreichbar, unter `https://kartenkiste.<dein-tailnet>.ts.net`. Das braucht später die App. Das iPhone erlaubt die Kamera nur über HTTPS.

## Vorher (einmalig, am Handy)

1. Kostenloses Tailscale-Konto anlegen: <https://login.tailscale.com> (z. B. mit Google- oder Apple-Konto).
2. Die **Tailscale-App** installieren (App Store / Play Store) und mit demselben Konto anmelden.
3. Im Tailscale-Admin unter **DNS** prüfen, dass **MagicDNS** und **HTTPS Certificates** aktiv sind. Fehlt HTTPS, zeigt das Skript einen Link zum Freischalten.

## Befehle auf dem VPS

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase5_tailscale.sh
```

Während des Laufs erscheint beim ersten Mal ein **Login-Link**. Öffne ihn am Handy und bestätige ihn. Erscheint ein zweiter Link zum Freischalten von HTTPS/Serve, bestätige auch diesen. Das Skript wartet und läuft dann allein weiter.

Am Ende steht eine Adresse, die du **am Handy mit verbundener Tailscale-App** im Browser öffnest:

```
https://kartenkiste.<dein-tailnet>.ts.net/api/v1/health
```

Erwartet wird: `{"status":"ok","version":"0.1.0","database":"ok"}`

Wenn das klappt:

```bash
git add docs/phase5
```

```bash
git commit -m "Phase 5: Tailscale auf dem VPS"
```

```bash
git push
```

Hinweis: Der vollständige Tailnet-Name wird nicht ins Repo geschrieben.
