# Kartenkiste – so kommst du rein

Kartenkiste ist eine private App für unsere Pokémon-Sammlungen: Karten scannen, Wert
verfolgen, Merkliste, versiegelte Produkte. Sie läuft auf einem eigenen Server und ist
**nur über Tailscale** erreichbar (ein privates Netz – niemand sonst kommt an die App).

Du brauchst etwa 10 Minuten.

---

## 1. Tailscale installieren

1. App **„Tailscale“** installieren (App Store bzw. Google Play, kostenlos).
2. Öffnen und mit Google, Apple oder Microsoft anmelden – ein eigener Account, kostenlos.
3. Wenn die App fragt, ob sie ein VPN einrichten darf: **Erlauben**. Tailscale leitet nur
   den Zugriff auf Kartenkiste über das private Netz, dein übriges Internet bleibt normal.

## 2. Freigabe annehmen

Du bekommst von mir einen **Freigabe-Link** (Tailscale „Share“). Auf dem Handy öffnen →
„Accept“. Danach taucht in der Tailscale-App ein Gerät **„kartenkiste“** auf.

Tailscale muss eingeschaltet sein, wenn du Kartenkiste benutzt (in der Tailscale-App oben
der Schalter).

## 3. Kartenkiste öffnen und registrieren

1. Die **Adresse** der App bekommst du von mir (beginnt mit `https://kartenkiste.`).
2. Auf **„Registrieren“** tippen, deinen **Einladungscode** eingeben (von mir, gilt einmal),
   Name, E-Mail und ein Passwort wählen.

## 4. Als App aufs Handy legen

**iPhone:** Adresse in **Safari** öffnen → Teilen-Symbol → **„Zum Home-Bildschirm“**.
Danach startet Kartenkiste wie eine normale App, auch die Kamera funktioniert.

**Android:** entweder
* in **Chrome** öffnen → Menü ⋮ → **„App installieren“**, oder
* die Android-App laden: Adresse + `/kartenkiste.apk` öffnen, Datei installieren
  (einmalig „Installation aus unbekannten Quellen“ für Chrome erlauben).

---

## Kurz erklärt

* **Scannen** (runder Knopf in der Mitte): Karte flach hinlegen, gutes Licht, Foto. Die App
  erkennt Karte, Sprache und Set und zeigt den Preis. Stimmt etwas nicht: **„Andere Karte?“**.
  Wenn du korrigierst, merkt sich die App dein Foto und erkennt die Karte beim nächsten Mal.
* **Slabs** (PSA, BGS, CGC …): einfach scannen – Firma und Note werden vom Etikett gelesen.
  Der Preis richtet sich nach Firma und Note.
* **Suche:** Deutsch oder Englisch („Glurak“ oder „Charizard“), mit Nummer („nachtara 215“)
  oder mit Setkürzel wie auf der Karte („PFL077“, „s6a 095“).
* **Preise:** zuerst Cardmarket (Euro). Wo Cardmarket nichts hat, ein US-Preis von
  PriceCharting, umgerechnet in Euro („US-Preis in €“). Geschätzte Preise sind markiert.
* **Versiegeltes** (Booster, Displays, Top-Trainer-Boxen): unter **Sammlung → „Versiegelt“**,
  Suche auch auf Deutsch („Top-Trainer-Box Prismatische Entwicklungen“).
* **Merkliste:** Herz-Symbol auf einer Karte.
* **Gewinn/Verlust:** Trag den Kaufpreis ein (direkt nach dem Scan oder über „Bearbeiten“). Dann
  zeigt die App, was du bezahlt hast und wie viel du heute im Plus oder Minus bist – gesamt, je
  Ordner und je Karte. Sortieren nach „Höchster Gewinn“ / „Größter Verlust“ geht auch.

Deine Sammlung sieht nur du (und der Admin zur Hilfe). Gespeichert werden keine Fotos, nur
die Merkmale zum Wiedererkennen.

Probleme? Screenshot an mich, mit einem Satz, was du erwartet hast.

---

## Für den Admin (Sebastian)

1. **Gerät teilen:** Tailscale-Admin (login.tailscale.com) → *Machines* → `kartenkiste` →
   ⋯ → **Share…** → Link an den Freund schicken. Er sieht nur dieses Gerät, nicht dein
   übriges Netz.
2. **Einladungscode:** in der App **Mehr → Einladungen → „+ Einladung“**. Der Code ist nur
   einmal sichtbar und gilt einmal.
3. **Android-App bauen** (nach Änderungen an der App):
   `bash deploy/phase5_app.sh --apk` → Download unter `…/kartenkiste.apk`.
4. **Passwort vergessen:** Mehr → Nutzer → ⋮ bei der Person → **„Passwort-Reset-Code“** und weitergeben.
