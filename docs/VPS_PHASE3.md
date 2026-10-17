# Phase 3 auf dem VPS ausführen

Das Skript macht Folgendes:
1. Es baut das Backend und den Preis-Worker neu. Die Datenbank-Migration für die Sammlung (Ordner, Positionen, Merkliste, Produkte, Tageswerte) läuft beim Start automatisch.
2. Es legt eine **Probe-Sammlung** in deinem Admin-Konto an und bewertet sie mit echten Preisen von TCGdex:
   - 2× Nachtara VMAX in NM
   - Glurak (Grundset) in LP
   - Mewtu ex als PSA 10
   - ein Display
3. Es zeigt Werte, Aufteilung und CSV-Export an.
4. Es macht die Probe danach **vollständig rückgängig**. In deiner Sammlung bleibt nichts zurück, das Skript prüft das auch.
5. Es testet, dass ohne Anmeldung alle neuen Endpunkte gesperrt sind.
6. Es schreibt alles nach `docs/phase3/ergebnis.md`.

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
bash deploy/phase3_vps.sh
```

Wenn am Ende „Fertig“ erscheint:

```bash
git add docs/phase3
```

```bash
git commit -m "Phase 3: Ergebnisse vom VPS"
```

```bash
git push
```
