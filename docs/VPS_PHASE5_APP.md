# Phase 5: App bauen und auf dem Handy testen

Das Skript baut die App „Kartenkiste“ auf dem VPS in einem Build-Container:
- die **Web-App (PWA)** für iPhone und Android. Sie wird von der API unter `https://kartenkiste.<dein-tailnet>.ts.net/` ausgeliefert.
- die **Android-APK**, fest auf diese Adresse eingestellt. Download unter `…/kartenkiste.apk`.

Beim **ersten Mal dauert es lange** (ca. 15–30 Minuten): Flutter und das Android-SDK werden geladen. Spätere Builds gehen deutlich schneller. Es werden ca. 15 GB freier Speicher gebraucht, das Skript prüft das.

## Befehle

```bash
cd ~/Pokemon_Tracker/Pokemon_Tracker
```

```bash
git pull
```

```bash
bash deploy/phase5_app.sh
```

Wenn am Ende „Fertig“ erscheint:

```bash
git add docs/phase5
```

```bash
git commit -m "Phase 5: App gebaut"
```

```bash
git push
```

## Am Handy testen (Tailscale-App verbunden)

**iPhone (PWA):**
1. In **Safari** `https://kartenkiste.<dein-tailnet>.ts.net/` öffnen.
2. Teilen-Symbol → **„Zum Home-Bildschirm“**.
3. Die App vom Home-Bildschirm starten und mit deinem Admin-Konto anmelden.

**Android:**
1. `https://kartenkiste.<dein-tailnet>.ts.net/kartenkiste.apk` im Browser öffnen und herunterladen.
2. Installieren. Android fragt einmal, ob der Browser Apps installieren darf → erlauben.
3. Alternativ geht auch auf Android die PWA (Chrome → „Zum Startbildschirm hinzufügen“).

**Bitte durchspielen und Rückmeldung geben (gerne mit Screenshots):**
1. Anmelden, Übersicht wird angezeigt
2. Suche „nachtara 215“ → Karte öffnen → Preise, Zustände, Verlauf, eBay-Link
3. „Sammlung“ → hinzufügen → erscheint in der Sammlung, Wert stimmt
4. Scan-Button (Mitte) → Foto aufnehmen → Ergebnis → „Zur Sammlung hinzufügen“
5. Merkliste: Karte merken, wieder entfernen
6. Mehr → Einladungen → Einladung erzeugen (Code wird angezeigt)
7. Abmelden und wieder anmelden
