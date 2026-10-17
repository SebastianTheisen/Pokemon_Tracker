# Phase 0 auf dem VPS ausführen

Diese Anleitung führt alle Tests aus, die in der Cloud-Umgebung nicht möglich waren:

- Prüfung der Datenquellen TCGdex, pokemontcg.io und Cardmarket. Bei Cardmarket ist es genau eine Anfrage.
- Scanner-Test mit deinen Fotos.
- Docker-Build mit Health-Check, falls Docker installiert ist.

Dauer: ca. 10 Minuten plus Zeit zum Fotografieren.

## 1. Repo auf den VPS holen

Per SSH auf den VPS einloggen und das Repo klonen:

```bash
git clone https://github.com/SebastianTheisen/Pokemon_Tracker.git
cd Pokemon_Tracker
```

Wenn das Repo privat ist, fragt GitHub nach Zugangsdaten. Als Passwort brauchst du ein **Personal Access Token**: GitHub → Settings → Developer settings → Fine-grained tokens, nur für dieses Repo, Recht „Contents: Read“.

Ist das Repo schon geklont, holst du nur den neuesten Stand:

```bash
cd Pokemon_Tracker && git pull
```

## 2. Testfotos vorbereiten (für den Scanner-Test)

Ziel: **ca. 20 Fotos** mit dem Handy, so wie man später scannen würde. Bitte gemischt:

| Anzahl | Was |
|---|---|
| 6–8 | Deutsche Karten, verschiedene Seltenheiten (normal, Holo, Full Art/Alternate Art) |
| 4–6 | Englische Karten |
| 1–2 | Japanische Karte(n) |
| 2–3 | Karte in Hülle (Sleeve / Toploader) |
| 1–2 | Gegradete Karte (Slab), falls vorhanden |
| 2–3 | „Schwierige“ Fälle: schräg, wenig Licht, unruhiger Hintergrund |

Tipps:
- Die Karte sollte etwa die Hälfte des Bildes ausfüllen.
- HEIC vom iPhone geht direkt, JPG ebenso.
- Die Dateinamen sind egal, z. B. `01.jpg`, `02.heic`.

Die Fotos kommen in den Ordner `scanner_testset/` im Repo. Der Ordner wird **nicht** committet. Hochladen geht z. B. von deinem Rechner aus:

```bash
scp ~/Bilder/karten/* benutzer@dein-vps:~/Pokemon_Tracker/scanner_testset/
```

### Optional, aber sehr hilfreich: Soll-Werte

Damit der Bericht die Trefferquote ausrechnet, lege `scanner_testset/soll.csv` an. Trennzeichen ist das Semikolon, die Nummer schreibst du so, wie sie auf der Karte steht:

```csv
datei;name;nummer
01.jpg;Nachtara VMAX;215/203
02.heic;Glurak;039/165
```

Eine Vorlage liegt in `docs/spikes/soll_vorlage.csv`.

## 3. Alles ausführen

```bash
bash deploy/phase0_vps.sh
```

Das Skript erledigt Folgendes:
- Es installiert fehlende Pakete (`git`, `curl`, `libglib2.0-0`, fragt dafür nach dem `sudo`-Passwort).
- Es installiert `uv` und Python 3.12, beides nur für deinen Benutzer.
- Es führt Lint, Typprüfung und Tests aus.
- Es führt die Spikes aus und schreibt die Berichte nach `docs/spikes/`.
- Es testet den Docker-Build, falls Docker vorhanden ist.

## 4. Ergebnisse zurückschicken

Am Ende steht die Zusammenfassung im Terminal. Die Ergebnisse liegen hier:

```
docs/spikes/zusammenfassung.md
docs/spikes/datenquellen.md
docs/spikes/scanner.md
docs/spikes/scanner_debug/       # erkannte Kontur + entzerrte Karte pro Foto
docs/spikes_ergebnisse.tar.gz    # alles zusammen
```

Zurück an mich, eine Variante genügt:
- **Einfach:** Den Inhalt von `zusammenfassung.md`, `datenquellen.md` und `scanner.md` in den Chat kopieren.
- **Mit Bildern:** `docs/spikes_ergebnisse.tar.gz` herunterladen (`scp benutzer@dein-vps:~/Pokemon_Tracker/docs/spikes_ergebnisse.tar.gz .`) und hier hochladen.

Die Debug-Bilder enthalten deine Fotos. Committe sie deshalb nicht, wenn das Repo öffentlich ist.

## Was danach passiert

Mit den Ergebnissen werte ich jeden Spike aus (Go/No-Go) und trage das in `UMSETZUNGSPLAN.md` ein. Erst dann beginnt Phase 1.
