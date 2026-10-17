# Phase 1 auf dem VPS ausführen

Das Skript macht Folgendes:
1. Es legt beim ersten Mal eine `.env` mit sicheren Zufallswerten an (Datenbank-Passwort, JWT-Schlüssel).
2. Es baut das Backend und startet es (PostgreSQL + API, Migrationen laufen automatisch).
3. Es fragt nach E-Mail und Namen für den **ersten Admin**, dann zweimal nach dessen Passwort (mindestens 10 Zeichen).
4. Es importiert den Katalog aus TCGdex in allen 6 Sprachen. Beim ersten Mal dauert das einige Minuten.
5. Es zählt den Katalog und testet mehrere Suchen.
6. Es schreibt alles nach `docs/phase1/ergebnis.md`.

Beim ersten Lauf entfernt das Skript das leere Test-Datenbank-Volume aus Phase 0. Dort liegen keine Daten. Es ist nötig, weil die Datenbank jetzt ein neues, sicheres Passwort bekommt.

## Befehle

Nacheinander eingeben:

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase1_vps.sh
```

Wenn am Ende „Fertig“ erscheint:

```bash
git add docs/phase1
```

```bash
git commit -m "Phase 1: Ergebnisse vom VPS"
```

```bash
git push
```

Beim `git push` fragt Git nach Benutzername (`SebastianTheisen`) und Token (`github_pat_…`), falls du den Credential-Helper nicht eingerichtet hast.

## Gut zu wissen

- **Die `.env` enthält Geheimnisse.** Sie bleibt nur auf dem VPS und wird nicht committet, weil sie in `.gitignore` steht.
- **Die API läuft danach dauerhaft.** Sie ist nur lokal auf dem VPS erreichbar (`127.0.0.1:8000`). Der Zugang für Freunde über Tailscale kommt in Phase 6.
- **Weitere Einladungscodes erzeugst du so:**

  ```bash
  cd ~/Pokemon_Tracker/Pokemon_Tracker
  ```

  ```bash
  docker compose exec api python -m app.cli create-invite --note "für Max"
  ```

- **Das Skript darf mehrfach laufen.** Ein vorhandener Admin wird übersprungen, und der Katalog wird nur ergänzt.
