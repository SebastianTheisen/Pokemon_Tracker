# Phase 4 auf dem VPS ausführen

Das Skript macht Folgendes:
1. Es baut Backend und Worker neu. Dabei werden die Texterkennungs-Modelle geladen, das koreanische Modell wird heruntergeladen. Die Datenbank-Migration für den Scanner (Scan-Protokoll, eigene Referenzbilder) läuft beim Start automatisch.
2. Es prüft, ob beide OCR-Modelle im Container funktionieren und das neue Scanner-Volume beschreibbar ist.
3. Es misst den Scanner mit den 7 Testfotos aus `scanner_testset/`, **zweimal**:
   - **kalt:** Die Katalogbilder werden dabei erstmals von TCGdex geladen.
   - **warm:** mit Cache, so wie im Alltag.

   Gespeichert wird dabei nichts, das Skript prüft das auch. Nur der Merkmal-Cache der Katalogbilder bleibt (gewollt).
4. Es prüft, dass ohne Anmeldung alle Scan-Endpunkte gesperrt sind und zu große Uploads sofort abgelehnt werden.
5. Es schreibt alles nach `docs/phase4/` (`ergebnis.md`, `scan_eval_kalt.md`, `scan_eval_warm.md`, `docker_build.log`).

Es fragt nichts ab und dauert etwa 5–10 Minuten (der Build lädt die Scanner-Bibliotheken).

## Befehle

Nacheinander eingeben:

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase4_vps.sh
```

Wenn am Ende „Fertig“ erscheint:

```bash
git add docs/phase4
```

```bash
git commit -m "Phase 4: Ergebnisse vom VPS"
```

```bash
git push
```
