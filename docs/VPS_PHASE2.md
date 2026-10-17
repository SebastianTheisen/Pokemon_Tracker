# Phase 2 auf dem VPS ausführen

Das Skript macht Folgendes:
1. Es baut das Backend neu und startet **zusätzlich den Preis-Worker**. Der Worker aktualisiert täglich um 12:30 Uhr die Preise der angesehenen Karten.
2. Es führt die neue Datenbank-Migration aus (Preis-Historie, Einstellungen). Das passiert automatisch beim Start.
3. Es holt für sieben Testkarten die **echten Preise von TCGdex**: Deutsch, Englisch, Japanisch und Chinesisch.
4. Es zeigt, was in der Preis-Historie gespeichert wurde.
5. Es schreibt alles nach `docs/phase2/ergebnis.md`.

Es fragt nichts ab und dauert etwa 1–2 Minuten.

## Befehle

Nacheinander eingeben:

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase2_vps.sh
```

Wenn am Ende „Fertig“ erscheint:

```bash
git add docs/phase2
```

```bash
git commit -m "Phase 2: Ergebnisse vom VPS"
```

```bash
git push
```

## Gut zu wissen

- **Preise einer bestimmten Karte ansehen:**

  ```bash
  docker compose exec api python -m app.cli prices "nachtara 215" --language de
  ```

- **Tägliche Preisrunde sofort auslösen:**

  ```bash
  docker compose exec api python -m app.cli refresh-prices
  ```

- **Worker-Protokoll ansehen:**

  ```bash
  docker compose logs --tail 20 worker
  ```
