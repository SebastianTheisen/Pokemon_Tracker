# Umsetzungsplan: Pokémon-Karten-Tracker (Arbeitstitel „Pokemon Tracker“)

Eine private Sammel-App im Stil von SCNDX: Pokémon-Karten scannen, Sammlung verwalten, belegte Marktpreise sehen. Sie ist für den Freundeskreis gedacht und wird nicht veröffentlicht.

Stand: 17.10.2026 · Status: **Phase 5 (Flutter-App „Kartenkiste“) in Arbeit – App fertig, Build auf dem VPS und Gerätetest offen**

---

## 0. Projektstatus (wird laufend gepflegt)

| Phase | Status | Notiz |
|---|---|---|
| 0 – Spikes und Fundament | ✅ erledigt | Alle Spikes ausgewertet, alle Entscheidungen getroffen (Ergebnis unten) |
| 1 – Backend-Kern | ✅ erledigt | 65.561 Karten importiert, Abnahme-Suchen ✅, Nachtest 0 Fehler, 111 Tests (96 % Coverage) |
| 2 – Preise | ✅ erledigt | Echte Preise mit Beleg (DE/EN/JA/ZH), Worker läuft, NM-Basis = Median, 163 Tests (95 % Coverage) |
| 3 – Sammlung, Merkliste, Dashboard | ✅ erledigt | VPS-Probe mit echten Preisen = Handrechnung (4.894,67 €), Zugriffsschutz ✅, 204 Tests (95 % Coverage) |
| 4 – Scanner | ✅ erledigt | VPS-Lauf ✅: Top-1 5/6, 0× sicher-aber-falsch, Ø 2,7 s (max 4,6 s). Latenz-Tuning und Abnahme 85 % → Phase 7. Binder-Scan als Beta; Abnahme Top-1 ≥ 85 % wartet auf weitere Testfotos |
| 5 – Flutter-App | 🟡 in Arbeit | App „Kartenkiste“; Tailscale vorgezogen (eigenes Gerät im Container); APK-Build per Docker auf dem VPS |
| 6 – Deployment und Härtung | ⚪ offen | |
| 7 – Nachbesserung | ⚪ offen | |

Legende: ⚪ offen · 🟡 in Arbeit · 🔴 blockiert · ✅ erledigt

### Phase 0 – Aufgaben

- [x] Repo-Grundgerüst: `backend/` mit `pyproject.toml` (uv), FastAPI-App-Factory, Konfiguration (`pydantic-settings`, Präfix `PT_`), structlog-Logging, Health-Endpoint `GET /api/v1/health`
- [x] Qualitäts-Tooling: ruff (Lint + Format), mypy `--strict`, pytest + pytest-asyncio + Coverage. Lokal alles grün (2 Tests, 97 % Coverage)
- [x] CI: `.github/workflows/backend.yml` (ruff, mypy, pytest)
- [x] pre-commit-Konfiguration, `.gitignore`, `.env.example`
- [x] `Dockerfile` (Backend) und `docker-compose.yml` (Postgres + API)
- [x] Spike-Skript Datenquellen: `backend/scripts/spike_datasources.py` (TCGdex-Sprachabdeckung und Felder, pokemontcg.io, eine einzelne Cardmarket-Anfrage)
- [x] Spike-Skript Scanner: `backend/scripts/spike_scanner.py` (Kartenerkennung, Entzerrung, RapidOCR, Name/Nummer, Trefferquote gegen `soll.csv`, Debug-Bilder). Rauchtest mit synthetischem Kartenfoto grün: Karte gefunden, Name und Nummer korrekt, ca. 330 ms
- [x] VPS-Skript `deploy/phase0_vps.sh` + Anleitung `docs/VPS_PHASE0.md`. Hier einmal komplett durchgelaufen (Lint/Typen/Tests grün, Berichte erzeugt)
- [x] Testsatz: 7 Fotos des Nutzers liegen fest im Repo unter `scanner_testset/` (mit `soll.csv` und Beschreibung)
- [x] Spike Scanner mit echten Fotos ausgeführt und ausgewertet → [`docs/spikes/scanner_auswertung.md`](docs/spikes/scanner_auswertung.md). Ergebnis: **Go mit Anpassung.** Konturerkennung allein reicht nicht (2/7 richtige Ausschnitte). Die Nummer per OCR ist sprachunabhängig gut lesbar (3 von 4 sichtbaren Fällen). Slab-Labels sind komplett lesbar. Japanische Namen sind mit dem Standardmodell nicht lesbar
- [x] Entscheidung Nutzer: angepasste Scanner-Strategie **inkl. JP/KO-OCR** freigegeben → Abschnitt 5.6 geändert
- [x] Scanner-Spike Lauf 2 mit RapidOCR 3 / PP-OCRv6: Name im Text 4/7 (6/7 ohne Logo-Zusatz), Nummer 5/7, in jedem Foto mindestens ein starkes Merkmal
- [x] VPS-Lauf 1 (Ubuntu 20.04, 6 CPU, 11 GB RAM): Tests grün, Scanner reproduziert. Auswertung Datenquellen: [`docs/spikes/datenquellen_auswertung.md`](docs/spikes/datenquellen_auswertung.md)
  - **TCGdex: Go.** Alle Sprachen vorhanden (de 155, en 220, ja 186, ko 95, zh-tw 98, zh-cn 57 Sets). Cardmarket-Preise (avg/low/trend/avg1/7/30, `idProduct` für den Beleglink) und TCGplayer-Preise sind enthalten
  - **pokemontcg.io:** HTTP 500, wird nicht gebraucht → Vorschlag: streichen
  - **Cardmarket direkt:** schon die erste Anfrage wird von Cloudflare gesperrt (403 „Just a moment“). Ohne Umgehung nicht abrufbar
  - **Docker:** fehlgeschlagen. Ursache gefunden und lokal nachgestellt (`README.md` fehlte im Image), korrigiert
  - **KO-Modell:** Der Test in Lauf 1 war wegen eines Testfehlers nicht aussagekräftig (Modell wird erst bei erkanntem Text geladen). Korrigiert, wird in Lauf 2 wiederholt
- [x] Bildabgleich (SIFT + RANSAC) offline geprüft: gleiche Karte auf verschiedenen Fotos 184–192 Übereinstimmungen, andere Karten ≤ 20, ca. 60 ms pro Vergleich. Spike-Skript gegen TCGdex-Katalog geschrieben (`backend/scripts/spike_image_match.py`), offline mit simuliertem TCGdex getestet
- [x] VPS-Lauf 2 ausgewertet → [`datenquellen_auswertung.md`](docs/spikes/datenquellen_auswertung.md) (Abschnitt Lauf 2), [`bildabgleich_auswertung.md`](docs/spikes/bildabgleich_auswertung.md)
  - **Docker:** ✅ Build und Health-Check ok
  - **KO-OCR-Modell:** ✅ Download und Start ok
  - **Bildabgleich:** Top-1 4/7. Alle Treffer mit klarem Abstand (Score 214–370 vs. ≤ 219). Alle Fehlschläge liegen an **Katalog-Lücken** (fehlende Bilder oder Karten), nicht am Verfahren
  - **Asiatische Karten:** JP-Preise vorhanden, ZH teilweise. Katalogbilder fehlen oft
  - **pokemontcg.io:** diesmal erreichbar, aber Preise vom 18.11.2025 (veraltet)
- [x] Entscheidung Nutzer (17.10.2026): Preise aus TCGdex + markierte Schätzung **und** Plug-in-Schnittstelle für weitere Quellen. Kein eigener Cardmarket-Abruf → Abschnitt 5.3 angepasst, Einstellung `PT_EXTRA_PRICE_PROVIDERS` statt `PT_CARDMARKET_LISTING_ENABLED`
- [x] Entscheidung Nutzer: pokemontcg.io bleibt als **Reserve** (nur englische Karten, nur wenn TCGdex ausfällt; Preise mit ihrem eigenen, oft alten Datum) → 5.1
- [x] Entscheidung Nutzer: eigene Referenzbilder aus bestätigten Scans, **pro Nutzer** → 4, 5.6
- [x] Entscheidung Nutzer: fehlende Karten selbst anlegen, **für alle sichtbar**, Admin kann bearbeiten/löschen → 4, 5.1
- [x] Abschluss Phase 0 (Ergebnis siehe unten)

### Phase 0 – Ergebnis (Go/No-Go)

| Spike | Ergebnis | Kernaussage |
|---|---|---|
| Fundament (Repo, CI, Tests, Docker) | ✅ Go | Docker-Build + Health-Check auf dem VPS ok |
| Datenquelle TCGdex | ✅ Go | Alle Sprachen, aktuelle Cardmarket-Preise mit Datum + Produkt-ID; Lücken bei Bildern asiatischer Karten |
| pokemontcg.io | ⚠️ Reserve | Preise ~11 Monate alt |
| Cardmarket direkt | ❌ No-Go | Cloudflare-Sperre → Preisstrategie 5.3 (TCGdex + Schätzung + Plug-ins) |
| Scanner-OCR (PP-OCRv6 + KO) | ✅ Go | Nummer in 5/7, Name in 6/7 Fotos; Slab-Labels komplett lesbar; KO-Modell lädt |
| Bildabgleich (SIFT) | ✅ Go | Sicher, wenn Katalogbild vorhanden (Score 214–370 vs. ≤ 219); Lücken → eigene Referenzbilder + Karten anlegen |
| Tailscale | ⏭️ verschoben | Test in Phase 6 (laut Absprache) |

### Phase 1 – Aufgaben

Entscheidungen (17.10.2026): Passwort-Reset **durch den Admin** (Einmal-Code, kein Mailserver); Katalog-Import in **allen 6 Sprachen**.

- [x] Datenbank: Modelle `users`, `invite_codes`, `refresh_tokens`, `password_reset_tokens`, `audit_log`, `card_sets`, `cards` + Alembic-Migration `0001_initial` (inkl. `pg_trgm`). Hoch-/Runtermigrieren getestet, `alembic check` ohne Abweichungen. Tabellen für Sammlung/Preise folgen in ihren Phasen
- [x] Sicherheit (`app/core/security.py`): Argon2id, JWT-Access-Tokens (15 min, HS256), Refresh-Tokens/Codes nur als SHA-256-Hash, gut abtippbare Codes ohne Verwechslungszeichen
- [x] Auth (`/auth/register|login|refresh|logout|reset-password`): Registrierung nur mit Einladungscode (einmalig, mit Ablauf, gegen Doppelnutzung gesperrt), Login ohne Hinweis ob E-Mail existiert (gleiche Meldung + Rechenzeit), Rate-Limit nach Fehlversuchen (429 + Retry-After), Refresh-Rotation mit **Diebstahlerkennung** (Wiederverwendung sperrt die ganze Sitzungsfamilie)
- [x] Eigenes Konto (`/me`, `/me/password`, `/me/sessions`): Profil, Passwortwechsel (beendet alle Sitzungen), Sitzungen ansehen/beenden
- [x] Admin (`/admin/users|invites`, `/admin/users/{id}/password-reset`): Nutzer sperren/entsperren, Rolle ändern (wirkt sofort), Einladungen erzeugen/auflisten/widerrufen, Reset-Code erzeugen. Schutz: keine Selbstsperre, letzter Admin bleibt. Alles im Audit-Log
- [x] Mandantentrennung: Sperren/Rollen wirken ohne neuen Login (Nutzer wird pro Anfrage frisch geladen); fremde Objekte → 404; Tests für alle Admin-Endpunkte (403/401) und IDOR (fremde Sitzung)
- [x] Katalog: TCGdex-Client, Import aller Sets/Karten je Sprache (parallel abrufen, je Set speichern, inkrementell, Fehler je Set isoliert, eigene Karten unangetastet)
- [x] Suche (`/cards/search`, `/cards/{id}`, `/sets`): Name + Nummer zerlegen („nachtara 215“), tippfehlertolerant (pg_trgm), DE/EN über gemeinsame TCGdex-ID verknüpft („umbreon 215“ findet „Nachtara VMAX“), Nummer allein, Sprachfilter
- [x] CLI (`python -m app.cli`): `create-admin`, `create-invite`, `sync-catalog`, `search`
- [x] Docker: Migrationen beim Start; CI mit PostgreSQL-Service
- [x] Härtung nach Selbst-Review: App startet in Produktion nicht mit Platzhalter- oder zu kurzem JWT-Schlüssel; Login-Limiter räumt alte Einträge auf (kein Speicherleck)
- [x] Qualität: ruff, mypy strict, **109 Tests grün, 96 % Coverage** (lokal gegen PostgreSQL 16)
- [x] VPS-Lauf ausgewertet ([`docs/phase1/ergebnis.md`](docs/phase1/ergebnis.md)): Backend gesund, Admin angelegt, **65.561 Karten in ~1 Minute importiert**

  | Sprache | Sets | Karten | mit Bild |
  |---|---|---|---|
  | de | 155 | 20.233 | 14.860 (73 %) |
  | en | 220 | 23.770 | 21.990 (93 %) |
  | ja | 181 von 186 | 13.006 | 3.882 (30 %) |
  | zh-tw | 98 | 7.436 | 2.146 (29 %) |
  | zh-cn | 57 | 877 | 0 |
  | ko | 91 von 95 | 239 | 0 |

  - **Suche ✅:** „nachtara 215“ → Nachtara VMAX · Drachenwandel · 215 (Abnahme erfüllt); „umbreon 215“ und Tippfehler „NACHTRA 215“ ebenso; „Team Rockets Mewtu ex 231“ ✅; „ルギアV 110“ und „ブラッキーex 217“ finden die Karte zusätzlich auf Chinesisch (gemeinsame Set-IDs)
  - **„鲤鱼王“ (Karpador, ZH):** keine Treffer – die Karte fehlt in TCGdex zh-cn (bekannte Katalog-Lücke → „Karten selbst anlegen“)
  - **9 Fehler:** Sets mit „+“ in der ID (`SM1+` … `SM5+`, JA/KO) → 404, weil die ID nicht URL-kodiert war. **Behoben** (Set-ID wird kodiert), Test mit simuliertem Server ergänzt; Nachtest auf dem VPS offen
  - **Protokoll:** jede HTTP-Anfrage wurde mitgeloggt und Farbcodes landeten in der Datei → httpx-Logs auf WARNING, Farben nur im Terminal. **Behoben**
  - **Erkenntnis für den Scanner:** KO/ZH-CN haben keine Katalogbilder, JA/ZH-TW nur ~30 % → die beschlossenen eigenen Referenzbilder sind für asiatische Karten zentral
- [x] Nachtest auf dem VPS: Import JA/KO mit **0 Fehlern**, die „+“-Sets sind da (JA 47, KO 49 Karten)
- [x] Dabei gefunden und behoben: Viele JA/KO-Sets wurden bei jedem Lauf neu geladen (TCGdex meldet mehr Karten, als es liefert). Neu geladen wird jetzt nur, wenn sich die gemeldete Kartenzahl seit dem letzten Import ändert. Test ergänzt (111 Tests)
- [x] **Abnahme Phase 1** ✅

**Nicht prüfbar in der Cloud-Umgebung:** echter TCGdex-Import (Host gesperrt) und Docker-Build (GHCR gesperrt) – beides übernimmt der VPS-Lauf.

### Phase 2 – Aufgaben

Entscheidungen/Annahmen (17.10.2026):
- **Beleglink Cardmarket:** direkt per Produkt-ID (`…/Products?idProduct=…`), ohne ID die Cardmarket-Suche – beide vom Nutzer im Browser geprüft
- **Frische:** beim Ansehen neu holen, wenn älter als 12 h; nach einem Fehler frühestens nach 60 min erneut
- **Tägliche Runde um 12:30 Uhr (Europe/Berlin)** statt nachts – TCGdex aktualisiert vormittags (UTC), eine Runde um 4 Uhr hätte nur den Vortagsstand
- **Bis Phase 3** umfasst die tägliche Runde die in den letzten 30 Tagen angesehenen Karten; ab Phase 3 zusätzlich Sammlung und Merkliste
- **Eigenpreis** wird mit der Sammlungsposition gespeichert (Phase 3); Phase 2 liefert die Logik der Zustandspreise

- [x] Datenbank: Migration `0002_pricing` – `price_points` (Historie, nie überschrieben, doppelte Stände verworfen), `price_checks` (Frische, Fehler, „angesehen“), `user_settings`
- [x] Preisquellen-Schnittstelle (`app/providers/pricing`): `PriceProvider`-Protokoll, `PriceQuote` mit Wert, Datum, Beleglink; „Kein Beleg, kein Preis“
- [x] TCGdex-Preise: Cardmarket (Trend, günstigstes Angebot, Ø, Ø 1/7/30 Tage; Normal + Reverse Holo) und TCGplayer (USD); 0/leer = kein Preis; getestet mit der echten Spike-Antwort
- [x] Plug-ins über `PT_EXTRA_PRICE_PROVIDERS` (fehlerhafte Einträge brechen den Start ab); externe Quellen können sich nicht als Cardmarket ausgeben
- [x] Absicherung: Zeitlimit je Abruf, Fehler isoliert, „Sicherung“ pausiert eine Quelle nach 3 Fehlern in Folge für 60 min; „Karte unbekannt“ zählt nicht als Ausfall
- [x] Anzeige: aktuelle Werte je Quelle/Variante; Zustandspreise MT–PO = Trend × Faktor (als **Schätzung** markiert, mit Basis und Faktor); externer belegter Zustandspreis hat Vorrang; ohne belegten Preis keine Schätzung
- [x] Preisverlauf: ein Punkt je Tag, Tiefst-/Höchstwert seit Beobachtungsbeginn
- [x] Einstellungen: eigene Zustandsfaktoren (0 < f ≤ 3), Zurücksetzen, Standardsprache – je Nutzer getrennt
- [x] API: `GET /cards/{id}/prices`, `GET /cards/{id}/price-history`, `GET/PATCH /me/settings`, `GET /admin/price-sources`
- [x] Worker (`python -m app.worker`, eigener Docker-Dienst) mit Sommer-/Winterzeit-sicherer Planung; CLI `refresh-prices` und `prices "<suche>"`
- [x] Qualität: ruff, mypy strict, **156 Tests grün, 95 % Coverage**; dabei gefunden und behoben: `idProduct: true` hätte einen kaputten Link erzeugt; ein Test prüfte den Fehlerfall nicht wirklich
- [x] VPS-Lauf ausgewertet ([`docs/phase2/ergebnis.md`](docs/phase2/ergebnis.md)): Health ok, Migration `0002_pricing`, Worker läuft (nächste Runde 18.10. 10:30 UTC = 12:30 Uhr). Echte Preise für alle 7 Karten inkl. **JA und ZH-TW** (Cardmarket), Beleglinks per Produkt-ID, TCGplayer für DE/EN-Karten. 65 Preiswerte gespeichert
- [x] Abnahmekriterien erfüllt: jeder Preis mit Datum und Link, kein erfundener Preis, Schätzungen markiert
- [x] **Gefunden:** Trend als NM-Basis ist anfällig (Glurak Grundset: Trend 58,10 € < günstigstes Angebot 95 €). **Entscheidung Nutzer:** Median aus Trend, Ø 7, Ø 30 → umgesetzt, mit den echten Glurak-Werten getestet (NM 423,40 € statt 58,10 €), Basis + Wert werden angezeigt. 163 Tests grün
- [x] Nachtest auf dem VPS: Glurak Grundset NM = 423,40 € (median(trend, avg7, avg30)) statt 58,10 €
- [x] **Abnahme Phase 2** ✅

### Phase 3 – Aufgaben

Entscheidungen (17.10.2026):
- **Sammlungswert = Zustandspreis:** Eigenpreis → belegter Zustandspreis (Plug-in) → Schätzung (NM-Basis × Faktor). Gegradet und versiegelt nur mit Eigenpreis (sonst „kein Wert“, gezählt als „ohne Wert“). Geschätzter Anteil wird ausgewiesen
- **Eine Merkliste** pro Nutzer
- **Gleiche Karte erneut hinzufügen = neue Position** (eigener Kaufpreis/Datum/Notiz)

- [x] Migration `0003_collection`: `folders`, `collection_items` (Karte *oder* Produkt per Check-Constraint, Menge ≥ 1, Grading nur bei Karten), `collection_events`, `portfolio_snapshots`, `wishlist_items`, `products`
- [x] Ordner: Standardordner „Sammlung“ automatisch, anlegen/umbenennen/sortieren, löschen nur mit Zielordner für enthaltene Karten, letzter Ordner bleibt
- [x] Positionen: Karte oder Produkt, Variante (normal/reverse), Zustand (Standard NM), Menge, Kauf- und Eigenpreis, Kaufdatum, Notiz, Grading (Firma + Note). Beim Hinzufügen werden Preise geholt und der Startwert gemerkt
- [x] Bewertung (`app/services/valuation.py`) und Kennzahlen: Gesamtwert, geschätzter Anteil, Aufteilung roh/gegradet/versiegelt, Karten, Sets, Positionen ohne Wert, Top-Karte, größter Gewinner/Verlierer, **Veränderung seit Hinzufügen (Zukäufe zählen nicht)**
- [x] Liste mit Filtern (Ordner, Art, Set, Sprache, Suche) und Sortierung (auch nach Wert); Set-Übersicht mit Fortschritt; Wertverlauf (Tageswerte + Live-Wert + Markierungen bei Bestandsänderungen); CSV-Export (Excel-tauglich, **gegen Formel-Injection geschützt**)
- [x] Merkliste mit NM-Wert; eigene Karten (für alle sichtbar) und Produkte; Bearbeiten/Löschen nur Admin, nicht löschbar solange in Sammlungen
- [x] Admin: Sammlung eines Nutzers **nur lesend** (Kennzahlen, Positionen) – jeder Zugriff im Audit-Log
- [x] Worker: tägliche Runde umfasst Sammlungs- (roh) und Merklisten-Karten, danach Tageswert je Nutzer
- [x] CLI `collection-check` (Probe mit echten Preisen, wird zurückgerollt)
- [x] **Abnahmetest mit Handrechnung:** gemischte Sammlung = 1.055,00 € (geschätzt 255,00 €; roh 255 / gegradet 500 / versiegelt 300); nach Preisanstieg 1.106,00 €, Veränderung +51,00 €, Tageswert gespeichert
- [x] Selbst-Review: `PATCH {"quantity": null}` hätte 500 ergeben, Note bei Rohkarten war setzbar, CSV-Formel-Injection über fremde Produktnamen möglich → alle behoben und getestet. **204 Tests, 95 % Coverage**
- [x] VPS-Lauf ([`docs/phase3/ergebnis.md`](docs/phase3/ergebnis.md)): Migration `0003_collection`, Worker läuft, Probe mit **echten Preisen**: 2× Nachtara VMAX NM 3.611,80 € (2 × 1.805,90), Glurak LP 232,87 € (423,40 × 0,55), PSA 10 900 €, Display 150 € → **4.894,67 €** = Handrechnung; Probe vollständig zurückgerollt (0 Reste); alle neuen Endpunkte ohne Anmeldung 401
- [x] **Abnahme Phase 3** ✅

### Phase 4 – Aufgaben

Entscheidungen (17.10.2026):
- **Weitere Testfotos später.** Phase 4 wird mit dem vorhandenen Testsatz (7 Fotos) fertig gebaut. Die Abnahme „Top-1 ≥ 85 % (DE/EN)“ wird nachgeholt, sobald mehr Fotos da sind
- **Binder-Scan** kommt als **Beta** in Phase 4

Umsetzungsdetails (im Rahmen von 5.6, keine Änderung am Konzept):
- **Katalogbilder lazy je Karte** statt je Set: Ein Bild wird erst geladen, wenn die Karte Kandidat eines Scans ist. Gespeichert werden nur die Merkmale (≈ 200 KB), nicht das Bild. Nur von `assets.tcgdex.net` (Schutz davor, dass eigene Karten mit fremder Bild-URL den Server beliebige Adressen abrufen lassen)
- **Bestätigen:** Der Kartenausschnitt liegt bis zu 30 min nur im Arbeitsspeicher. Bestätigt der Nutzer (oder wählt eine andere Karte), wird er sein Referenzbild (max. 5 je Karte). Das Foto selbst wird nie gespeichert
- **Koreanisch:** zweiter OCR-Durchlauf, wenn das Ergebnis unsicher ist und das Standardmodell weder Japanisch noch Latein erkannt hat (oder Sprache „ko“ gewählt). Er wird nur übernommen, wenn er das Ergebnis verbessert

- [x] Scanner-Modul `app/scanner/`: Bilder sicher laden (JPEG/PNG/WebP/HEIC, Pixel-Grenze, EXIF-Drehung), OCR-Hülle (PP-OCRv6 + koreanisches Modell), Textmerkmale (Nummer mit Setgröße, Setcode inkl. OCR-Verwechslung „5“/„S“, Namen, Sprache aus der Schrift), Slab-Labels (PSA/BGS/CGC, Note, Name, Sprache), Bildabgleich (SIFT + RANSAC, Merkmale kompakt gespeichert), Binder-Zerlegung (Konturen oder Raster 3×3/4×3/2×2)
- [x] Migration `0004_scanner`: `scan_log` (nur Merkmale und Ergebnis, kein Bild), `card_reference_images`; hoch/runter getestet, `alembic check` ohne Abweichungen
- [x] Identifikation (`app/services/scan.py`, `scan_scoring.py`): Kandidaten über Nummer (+ Setgröße/Setcode) und unscharfen Namen, Bildabgleich gegen Katalogbilder **und eigene Referenzbilder**, ohne Text Rettungsweg über eigene Referenzbilder. Punkte mit Begründung je Kandidat, **sicher** nur bei starkem Beleg und klarem Abstand zur nächsten anderen Karte (gleiche Karte in anderer Sprache zählt nicht als Konkurrenz)
- [x] API: `POST /scan`, `POST /scan/batch`, `POST /scan/binder` (Beta), `POST /scan/{id}/confirm`, `GET /scan/references`, `GET /scan/references/{id}/image`, `DELETE /scan/references/{id}`. Ergebnis: bester Treffer + bis zu 4 Alternativen, Confidence, Hinweis („Erkannt als …“ / „Falsche Karte? Selbst suchen“), Slab-Vorschlag
- [x] Schutz: Rate-Limit (600 Bilder/Stunde je Nutzer, 429 + Retry-After), Upload-Grenze **vor** dem Einlesen (413), Dateityp über den Inhalt geprüft, Referenzbilder nur für den Eigentümer, Worker löscht altes Scan-Protokoll (90 Tage) und verwaiste Dateien
- [x] Evaluation: `cli scan-eval` (Top-1, Top-5, „sicher, aber falsch“, Latenz, Abnahme-Status), `soll.csv` um erwartete TCGdex-ID ergänzt (`-` = nicht im Katalog, richtig ist dann „unsicher“). Außerdem `cli scan` und `cli scanner-warmup`
- [x] Docker: Scanner-Bibliotheken im Image, OCR-Modelle inkl. Koreanisch beim Bauen geladen, Volume `scanner-data`
- [x] Qualität: ruff, mypy strict, **314 Tests grün, 96 % Coverage**. Tests mit den echten Testfotos (Bildabgleich echt, OCR als Attrappe mit den Spike-Texten) und ein Ende-zu-Ende-Test mit echter OCR (Slab-Foto 04 → S12-110, PSA 10)
- [x] VPS-Lauf ([`docs/phase4/ergebnis.md`](docs/phase4/ergebnis.md)): Migration `0004_scanner`, beide OCR-Modelle (inkl. Koreanisch) im Image, Volume beschreibbar, Evaluation speichert nichts (0 Einträge), alle Scan-Endpunkte ohne Anmeldung 401, 40-MB-Upload → 413, Speicher API ≈ 90 MB
  - **Evaluation mit echtem Katalog (warm):** Top-1 **5/6** (83 %), **0× „sicher, aber falsch“**, Schiggy (nicht im Katalog) korrekt als unsicher. 02 Mewtu ex (DE), 03/04 Lugia V, 05 Nachtara ex (nur über Bildabgleich, Score 131) und 06 Lugia (`M6a-142`, nur Text, kein Katalogbild) richtig und sicher
  - **07 Karpador (ZH):** falsch, aber als *unsicher* gemeldet. Die Karte fehlt in TCGdex zh-cn (bekannte Lücke aus Phase 1) → Fall für „Karte selbst anlegen“ + eigenes Referenzbild
  - **Latenz:** Ø 2,71 s (warm), max 4,57 s (01, Website-Screenshot mit viel Text) → Ziel ≤ 3 s pro Karte noch nicht bei allen Fotos erfüllt; kalt (erste Bild-Downloads) Ø 3,92 s
  - Kleiner Fehler im VPS-Skript: Testfotos im Container konnten nicht gelöscht werden (gehörten root) → behoben, harmlos
- [x] **Entscheidung Nutzer (17.10.2026):** Latenz bleibt vorerst so (Ø 2,7 s, max 4,6 s), weiter mit Phase 5. Verbesserung in Phase 7
- [x] **Abschluss Phase 4** ✅ – nach Phase 7 verschoben: Latenz ≤ 3 s bei textreichen Fotos (weniger Bildabgleich-Kandidaten, kein KO-Durchlauf bei chinesischen Karten) und Abnahme Top-1 ≥ 85 % (DE/EN) mit weiteren Testfotos

### Phase 5 – Aufgaben

Entscheidungen (17.10.2026):
- **App-Name: „Kartenkiste“** (eigener Name, keine SCNDX-Marke)
- **Tailscale wird vorgezogen** (aus Phase 6), damit die App von Anfang an auf iPhone (PWA, Kamera braucht HTTPS) und Android getestet werden kann
- ~~Tailscale direkt auf dem VPS~~ → **revidiert:** Auf dem VPS läuft Tailscale schon für eine andere App (Gerät `gtcha`). Der erste Versuch hat dieses Gerät umbenannt (behoben, Skript benennt nie mehr um). **Entscheidung Nutzer:** Kartenkiste bekommt ein **eigenes Tailscale-Gerät „kartenkiste“ als Docker-Container** (`deploy/tailscale/serve.json`: HTTPS → `api:8000`). Vorteil: Freunde sehen per Node-Sharing nur Kartenkiste → Abschnitt 8.1
- **Android-APK wird auf dem VPS per Docker gebaut** (Build-Container mit Android-SDK)

- [x] Schritt 1: Tailscale-Container „kartenkiste“ ([`docs/phase5/tailscale.md`](docs/phase5/tailscale.md)): HTTPS im Tailnet, Health ✅, Gerät „gtcha“ der anderen App unverändert
- [x] Flutter-Grundgerüst `app/` (Flutter 3.47.7, Riverpod 3, go_router): Navy-Theme, untere Navigation mit zentralem Scan-Button, API-Client mit automatischer Token-Erneuerung (eine gemeinsame Erneuerung für parallele Anfragen), Refresh-Token sicher gespeichert, Access-Token nur im Speicher. Modelle von Hand statt `freezed` (kein Code-Generator nötig)
- [x] Auth-Screens: Anmelden, Registrieren mit Einladungscode, Passwort-Reset mit Admin-Code
- [x] Übersicht (Wert, Veränderung, Kurve, Schnellaktionen, Kennzahlen, Aufteilung, Highlights), Suche (Sprachfilter, fehlende Karte anlegen), Karten-Detail (Zustandspreise mit „Schätzung“/„Beleg“, Quellen mit Datum und Link, Verlauf mit Tiefst-/Höchstpreis, eBay „Verkauft“), Sammlung (Filter, Sortierung, Ordner, Bearbeiten/Entfernen, Sets mit Fortschritt), Merkliste, Mehr (Profil, Zustandsfaktoren, Standardsprache, Geräte, Passwort)
- [x] Scanner: Kamera/Galerie, Ergebnis mit Sicherheit und Begründung, Alternativen, „Selbst suchen“, Bestätigen (→ eigenes Referenzbild), Slab-Vorschlag beim Hinzufügen; Stapel-Scan und Binder-Scan (Beta)
- [x] Admin: Nutzer (sperren, Rolle, Reset-Code, Sammlung lesend), Einladungen (Code nur einmal sichtbar, kopieren, widerrufen)
- [x] Web-Build wird von der API unter `/` ausgeliefert (Rückfall auf `index.html` für App-Seiten, API-Fehler bleiben JSON, kein Cache für `index.html`/Service-Worker); PWA-Manifest und eigenes Icon (Kartenkiste)
- [x] APK-Build-Container (`deploy/app-builder`, Flutter + Android-SDK + JDK 21, Caches und Signaturschlüssel in Volumes) und Skript `deploy/phase5_app.sh`; APK-Download unter `/kartenkiste.apk` (nur im Tailnet)
- [x] Qualität: `flutter analyze` ohne Befund, **12 Flutter-Tests** (Login, Suche → Detail, kein erfundener Preis, Scan → Sammlung mit Slab, unsicherer Scan, Admin-Einladung, Rechte, Token-Erneuerung, Formatierung); Tests fanden 3 echte Fehler (Navigationsleiste belegte den ganzen Bildschirm, zu breite Auswahlfelder, zu früh freigegebene Eingabedialoge) → behoben. Backend: 316 Tests. CI-Workflow für die App
- [ ] VPS: App bauen (`deploy/phase5_app.sh`) – 1. Lauf: Web + APK gebaut (11 min), aber das Backend-Image war alt (Skript baute es nicht neu) → Startseite 404. Skript korrigiert. 2. Versuch: Startseite ✅, am iPhone aber nur weiße Seite → Ladeanzeige mit sichtbarer Fehlermeldung (statt weiß), Gzip-Kompression (App-Download 11 MB → 4 MB). Lokal mit echtem Backend im Browser durchgeklickt: Login, Übersicht, Sammlung, Suche, Merkliste, Mehr ✅
- [x] Gerätetest 1 (iPhone): App läuft. **Rückmeldung Nutzer:** zu unübersichtlich – Startseite überladen/langweilig, Hinzufügen/Scannen umständlich. **Entscheidung:** „wie SCNDX, aber schlanker“, erst Vorschau-Bilder
- [ ] Neues Design (Vorschau zur Freigabe): Startseite mit farbiger Wert-Karte, großem „Karte scannen“, Bilder-Reihen „Wertvollste Karten“/„Zuletzt hinzugefügt“; Scan-Ergebnis groß mit Preis und **ein Tipp „Hinzufügen“** (NM, 1×; Slab mit Note), danach „Nächste Karte“/„Rückgängig“; Alternativen und Begründung nur auf Wunsch; Hinzufügen-Formular nur Zustand + Anzahl („Weitere Angaben“ aufklappbar); Sammlung als Bilder-Raster; Preis-Erklärung verständlich. 13 App-Tests grün, mit echtem Backend und echter OCR im Browser durchgespielt
- [x] **Rückmeldung Nutzer (Gerätetest 2):** Viele Kartenbilder fehlen (TCGdex: JA ~30 %, KO/ZH-CN 0 %), japanische Karten ohne Übersetzung schwer zu finden. **Entscheidungen:** eigene Fotos *nicht* als Kartenbild → **bessere Bildquelle suchen**; **Übersetzung über PokéAPI: ja**
- [x] Scanner: Promo-Nummern wie „132/M-P“ zählen als Setcode (Karte des Nutzers: Pikachu ex Mega-Promo)
- [x] Übersetzung: Pokémon-Namen aus PokéAPI (`app/data/species_names.json`, 1.025 Pokémon, DE/EN/JA/KO/ZH). Asiatische Karten zeigen den deutschen Namen („ピカチュウex“ → „Pikachu ex“, „ロケット団のミュウツーex“ → „Team Rockets Mewtu ex“) mit Original darunter; Suche „pikachu 132“ findet auch japanische, koreanische und chinesische Karten. Trainer/Energie bleiben unübersetzt
- [ ] Bildquellen-Recherche: Kostenlose APIs mit JP-Bildern gibt es nicht (Master Setter, Scrydex, pokemontcgapi.com nur bezahlt/Test). **Vielversprechend: offizielle Kartendatenbanken** – JP `pokemon-card.com` (Such-API mit allen Karten inkl. Bild-URL), KO `pokemoncard.co.kr`, TW `asia.pokemon-card.com` (vom Open-Source-Projekt PTCG-database genutzt). Hinweis: pokemon-card.com untersagt die *Weiterverbreitung* der Bilder; Nutzung im privaten Kreis, Bilder direkt vom offiziellen Server laden (nicht kopieren/veröffentlichen). Spike auf dem VPS (`deploy/phase5_bildquellen.sh`) prüft Erreichbarkeit, Bild-URLs und Einbinden. ZH-CN: keine offizielle Datenbank gefunden
  - **Ergebnis Spike (17.10.2026):** Ersatzbilder aus anderer Sprachfassung (`fill-images`, 7.733 Bilder) heben die Abdeckung auf DE 96 %, EN 93 %, KO 100 %, ZH-CN 95 %, ZH-TW 55 %, JA 31 %. JP- und TW-Datenbank liefern alle Karten samt Bild, Bilder direkt einbindbar. KO-Schnittstelle abgeschaltet (410). Für DE/EN: pokemontcg.io (EN-Bilder, Set-IDs weichen von TCGdex ab, z. B. `swsh4.5` → `swsh45`) und offizielle pokemon.com-Bilder (DE und EN, ab Schwert & Schild, Muster `…/cms2-de-de/img/cards/web/SWSH7/SWSH7_DE_215.png`). Restlücken DE/EN v. a. Shiny Vault, Galarian/Trainer Gallery, Promos, Trainer-Kits und Sets wie `B2a` (vermutlich TCG Pocket = nur digital). Vorschlag für den Import steht, wartet auf Freigabe
  - **Entscheidung (18.10.2026):** Import wie vorgeschlagen für alle Sprachen freigegeben; TCG-Pocket-Karten bleiben im Katalog
- [x] **Bild-Import gebaut** (`app/services/image_import.py`, Migration 0006): pokemontcg.io-Datensatz (EN-Bilder für EN/DE, Set-Zuordnung über ID, Name und Ausnahmeliste), pokemon.com (offizielle DE/EN-Bilder, Adresse vor dem Speichern geprüft, Sets ohne Treffer werden übersprungen), offizielle Datenbanken Japan und Taiwan (Liste + einmalig Detailseite je Karte, Zuordnung über Setcode + Nummer, sonst Nummer + Setgröße + Name; fehlende Karten werden in bekannten Sets mit TCGdex-ID-Schema angelegt). Regeln: TCGdex-Bild hat Vorrang, Bild in Kartensprache ersetzt Ersatzbild, TCGdex-Abgleich löscht fremde Bilder nicht mehr. Nur Adressen werden gespeichert, 1 Anfrage/s je Server, Schutz gegen geänderte Seiten (Abbruch ohne Speichern). Worker importiert wöchentlich (`PT_IMAGE_IMPORT_INTERVAL_DAYS`), CLI `import-images` (mit `--dry-run`) und `image-status`. App: Bildadressen je Quelle (kleine Fassung für Listen), Etikett „Bild Englisch“ bei Ersatzbildern. Scanner darf die neuen Bild-Hosts laden. Tests: 359 Backend, 15 Flutter
- [x] **Recherche weitere Quellen** ([`docs/phase5/api_recherche.md`](docs/phase5/api_recherche.md)): Freie Preis-APIs (TCGCSV, PokéWallet, PokemonPriceTracker, PokeTrace) liefern US-Preise bzw. dieselben Cardmarket-Durchschnitte wie TCGdex. Cardmarket-API geschlossen, Webseite gesperrt → keine freie Quelle für Cardmarket-Preise nach Sprache und Zustand
- [x] **Entscheidung Nutzer (18.10.2026):** gefilterter Cardmarket-Link, Sprachfaktoren und Lesezeichen zum Auslesen der selbst geöffneten Angebotsseite
- [x] **Deutsche Cardmarket-Preise:** (1) Knopf „Cardmarket-Angebote“ in der Karte öffnet die Angebote gefiltert nach Kartensprache und gewähltem Zustand (`language`, `minCondition`), (2) Sprachfaktoren je Kartensprache (Standard 1,00, Migration 0007) fließen in die Schätzung, (3) Lesezeichen „An Kartenkiste senden“ liest die geöffnete Cardmarket-Seite (Zustand, Preis, Sprach-/Sondersymbole) und öffnet Kartenkiste mit Vorschau; Server wertet aus (Zustand oder besser, günstigstes und Ø 3 günstigste, signiert/Erstauflage ausgeschlossen) und speichert als Beleg `cardmarket_offers` mit Link und Datum. Server ruft Cardmarket nie ab. Tests: 377 Backend, 19 Flutter, Lesezeichen in Chromium gegen Testseite geprüft
- [x] **Recherche TCGAPI.net:** kostenlos nur Kartendaten + Basispreise; eBay-Verkäufe erst im Bezahl-Abo. eBay-Abruf über Tor abgelehnt (Umgehung von Sperren, eBay-Regeln) → **Entscheidung Nutzer:** Lesezeichen erweitern
- [x] **eBay-Verkäufe per Lesezeichen:** Das Lesezeichen erkennt die eBay-Suche „Verkaufte Artikel“ (Knopf in der Karte, mit Sprungmarke) und liest Titel, Preis, Verkaufsdatum. Server schlägt passende Verkäufe vor (Nummer im Titel, kein Konvolut/Produkt/Fälschung, Euro, ≤ 4 Monate), Vorschau mit An-/Abwählen, Gruppen ungegradet bzw. „PSA 10“, „BGS 9.5“ …; gespeichert als `ebay_sold` (Median, ab, bis, Anzahl) mit Link. **Gegradete Sammlungspositionen** werden jetzt mit dem Median gleicher Firma und Note bewertet. Tests: 393 Backend, 21 Flutter, Lesezeichen (Cardmarket + eBay alt/neu) in Chromium geprüft
- [x] **eBay-Zugriffstest (18.10.2026):** Nutzer gibt an, eBay habe das automatische Abrufen erlaubt (Nachweis nicht geprüft; bitte die eBay-Antwort in `docs/` ablegen). Vorbereitet ist nur ein ehrlicher Test: `deploy/phase5_ebay_test.sh [--tor]` ruft die „Verkaufte Artikel“-Suche einmal direkt ab und meldet Status und Sperr-Hinweise. Kein Verschleiern (ehrlicher User-Agent, kein Adresswechsel, keine Captcha-Lösung), kein automatischer Import. Erst nach dem Ergebnis wird entschieden, ob ein Worker-Abruf gebaut wird
  - **Ergebnis:** eBay antwortet dem VPS mit **HTTP 403** (Sperr-Hinweis). Kein automatischer eBay-Abruf; Umgehung (Tor, IP-Wechsel, frische Browser) bewusst nicht gebaut, Tor-Teil wieder entfernt. Weiter nur über eBay selbst (Freigabe der VPS-IP oder Zugang Marketplace Insights) bzw. das Lesezeichen
- [x] **Bild-Import schneller:** Schnellweg ordnet Karten ohne Detailseite zu, wenn Setcode (aus der Liste) und Name im Set auf beiden Seiten eindeutig sind; diese Karten überspringen die Detailseite. Zusätzlich wird alle 2.000 Detailseiten zwischendurch zugeordnet, damit Bilder schon während des Laufs erscheinen. Tempo je Server bleibt 1 Anfrage/s
- [x] **Bild-Import Tempo einstellbar (Nutzerwunsch: schneller testen):** `PT_IMAGE_IMPORT_REQUEST_INTERVAL_SECONDS` (Abstand je Server) und `PT_IMAGE_IMPORT_CONCURRENCY` (gleichzeitige Detailseiten). Automatische Bremse: bei 429/403/503 verdoppelt sich der Abstand je Server (bzw. `Retry-After`, max. 30 s), nach 200 Erfolgen wird er schrittweise wieder kleiner; Sperr-Antworten bei Bildprüfungen zählen nicht als „kein Bild“
- [x] **Tempo-Test 4/s × 8 parallel (18.10.2026):** Taiwan problemlos; pokemon-card.com sperrte nach ~14 min (HTTP 403), Japan brach ab. → **Herantasten:** Startabstand je Server (`PT_IMAGE_IMPORT_START_INTERVALS`, Standard Japan 1 s) und Parallelität je Server (`PT_IMAGE_IMPORT_HOST_CONCURRENCY`, Standard Japan 2). Nach 100 Erfolgen in Folge wird der Abstand × 0,75 kleiner bis zum kleinsten Abstand; bei Sperre einmal verdoppeln (gleichzeitige Sperr-Antworten zählen einmal). Abbruch erst nach 4 Paketen ganz ohne Erfolg; abgebrochene Quellen werden nach `PT_IMAGE_IMPORT_RETRY_HOURS` (3) erneut versucht
- [x] **Rückmeldung Slab-Scan (PSA 10 Lugia V):** Scan zeigte den Near-Mint-Preis der Rohkarte. Jetzt: bei Slabs Median gespeicherter eBay-Verkäufe gleicher Firma und Note; fehlt er, Hinweis und Knopf „Verkaufte PSA 10 bei eBay“ (Suche mit Note, bei asiatischen Karten mit übersetztem Namen + „japanese“). Flutter-Tests: 22
- [x] **Preise direkt beim Scannen holen:** Scan-Ergebnis zeigt für die gewählte Karte Knöpfe „Cardmarket <Sprache> ab NM“ und „eBay verkauft“ (Rohkarte) bzw. „Verkaufte PSA 10 bei eBay“ / „neu holen“ (Slab, Suche mit Note); dort überträgt das Lesezeichen die Preise. Flutter-Tests: 23
- [x] **Schnellere Deploys:** `deploy/phase5_app.sh` baut standardmäßig nur die Web-App; die Android-APK nur mit `--apk` (zuletzt gebaute APK bleibt zum Download erhalten). APK erst zum Abschluss wieder bauen. Web-Build ohne WebAssembly-Probelauf (`--no-wasm-dry-run`, lokal 96 s → 51 s), wird übersprungen, wenn sich `app/` nicht geändert hat (`--force` erzwingt); api/worker starten nur neu, wenn sich das Backend-Image geändert hat
- [x] **Rückmeldung Slab-Scan Mega-Dragonite ex (PSA 10, neues Label nur mit PSA-Logo):** Parser erkennt PSA jetzt auch am Label-Aufbau (Kopfzeile „20xx POKEMON …“ + Notenwort + 8–10-stellige Zertifikatsnummer), Sprachhinweis „JP“, „BLACK LABEL“ → Note „10 BL“; beide echten Fotos geprüft. **Slab frei wählbar:** Formular mit „Rohkarte | Slab“ (auch nachträglich beim Bearbeiten), Firmen PSA, Beckett (BGS), CGC, SGC, TAG, ACE, Andere; Note 1–10 in halben Schritten + Black Label; im Scan-Ergebnis „Ist ein Slab?“ bzw. „Slab anpassen“. API: `PATCH …/items/{id}` mit `grading_company` stellt um (Note Pflicht, Startwert neu). eBay-Gruppen erkennen Black Label
- [x] **Rückmeldung falsche Cardmarket-Seite (Glurak 30th CELEBRATION M6a 137, JA):** TCGdex verlinkt das vereinfacht-chinesische Produkt (Datenfehler bei TCGdex, `cardmarket: 908315`), damit auch falscher Schätzpreis. **Korrektur per Lesezeichen:** Auf Cardmarket die richtige Ausgabe öffnen (z. B. „Reprints“) → Lesezeichen → Vorschau mit Haken „Diese Seite künftig für die Karte verwenden“ (vorausgewählt, wenn man weitergeklickt hat). Gespeichert in `card_price_links` (Migration 0008, gilt für alle Nutzer); danach verlinkt die App diese Seite und nutzt die Cardmarket-Werte von TCGdex für die Karte nicht mehr. Damit die Karte beim Weiterklicken nicht verloren geht, merkt der Server beim Antippen eines Preis-Knopfs die Karte (`PUT/GET /me/price-target`, 2 h). Tests: Backend + 25 Flutter
- [x] **Spike offizielle Cardmarket-Downloads** (`docs/phase5/cardmarket_katalog.md`): Produktkatalog (74 822 Einzelkarten) und Preisführer (79 804 Einträge, Trend/Low/Avg, täglich) sind vom VPS frei abrufbar. Produktnamen enthalten **keine** Setkürzel/Nummern (nur „Charizard [Energy Burn | Fire Spin]“), aber `idExpansion` (Ausgabe) und `idMetacard` (gleiche Karte über alle Ausgaben).
- [x] **Spike 2 Verknüpfung prüfen** (`docs/phase5/cardmarket_mapping.md`): TCGdex verknüpft Sets **geschlossen** mit einer Cardmarket-Ausgabe (ja/M6a: 173/173 in Ausgabe 6603; ja/SV2a, en/de sv03.5 sauber). Der Fehler betrifft also das ganze Set, nicht einzelne Karten – Mehrheitsabgleich erkennt ihn nicht. Zum 30th-Jubiläum hat Cardmarket vier Ausgaben gleichzeitig angelegt (6601: 191, 6602: 176, 6603: 176, 6604: 207 Karten); 6602 und 6603 sind „Zwillinge“ gleicher Größe (vermutlich JA und vereinfachtes Chinesisch). Ausgabenamen/-sprachen stehen nicht im Download.
- [x] **Cardmarket-Verknüpfung im Vorfeld** (Freigabe 20.10.2026; Nutzer prüfte: 6602 = Japanisch, 6603 = vereinfachtes Chinesisch, 6604 = Indonesisch/Thailändisch):
  - Worker lädt ca. 2 min nach dem Start und danach alle 24 h Produktkatalog + Preisführer (`cm_products`, `cm_prices`, Migration 0009), erkennt „Zwillinge“ (Ausgaben mit ≥ 75 % gleichen Metakarten, angelegt innerhalb von 45 Tagen) und fragt für jedes Set ohne Zuordnung TCGdex nach der Cardmarket-ID einer Karte (`card_sets.cardmarket_expansion_*`).
  - Fest hinterlegt: `ja/M6a` → 6602 (Japanisch); Bezeichnungen 6602/6603/6604. Bisher gespeicherte Cardmarket-Werte solcher Sets werden verworfen und neu geholt.
  - Beim Preisabruf hängt der Server das TCGdex-Produkt über `idMetacard` in die Ausgabe des Sets um – **nur zwischen Sprachfassungen** (Trainer-Gallery-Ausgaben u. Ä. bleiben unberührt). Werte dann aus dem Preisführer des richtigen Produkts; fehlt es, gibt es keinen Cardmarket-Preis (statt eines falschen), der Link zeigt trotzdem auf die richtige Seite.
  - App: Zeile „Cardmarket-Ausgabe“ im Scan-Ergebnis (Rohkarte) und auf der Kartenseite, nur wenn es Sprachfassungen gibt; bei unsicherer Zuordnung gelb „Cardmarket-Sprachfassung prüfen“. Auswahl mit Preis, Link zum Ansehen und Benennen der Ausgabe; eine andere Sprachfassung gilt für das ganze Set und alle Nutzer (`PUT /cards/{id}/cardmarket`, Audit-Log).
  - CLI: `cardmarket-import`, `cardmarket-status` (listet unsichere Sets); Skript `deploy/phase5_cardmarket_status.sh`. Tests: Backend 425, Flutter 28
- [x] **Apify Stufe A** (`docs/phase5/apify_probe.md`, kostenlos): Free-Konto (5 $/Monat). Passend: `phantom_coder/cardmarket-listings-scraper` (Produktseite + Sprache + Mindestzustand + Verkäuferland), `crawloop/cardmarket-listings-scraper`, eBay: `caffein.dev/ebay-sold-listings` (ebay.de, meistgenutzt), `yumitori/ebay-sold-scraper` (DE, kostenloses Preismodell, Preisführer je Note). Token nur in der `.env` (`deploy/phase5_apify_token.sh`)
- [x] **Apify Stufe B/C** (`docs/phase5/apify_runs.md`, `apify_runs_c.md`, zusammen 0,11 $): **eBay.de mit `caffein.dev/ebay-sold-listings` sehr gut** (Euro-Preise, Datum, Titel, Link, ~10–20 s, ~0,0001 $ je Lauf; Rohkarte mit `-PSA -BGS -CGC`). `yumitori` liefert trotz DE US-Dollar/ebay.com → ungeeignet. Cardmarket: `phantom_coder` liefert nur ohne Filter Treffer (englische Produktseite), mit Sprache/Zustand 0; `crawloop` mit Residential-Proxy Zeitüberschreitung; Deal-Finder 0 → Cardmarket über Apify vorerst nicht verlässlich
- [x] Cardmarket-Status (`docs/phase5/cardmarket_status.md`): 74 822 Produkte, 28 Ausgaben mit Zwillingen, 454 Sets über TCGdex verknüpft, 355 ohne Cardmarket-ID bei TCGdex, `ja/M6a` fest. „Unsicher“ nur noch für asiatische Sets (DE/EN waren alle richtig): 7 Sets
- [x] **Apify Store-Suche + Stufe D/E** (`docs/phase5/apify_store.md`, `apify_runs_d.md`, `apify_runs_e.md`): 398 Dienste, ~50 mit echtem ebay.de + verkauft; Cardmarket nur 3 mit Angeboten. `phantom_coder` liefert Cardmarket-Angebote **Deutsch ab NM** korrekt, braucht aber die Produktseite mit Namen (nicht `?idProduct=`), Suche danach blockiert. Echte Kosten: eBay.de 20 Verkäufe ≈ 0,07–0,08 $, Cardmarket ≈ 0,15 $ je Abfrage; Monatslimit Apify 8 $
- [x] **Entscheidung 21.10.2026:** eBay automatisch (Punkt 1) + Kostenbremse (Punkt 3); Cardmarket bleibt beim Lesezeichen
- [x] **eBay.de-Verkäufe auf Knopfdruck** (Migration 0010 `ebay_fetches`): Dienst `epicscrapers/ebay-sold-listings-api`, nur ebay.de, 90 Tage, 20 Treffer. Suche aus der Karte („Glurak ex 183/165“, asiatisch mit deutschem Namen + „japanese“); Rohkarte schließt PSA/BGS/CGC/SGC/TAG/Beckett aus, Slab sucht „PSA 10“. Gleiche Suche 72 h gemerkt (kostenlos), „Neu abrufen“ möglich. Kostenbremse `PT_APIFY_MONTHLY_BUDGET_USD` (Standard 7 $, höchstens Apify-Limit) + Deckel 0,15 $ je Lauf; doppelter Tipp startet keinen zweiten Lauf. Vorschau/Auswahl/Speichern wie beim Lesezeichen. App: „eBay verkauft“ bei Scan (Rohkarte und Slab) und Karte holt direkt; ohne Token wie bisher Browser + Lesezeichen. API: `POST /cards/{id}/ebay-sold/fetch`, `GET /apify/status`. Tests: Backend 432, Flutter 30
- [ ] Auf dem VPS: Deploy, eBay-Abruf bei einer Karte und einem Slab testen
- [x] **Apify Pokémon-Suche** (`docs/phase5/apify_pokemon.md`): 197 Dienste, meist US-Plattformen. Entscheidung 21.10.2026: (1) PSA-Zertifikat beim Slab-Scan, (2) Sealed-Preise aus dem Cardmarket-Download, (3) Preisbewegungen der Sammlung
- [x] **Sealed-Preise** (Migration 0011): Der Katalog-Import lädt auch `products_nonsingles_6.json` (Kategorie je Produkt; Zwillinge nur aus Einzelkarten). Suche `GET /cardmarket/sealed?q=` (englische Namen, mit Preis), Anlegen `POST /products/from-cardmarket` (je Sprache, verknüpft gleichnamige Altprodukte statt doppelt). Wert versiegelter Positionen = Median aus Trend, Ø 7, Ø 30 des Preisführers (Quelle „cardmarket“). App: Sammlung → Knopf „Versiegeltes hinzufügen“ (Suche, Sprache, Anzahl). Nebenbei Layout-Überläufe (Kopf der Sammlung, Raster, Startseite) auf schmalen Handys behoben. Tests: Backend 443, Flutter 31
- [x] **Preisbewegungen** (`GET /collection/movers?days=7`): je eigener Rohkarte und Variante neuester Cardmarket-Trend gegen den letzten Wert vor dem Zeitraum, gewichtet mit der Anzahl; Rauschen ausgeblendet (unter 1 € oder unter 5 %). Gegradete und versiegelte Positionen haben keinen Tagesverlauf und fehlen. App: Startseite „Bewegungen (7 Tage)“ mit je 3 Gewinnern und Verlierern. Tests: Backend 444, Flutter 32
- [x] **Spike PSA über Apify** (`docs/phase5/apify_runs_f.md`): beide Dienste von psacard.com geblockt (Cloudflare 403) → unbrauchbar
- [x] **Kartendetails aus TCGdex** (Migration 0012): Worker holt ~10 min nach dem Start und danach täglich je Karte ohne Abgleich `GET /{lang}/cards/{id}` (zuerst DE, EN; 4 gleichzeitig) → Seltenheit, Varianten (normal/reverse/holo/1. Edition), Illustrator und nebenbei die Cardmarket-ID (bessere Cardmarket-Verknüpfung). 404 = abgeglichen, andere Fehler → nächster Lauf. CLI `sync-card-details [--limit]`. App: Kartenseite zeigt Fassungen und Illustrator; beim Hinzufügen nur vorhandene Fassungen (Holo-Karten: „Holo“ statt „Normal“, Reverse nur wenn es sie gibt). Tests: Backend 448, Flutter 33
- [x] **PSA-Zertifikat beim Slab-Scan** (Migration 0013 `psa_certs`): Scanner liest die Zertifikatsnummer (8–10 Ziffern) vom Etikett; mit `PT_PSA_TOKEN` fragt der Server die offizielle PSA Public API (`/cert/GetByCertNumber`) und merkt sich das Ergebnis (30 Tage; PSA gestört → alter Stand). Scan-Antwort: `psa` (Karte, Nummer, Note, Population) und `psa_warning`, wenn PSA eine andere Nummer nennt; die Note von PSA gilt. Manuell: `GET /scan/psa/{nummer}`. Ohne Token unverändert. App: „✓ Von PSA bestätigt …“ und Hinweis im Scan-Ergebnis. Feldnamen der PSA-Antwort aus der PSA-Doku, noch nicht live geprüft. Tests: Backend 452, Flutter 34
- [x] **Spike Sealed-Bilder** (`docs/phase5/sealed_images.md`): Cardmarket liefert keine Bilder; tcgcsv.com (kostenloser Spiegel des TCGplayer-Katalogs) hat für Pokémon (Kat. 3) 4.819 und Pokémon Japan (Kat. 85) 2.783 versiegelte Produkte mit Bild. Gleicher Name trifft nur 12 % → unscharfe Zuordnung nötig. Englische/japanische Verpackungsbilder sind ok (Entscheidung 21.10.2026)
- [x] **Bilder für versiegelte Produkte** (Migration 0014, `app/services/sealed_images.py`): wöchentlich nach dem Katalog-Import (`PT_SEALED_IMAGES_INTERVAL_DAYS`, Standard 7) lädt der Worker die TCGplayer-Produkte von tcgcsv.com und ordnet sie den versiegelten Cardmarket-Produkten zu – Wortvergleich (Jaccard ≥ 0,75, „Booster Box“ = „Display“, „Elite Trainer Box“ = „ETB“ …), gleiche Produktart Pflicht, asiatische Ausgaben zuerst im japanischen Katalog, zweideutige Treffer verworfen. Gespeichert wird nur die Bildadresse; eigene Produkte ohne Bild übernehmen sie. Fehler stören den Import nicht. CLI `cardmarket-import --images` erzwingt den Abgleich. App: Bild in Sammlung, Startseite, Positionsblatt und Sealed-Suche (ganz sichtbar statt beschnitten). Tests: Backend 455, Flutter 34
- [x] Erster Bildabgleich auf dem VPS (21.10.2026): 1.910 von 5.102 versiegelten Produkten mit Bild (37 %) – Box Sets 461, Displays 306, Tins 266, Booster 239, Blister 200, Themendecks 198, ETB 140, Münzen 94
- [x] Web-App-Prüfung (`docs/phase5/web_check.md`): alle Dateien vollständig, auch über Tailscale; „Load failed“ kam vom Neustart beim Deploy. Web-Dateien jetzt `no-cache` (kein Mischstand nach Updates), Ladebildschirm wiederholt einmal und nennt die fehlende Datei
- [x] **Spike PSA API 2** (`docs/phase5/psa_api.md`): Cloudflare sperrt die Contabo-Adresse vor jeder Prüfung des Tokens (auch die Doku-Seite) → vom VPS nicht nutzbar
- [x] **Analyse Fehlschläge** (`docs/phase5/sealed_images_misses.md`): fast immer gibt es das Produkt bei TCGplayer, der Vergleich war zu streng – Füllwörter („EX“, „Unlimited Edition“) zählten wie Namen, „Tins“ ≠ „Tin“, TCGplayer-Produkte ohne erkennbare Art („Battle Academy“) wurden verworfen, „Exclusive“ machte Pokémon-Center-ETBs zweideutig
- [x] **Bildzuordnung nachgeschärft:** gewichtete Ähnlichkeit (seltene Wörter zählen mehr, Schwelle 0,72), Mehrzahl = Einzahl, „Unlimited Edition“/„Exclusive“ ignoriert („1st“ bleibt), unbekannte Art nur bei fast gleichem Namen (≥ 0,9), „Code Card“-Produkte ausgeschlossen, verworfene Altzuordnungen werden entfernt. Analyse mit Stichprobe von 30 Treffern zum Gegenlesen. App: Knopf „Versiegelt“ unten rechts in der Sammlung statt Symbol in der Kopfzeile. Tests: Backend 458, Flutter 34
- [x] Lauf 2 auf dem VPS: 1.914 von 5.102 (37 %), Stichprobe 30 von 30 richtig. Restliche Fehlschläge: TCGplayer ergänzt in Klammern („Theme Deck [Salamence]“), Epochen-Kürzel („XY BREAKthrough“), „POP Series 1 Pack“, „EU“ statt „International Version“
- [x] **Nachschärfung 2:** Klammerwörter, die Cardmarket nicht nennt, zählen nur zu 25 % dagegen; Epochen-Kürzel (EX, XY, BW, SM, SWSH, DP, HGSS) ignoriert; „Pack“ = „Booster“, „EU“ = „International“. Tests: Backend 459
- [x] Lauf 3: 1.964 von 5.102 (38 %), Stichprobe 30 von 30 richtig. „EX“ überall zu ignorieren war zu grob („Reshiram Box“ ≠ „Reshiram ex Box“)
- [x] **Nachschärfung 3:** „EX“ nur am Namensanfang ignoriert (Epoche), Apostroph-Rest „s“ weg, Kategorie „Pokémon Tins“ ergibt die Art Tin. Tests: Backend 460
- [x] Feintuning der TCGplayer-Bilder beendet (38 %); Rest über eigene Fotos (später)
- [x] **Spike Apify G/H:** Cardmarket-Scraper (unfenced-group, ahmed_jasarevic) liefern nur die offizielle Cardmarket-Datei neu verpackt, ohne Bilder; lulzasaur scheitert an der Sperre. parselab verpackt TCGdex (gleiche Felder, Bilder von assets.tcgdex.net, gleiche Lücken). pokemontcg.io-Wrapper nur Englisch, pokeapi = Videospieldaten → Apify bringt für Katalog und Bilder nichts
- [x] **Bestandsaufnahme** (`deploy/phase5_bestand.sh`, `docs/phase5/bestand.md`): Lücken vor allem KO (239 von ~7.900), ZH-CN (877 von ~7.000), JA (~3.300), ZH-TW (~1.500); DE ~750, EN ~230. ~4.000 Pocket-Karten im Katalog. Cardmarket: 74.925 Einzelkarten, davon 39 % mit unseren Karten verknüpft, 260 von 787 Ausgaben zugeordnet

### Phase 5b – Vollständige Daten aus verlässlichen Quellen (Entscheidung 21.10.2026)

Ziel: alle Sets, Karten, Bilder und Preise aller Sprachen. Quellen je Bereich: offizielle Datenbanken der Herausgeber (Karten, Bilder), Cardmarket-Tagesdatei (Preise, Sealed), TCGdex als Ergänzung. „Fertig“ = Bestandsaufnahme erreicht je Sprache die Zielzahl der Quellen-Messung.

- [x] **Pocket entfernt:** TCGdex-Serie `tcgp` (Handyspiel) wird nicht mehr importiert, vorhandene Pocket-Sets werden nach jedem Import gelöscht – Karten in Sammlungen bleiben. CLI `remove-digital [--dry-run]`
- [x] **Sealed-Suche auf Deutsch:** Produktarten („Top-Trainer-Box“, „Display“, „Sammelkoffer“, „Kollektion“ …) und Set-Namen (deutsch → englisch über gleiche TCGdex-ID) werden übersetzt; ohne Treffer zählt die Eingabe. Tests: Backend 463
- [x] **Quellen-Messung** (`bash deploy/phase5_quellen.sh`, `docs/phase5/quellen.md`): EN vollständig (21.290 gegenüber 20.530 im pokemontcg.io-Datensatz; fehlen 2 Mini-Sets und einzelne SM-Karten). DE: 57 englische Sets ohne deutsches Set (McDonald's, Trainer-Kits, POP …), echte Lücken XY-/SW-Promos, Drachengruft, Celebrations Classic. JA: offizielle Suche bricht nach 11 Seiten mit HTTP 503 ab (zu schnell) – fehlende Sets MEZ, MEE, MEM. Asien-Zählung kaputt (Seitenaufbau). Korea: pokemoncard.co.kr antwortet dem Server mit 410. Festland-China: pokemon.cn ohne Kartendatenbank
- [x] **Spike PriceCharting** (`docs/phase5/apify_runs_i.md`, 0,26 $): `gio21/pricecharting-scraper` findet EN, JA, **KO und ZH** (eigene Sets), nicht Deutsch; Preise ungegradet und Grade 7/8/9/9.5/PSA 10 in USD, Nummer, Set, Produkt-URL, ohne Bild (0,005 $ je Treffer). `incognito_mode` liefert Bilder, Verlauf, Verkäufe, POP – aber ~0,075 $ je Produkt
- [x] **PriceCharting-Preise:** neue Preisquelle (Apify `gio21`), nur wenn Cardmarket keinen Preis hat oder die Karte als Slab in einer Sammlung liegt; gesucht englisch (Name über gleiche TCGdex-ID bzw. Pokémon-Namensübersetzung) + Nummer + „Japanese/Korean/Chinese“; Treffer nur bei passender Sprache, Nummer und Name, bei mehreren entscheidet Set bzw. Erscheinungsdatum. Umrechnung mit dem EZB-Tageskurs, gespeichert in Euro. Gültig 30 Tage (`PT_PRICECHARTING_MAX_AGE_DAYS`), eigener Zeitrahmen 45 s, 2 $ des Apify-Monatsbudgets bleiben für eBay reserviert. Rohkarten: Zustandsschätzung auf Basis des US-Preises; Slabs: eBay.de-Median, sonst PriceCharting-Notenpreis (Note 10 nur PSA). Slabs zählen jetzt zur täglichen Preisrunde. App: Quelle „PriceCharting (US-Preis in €)“. Tests: Backend 477, Flutter 34
- [ ] Import Japanisch und Taiwan aus den offiziellen Datenbanken (Kartenliste, Nummern, Bilder)
- [ ] Deutsch und Englisch: fehlende Sets und Promos ergänzen
- [ ] Korea und Festland-China: Quelle festlegen und importieren
- [ ] Preise: Cardmarket-Zuordnung je Ausgabe über Name und Nummer neu aufbauen (Ziel: jede Karte, die Cardmarket führt, hat einen Preis)
- [ ] Sealed: eigene Fotos je Produkt (für alle Nutzer) und Platzhalter je Produktart
- [ ] PSA entscheiden: Link „Bei PSA prüfen“ (psacard.com/cert/…) in der App und/oder PSA-Support um Freigabe der Server-Adresse bitten
- [ ] Auf dem VPS: Deploy, Status prüfen (`deploy/phase5_cardmarket_status.sh`), Glurak M6a 137 erneut scannen – Cardmarket-Knopf muss die japanische Ausgabe öffnen
- [ ] Auf dem VPS: Link-Filter und Lesezeichen an echten Cardmarket- und eBay-Seiten prüfen (Seitenaufbau nur aus Dokumentation bekannt)
- [ ] Bild-Import auf dem VPS: `deploy/phase5_bilder.sh` (Probelauf prüfen, Parser ggf. nachschärfen), danach Abdeckung kontrollieren. Offen: Taiwan-Bilder sind große PNGs (~1,6 MB) – ggf. später verkleinerte Vorschau; Korea weiter ohne Quelle
- [ ] Abnahme: Kern-Flows auf iPhone (PWA) und Android

### Änderungsprotokoll

| Datum | Änderung |
|---|---|
| 17.10.2026 | Plan erstellt |
| 17.10.2026 | Vorhandener Ubuntu-VPS, 5–10 Nutzer, optionaler `CardmarketListingProvider` (ohne Tor/IP-Rotation) |
| 17.10.2026 | Phase 0 gestartet: Backend-Gerüst, Tooling, CI, Docker, Spike-Skript Datenquellen |
| 17.10.2026 | Scanner-Spike, VPS-Skript und Anleitung ergänzt. Phase 0 wartet auf den VPS-Lauf |
| 17.10.2026 | Scanner-Spike mit 7 Nutzerfotos ausgewertet: Go mit Anpassung, Strategie-Vorschlag wartet auf Freigabe |
| 17.10.2026 | Strategie inkl. JP/KO-OCR freigegeben, Abschnitt 5.6 angepasst. Umstieg auf RapidOCR 3 (PP-OCRv6) |
| 17.10.2026 | VPS-Lauf 1 ausgewertet (TCGdex Go, Cardmarket gesperrt, pokemontcg.io 500). Docker-Fehler behoben, Spike Bildabgleich + asiatische Preise ergänzt |
| 17.10.2026 | Preisstrategie entschieden: TCGdex + Schätzung + Plug-in-Schnittstelle. `CardmarketListingProvider` entfällt |
| 17.10.2026 | VPS-Lauf 2 ausgewertet: Docker ok, KO-Modell ok, Bildabgleich Top-1 4/7 (Fehlschläge nur durch Katalog-Lücken) |
| 17.10.2026 | Entscheidungen: pokemontcg.io als Reserve, Referenzbilder pro Nutzer, Karten anlegen für alle. **Phase 0 abgeschlossen** |
| 17.10.2026 | Phase 1 gestartet. Entscheidungen: Passwort-Reset durch Admin, Katalog in allen 6 Sprachen. Code, Tests, CLI, Docker-Start mit Migrationen und VPS-Skript fertig |
| 17.10.2026 | VPS-Lauf Phase 1: 65.561 Karten, Abnahme-Suchen ✅. Fix für Set-IDs mit „+“ und leiseres Import-Protokoll; Nachtest offen |
| 17.10.2026 | Nachtest 0 Fehler; inkrementeller Import vergleicht gemeldete Kartenzahl. **Phase 1 abgeschlossen** |
| 17.10.2026 | Phase 2 gestartet: Beleglink per Produkt-ID (vom Nutzer geprüft), tägliche Runde 12:30 Uhr. Code, Tests, Worker, CLI und VPS-Skript fertig |
| 17.10.2026 | VPS-Lauf Phase 2 ✅. NM-Basis auf Median aus Trend/Ø7/Ø30 umgestellt (Ausreißer beim Glurak Grundset) |
| 17.10.2026 | Nachtest Median ✅. **Phase 2 abgeschlossen** |
| 17.10.2026 | Phase 3 gestartet (Zustandspreis als Wert, eine Merkliste, neue Position je Hinzufügen). Code, Tests, Worker-Erweiterung, VPS-Skript fertig |
| 17.10.2026 | VPS-Lauf Phase 3 ✅ (echte Werte = Handrechnung). **Phase 3 abgeschlossen** |
| 17.10.2026 | Phase 4 gestartet: Binder-Scan als Beta, weitere Testfotos später (Abnahme 85 % wird nachgeholt) |
| 17.10.2026 | Phase 4: Scanner-Modul, Identifikation, API (Einzel/Stapel/Binder, Bestätigen, Referenzbilder), Evaluation, Docker und VPS-Skript fertig. VPS-Lauf offen |
| 17.10.2026 | VPS-Lauf Phase 4: Top-1 5/6, 0× sicher-aber-falsch, Latenz Ø 2,7 s / max 4,6 s. Aufräum-Fehler im Skript behoben |
| 17.10.2026 | Entscheidung: Latenz-Tuning nach Phase 7. **Phase 4 abgeschlossen** |
| 17.10.2026 | Phase 5 gestartet: App „Kartenkiste“, Tailscale vorgezogen und direkt auf dem VPS, APK-Build per Docker auf dem VPS |
| 17.10.2026 | Tailscale-Fehler: erstes Skript hat das bestehende VPS-Gerät (andere App) umbenannt. Rückbau-Anleitung, Skript abgesichert; neu: eigenes Gerät „kartenkiste“ im Container |
| 17.10.2026 | Tailscale-Container ✅. Flutter-App mit allen Kern-Screens, Tests, Web-Auslieferung durch die API, Build-Container für Web + APK |
| 18.10.2026 | eBay-Verkäufe per Lesezeichen, Wert für gegradete Karten |
| 18.10.2026 | Deutsche Cardmarket-Preise: gefilterter Link, Sprachfaktoren, Lesezeichen „An Kartenkiste senden“ |
| 18.10.2026 | Bild-Import aus pokemontcg.io, pokemon.com und den offiziellen Datenbanken JP/TW (wöchentlich im Worker) |
| 18.10.2026 | Neues, schlankeres Design (Vorschau). Übersetzung asiatischer Kartennamen (PokéAPI) + mehrsprachige Suche. Recherche Bildquellen → Spike offizielle Datenbanken |
| 20.10.2026 | Cardmarket-Verknüpfung im Vorfeld: offizieller Katalog + Preisführer, Sprachfassung je Set (Glurak M6a → japanisch), Auswahl im Scan und auf der Kartenseite |

---

## 1. Festgelegte Entscheidungen

| Thema | Entscheidung |
|---|---|
| Frontend | **Flutter** (Dart): Android-APK plus **PWA (Flutter Web)** für iPhone |
| Backend | **Python 3.12**, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, PostgreSQL |
| Scanner | Serverseitig in Python: OpenCV (Kartenerkennung) + OCR + Bild-Matching, alles lokal und kostenlos |
| Karten-/Preisdaten | **TCGdex** (mehrsprachig, Cardmarket-Preisfelder) als Hauptquelle, **pokemontcg.io** nur als Reserve. Preise gelten nur mit Quelle, Datum und Link |
| Hosting | **Vorhandener VPS (Ubuntu)** mit Docker Compose |
| Nutzerzahl | **5–10 Nutzer** (Freundeskreis) |
| Zugang für Freunde | **Tailscale** (Free-Plan). Das Backend ist nicht öffentlich erreichbar, Freunde nutzen Node-Sharing |
| Nutzerverwaltung | Einladungscode + E-Mail/Passwort. Rollen: `user` und `admin` |
| Datenschutz | Jeder sieht nur seine Sammlung. Der Admin sieht die Nutzerliste und darf jede Sammlung **lesend** einsehen (mit Audit-Log) |
| Zustandspreise | NM-Basis = Median aus Cardmarket-Trend, Ø 7 und Ø 30 Tagen × Zustandsfaktor (als Schätzung markiert), Eigenpreis, Plug-in-Schnittstelle für weitere Quellen (Abschnitt 5.3) |
| eBay | Deep-Link zur eBay-Suche mit Filter „Verkaufte Artikel“, keine eigenen Verkaufsdaten |
| KI-Chat | Entfällt (laufende Kosten) |
| Kosten | Keine zusätzlichen (VPS ist vorhanden). Alle Dienste und Bibliotheken sind kostenlos |

Abgrenzung: Wir bauen die **Funktionen** nach. Code, Name, Logo, Icon, Texte und Screenshots von SCNDX übernehmen wir **nicht**. Kartenbilder und -namen gehören den Rechteinhabern (The Pokémon Company). Das Projekt bleibt privat.

---

## 2. Funktionsumfang (aus den Screenshots abgeleitet)

### 2.1 Übersicht (Dashboard)
- Schnellaktionen: Karte scannen, Sammlung, Merkliste, Stapel scannen.
- Suchfeld mit Hinweis „Karte suchen – Preis mit Beleg“.
- Kachel „Sammlungswert“:
  - Gesamtwert in €.
  - Veränderung seit dem Hinzufügen. Zukäufe zählen nicht mit.
  - Info-Text, solange noch keine Kurve vorliegt. Vergangene Tage werden nicht nachgetragen.
- Kennzahlen: Gesamt-Karten, Anzahl Sets, höchster Einzelwert.
- Aktuelle Highlights: Top-Karte (teuerste), später größter Gewinner und Verlierer.

### 2.2 Scannen
- Kameraansicht mit Rahmenmarkierung, Blitz-Schalter und Auslöser.
- Foto aus der Galerie.
- „Manuell hinzufügen“.
- **Stapel-Scan**: mehrere Karten nacheinander, Ergebnisliste zum Bestätigen.
- **Binder-Scan (Beta)**: eine Binderseite (3×3 oder 4×3) fotografieren und alle Karten erkennen.
- Erkennungsergebnis mit Hinweis „Erkannt als …“ und „Falsche Karte? Selbst suchen“.
- Das Original begrenzt die Scans pro Woche (Abo-Modell). Das übernehmen wir nicht. Optional gibt es ein pro Nutzer konfigurierbares Rate-Limit gegen Missbrauch.

### 2.3 Suche
- Freitext auf Deutsch und Englisch, auch gemischt.
- Name + Kartennummer kombiniert, z. B. `nachtara 215`.
- Ergebnisliste mit Vorschaubild, Name, Set und Nummer. Die Sprache steht im Titel, z. B. „(JP)“.
- Sprachen: DE, EN, JP, KO, ZH (vereinfacht und traditionell).
- Versiegelte Produkte (Booster, Bundles, Top-Trainer-Boxen, Displays, Cases).

### 2.4 Karten-Detail
- Kopf mit Bild, Name, Set und Nummer.
- Sprachwahl, wenn die Karte in mehreren Sprachen existiert („Welche Sprache?“). Der Preis wird erst danach ermittelt.
- Zustandsauswahl MT / NM / EX / GD / LP / PL / PO.
- Preisblock:
  - Cardmarket-Preis (DE) mit Datum und Link zur Quelle.
  - Sektion „Andere Zustände“.
  - Hinweis, wenn es keinen belegten Preis gibt: keine erfundene Zahl.
- Button „Aktuelle Angebote bei eBay“ (Deep-Link).
- Preisverlauf als Kurve, dazu „Tiefster Preis“ und „Höchster Preis“ über alle belegten Preise seit Beobachtungsbeginn.
- „Hinzufügen zu“ (Ordner), „Gemerkt“-Schalter.
- Eigener Preis, wenn man die Karte anders bewertet. Er wird klar als „dein Preis“ gekennzeichnet.

### 2.5 Sammlung
- Kopf mit „N Positionen · M Objekte“.
- Sammlungswert mit Kurve. Markierte Punkte zeigen, wo sich der Bestand geändert hat. Dazu der Hinweis „Ein Sprung ist ein Zu- oder Abgang, kein Gewinn“.
- Aufteilung: **Rohkarten**, **Gegradet**, **Versiegelt** (Wert und Anzahl Positionen).
- Suche in der Sammlung.
- Ordner-Auswahl und „Filtern & sortieren“.
- Gruppierung nach Set mit Fortschritt („1 von 216 Karten“), aufklappbar.
- Je Position: Menge, Kaufpreis, Notiz, Zustand, Sprache.
- **CSV-Export** (teilen).
- Gegradete Karten: Grading-Firma und Note, nach Möglichkeit per OCR vom Slab-Label gelesen.

### 2.6 Listen / Merkliste
- Gemerkte Karten mit Löschen-Symbol.
- Mehrere Ordner für die Sammlung (z. B. „Sammlung“, „Sammlung 2“).

### 2.7 Mehr-Menü (⋮)
- Profil, Passwort ändern, Abmelden, Einstellungen (Zustandsfaktoren, Standardsprache).
- Hilfe/FAQ (statt Chat).
- **Admin-Bereich**, nur für Admins:
  - Nutzerliste.
  - Einladungscodes erzeugen und widerrufen.
  - Sammlung eines Nutzers **nur lesend** einsehen.
  - Nutzer sperren oder löschen.

### 2.8 Design
- Dunkles Navy-Theme mit Blau-/Violett-Akzenten.
- Untere Navigation: Übersicht, Sammlung, **zentraler Scan-Button**, Suche, Listen, Mehr.
- Eigene Farben, eigenes Logo und eigener Name, keine Übernahme der SCNDX-Marke.

---

## 3. Architektur

```
┌────────────────────┐   HTTPS (Tailscale)   ┌──────────────────────────────┐
│ Flutter App        │ ───────────────────▶ │ VPS (Docker Compose)         │
│  · Android (APK)   │                       │  ┌────────┐  ┌───────────┐   │
│  · PWA (iOS/Web)   │ ◀─────────────────── │  │ api    │  │ worker    │   │
└────────────────────┘                       │  │FastAPI │  │ Preise,   │   │
                                             │  │+Scanner│  │ Katalog   │   │
        Tailscale (Node-Sharing)             │  └───┬────┘  └────┬──────┘   │
                                             │      └─── PostgreSQL ───┘    │
                                             │  tailscale (Sidecar, serve)  │
                                             └──────────────────────────────┘
                                                   │ ausgehend
                                       TCGdex API · pokemontcg.io API
```

### 3.1 Warum der Scanner im Backend liegt
- Die Logik besteht einmal in Python und ist testbar.
- Sie funktioniert für Android **und** die iOS-PWA gleich, ohne native ML-Pakete.
- Die App schickt ein bereits verkleinertes Foto (max. ca. 1280 px, JPEG) an `POST /scan`.
- Nachteil: Die Erkennung braucht eine Netzverbindung. Das ist bei einer Freundes-App akzeptabel.

### 3.2 Backend-Stack (Python)
- Python 3.12, **FastAPI** (async), **Pydantic v2**, **SQLAlchemy 2.0 async** + **asyncpg**, **Alembic**.
- **httpx** (async Clients für die Daten-APIs), **tenacity** (Retries mit Backoff).
- **argon2-cffi** (Passwort-Hashing), **PyJWT** (Access- und Refresh-Token).
- **APScheduler** oder ein eigener Worker-Container für geplante Jobs.
- **structlog** (strukturierte Logs), **pydantic-settings** (Konfiguration über Umgebungsvariablen).
- Scanner: **opencv-python-headless**, **numpy**, **RapidOCR 3** (ONNX, PP-OCRv6 für DE/EN/JP/ZH, zusätzliches KO-Modell), **imagehash** und optional ein kleines ONNX-Embedding-Modell.
- Qualität: **ruff** (Lint + Format), **mypy --strict**, **pytest** + **pytest-asyncio** + **httpx.AsyncClient**, **testcontainers** oder eine Postgres-Test-DB, **pre-commit**.
- Paketverwaltung mit **uv** und `pyproject.toml`.

### 3.3 Frontend-Stack (Flutter)
- Flutter 3.x stable. State-Management mit **Riverpod**, Routing mit **go_router**.
- **dio** für HTTP mit Interceptor für Token-Refresh. **freezed** + **json_serializable** für Modelle.
- **camera** (plus Web-Fallback über `image_picker`/Browser-Kamera), **fl_chart** für Kurven, **cached_network_image**.
- **flutter_secure_storage** (Android) bzw. verschlüsselter Web-Speicher für Tokens.
- Tests: `flutter_test`, Widget-Tests und Golden-Tests für die Kernscreens.

### 3.4 Repo-Struktur (Monorepo)

```
Pokemon_Tracker/
├── UMSETZUNGSPLAN.md
├── README.md
├── docker-compose.yml
├── .github/workflows/        # CI: ruff, mypy, pytest, flutter test
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── core/             # config, security, logging, deps
│       ├── db/               # engine, session, base
│       ├── models/           # SQLAlchemy-Modelle
│       ├── schemas/          # Pydantic-DTOs
│       ├── repositories/     # Datenzugriff, erzwingt Owner-Filter
│       ├── services/         # Fachlogik (collection, pricing, scan, admin)
│       ├── providers/        # Katalog- und Preisquellen (austauschbar)
│       ├── scanner/          # detect, rectify, ocr, match, pipeline
│       ├── workers/          # Katalog-Sync, Preis-Snapshots
│       └── api/v1/           # Router: auth, cards, scan, collection, lists, admin
│   └── tests/
├── app/                      # Flutter-Projekt
│   └── lib/{core,features/{dashboard,scan,search,card_detail,collection,lists,admin,settings}}
└── deploy/                   # Compose-Overrides, Tailscale-Setup, Backup-Skripte
```

---

## 4. Datenmodell (PostgreSQL)

| Tabelle | Wichtige Spalten |
|---|---|
| `users` | id (UUID), email (unique), password_hash, role (`user`/`admin`), is_active, created_at |
| `invite_codes` | code_hash, note, created_by, expires_at, used_by, used_at, revoked_at |
| `password_reset_tokens` | user_id, token_hash, created_by (Admin), expires_at, used_at |
| `refresh_tokens` | id, user_id, token_hash, family_id (Diebstahlerkennung), expires_at, revoked_at, replaced_by (Rotation), user_agent |
| `sets` | id, external_id, name_de/en/…, series, release_date, total_cards, logo_url |
| `cards` | id, external_id, set_id, number, language, name, name_de/en, rarity, image_url, search_vector (tsvector), source (`tcgdex`/`user`), created_by, updated_by |
| `card_reference_images` | id, card_id, user_id (Eigentümer, Referenz wirkt nur für ihn), image_path, features (vorberechnete Merkmale), source_scan_id, created_at |
| `products` | id, kind (`booster`, `booster_bundle`, `elite_trainer_box`, `display`, `tin`, `collection_box`, `blister`, `case`, `other`), language, name, set_id, image_url, created_by – von Nutzern angelegt, für alle sichtbar |
| `price_points` | id, card_id, source (`cardmarket`/`tcgplayer`/Plug-in), variant, metric (`trend`, `low`, …), condition (nur bei zustandsgenauen Quellen), value, currency, source_updated_at, source_url, fetched_at. Schätzungen werden nicht gespeichert, sondern berechnet. Preise für versiegelte Produkte folgen mit den Produkten |
| `price_checks` | card_id + source, checked_at, ok, message, last_viewed_at |
| `folders` | id, user_id, name (je Nutzer eindeutig), sort_order |
| `collection_items` | id, user_id, folder_id, card_id **oder** product_id, variant, condition, quantity, purchase_price, purchase_date, custom_price, note, grading_company, grade, value_at_add (Startwert für „Veränderung seit Hinzufügen“) |
| `collection_events` | id, user_id, item_id, event_type (added/quantity_changed/removed), delta_quantity, unit_value, created_at (Basis für die markierten Punkte) |
| `portfolio_snapshots` | user_id + day, total_value, raw_value, graded_value, sealed_value, estimated_value, item_count, position_count |
| `wishlist_items` | id, user_id, card_id **oder** product_id (je Nutzer eindeutig), created_at |
| `user_settings` | user_id, default_language, condition_factors (JSONB) |
| `audit_log` | id, actor_id, action, target_user_id, created_at, ip |
| `scan_log` | id, user_id, created_at, matched_card_id, confidence, duration_ms (für Rate-Limit und Qualitätsmessung) |

Regeln:
- Alle nutzerbezogenen Tabellen haben `user_id`. Jede Abfrage geht über Repositories, die `user_id` zwingend filtern.
- Zusätzlich optional **PostgreSQL Row-Level-Security** als zweite Absicherung. Dafür setzt jede Sitzung `SET app.current_user`.
- Preise werden **nie überschrieben**. Jeder Abruf wird zu einem neuen `price_point`, daraus entstehen Kurven sowie Tiefst- und Höchstpreis.

---

## 5. Daten, Preise und Scanner

### 5.1 Katalog
- **Quelle:** TCGdex (REST, mehrsprachig, Karten mit Bild-URLs, Cardmarket-Preise) als Hauptquelle.
- **Reserve:** pokemontcg.io nur für englische Karten und nur, wenn TCGdex nicht erreichbar ist. Preise von dort tragen ihr eigenes Datum (im Spike ~11 Monate alt) und werden entsprechend angezeigt.
- **Selbst angelegte Karten:** Fehlt eine Karte (z. B. alte JP-Karten, chinesische Sondersets), kann jeder Nutzer sie mit Name, Set, Nummer, Sprache und Foto anlegen. Sie ist für alle sichtbar (`source = user`), der Admin kann sie bearbeiten oder löschen. Preise dafür: Eigenpreis oder Plug-in-Quelle.
- Worker `catalog_sync`:
  - Initialer Import aller Sets und Karten pro Sprache. Danach tägliche Inkremente anhand neuer Sets.
  - Volltextsuche über Postgres (`tsvector` + `pg_trgm`) für Tippfehler und gemischte DE/EN-Namen.
- Der Suchparser trennt Name und Nummer: `nachtara 215` → Name ≈ „nachtara“, Nummer = 215. Dazu kommen Formate wie `125/SM-P`, `215/203` und `SV9 12`.
- **Phase-0-Ergebnis:** siehe [`docs/spikes/datenquellen_auswertung.md`](docs/spikes/datenquellen_auswertung.md).

### 5.2 Versiegelte Produkte
- Für Booster, Displays und Boxen ist **keine freie, strukturierte Quelle bekannt**. Das wird in Phase 0 geprüft.
- Fallback: Produkte lassen sich **selbst anlegen** (Name, Set, Typ, Bild) und mit **manuellem Preis** führen. Ein kleiner Seed-Katalog gängiger Produkttypen je Set kann ergänzt werden.

### 5.3 Preise: belegt, geschätzt, manuell
Grundregel wie im Original: **Wir erfinden keine Preise.** Jede Zahl trägt Typ, Quelle, Datum und Link.

*Entscheidung 17.10.2026 nach dem Datenquellen-Spike: Cardmarket blockt schon die erste direkte Anfrage per Cloudflare. Umgesetzt werden deshalb (a) Preise aus TCGdex plus markierte Schätzung und (b) eine Plug-in-Schnittstelle für weitere Preisquellen. Ein eigener Cardmarket-Abruf (mit oder ohne Tor) ist nicht Teil des Projekts.*

| Preis-Art | Herkunft | Anzeige |
|---|---|---|
| `verified` | TCGdex-Felder `pricing.cardmarket.*` (siehe unten), Datum aus `updated`, Link aus `idProduct` | „Cardmarket · Stand TT.MM.JJJJ“ + Link zur Produktseite |
| `estimated` | NM-Basis × Zustandsfaktor | deutlich als **„Schätzung“** markiert, nie als belegt summiert |
| `manual` | Eigener Preis des Nutzers | „Dein Preis“ |
| `external` | Optionale Plug-in-Quelle (siehe unten) | Name der Quelle + Datum + Link, wie vom Plug-in geliefert |

**TCGdex-Felder und ihre Verwendung** (je Variante: normal bzw. `*-holo` für Holo/Reverse):

| Feld | Anzeige in der App | Verwendung |
|---|---|---|
| `trend` | **Marktpreis (Trend)** | Hauptwert der Anzeige; fließt in die NM-Basis ein |
| `low` | **Günstigstes Angebot** (beliebiger Zustand) | Info, nicht als NM-Preis verwenden. Im Spike: 220 € bei 1.806 € Trend |
| `avg1`, `avg7`, `avg30` | Durchschnitt 1/7/30 Tage | Detailansicht und Preisverlauf |

**NM-Basis (Entscheidung 17.10.2026 nach VPS-Lauf Phase 2):** Median aus `trend`, `avg7` und `avg30` (soweit vorhanden), Ersatz `avg`. Grund: Beim Glurak (Grundset) lag der Trend mit 58,10 € sogar unter dem günstigsten Angebot (95 €), Ø 7 = 423,40 €, Ø 30 = 765,81 € – der Median (423,40 €) ist robust gegen solche Ausreißer und bei unauffälligen Karten gleich dem Trend. Die App zeigt Basis und Wert immer mit an.

**Zustandsfaktoren (Standard, je Nutzer änderbar):** MT 1,05 · NM 1,00 · EX 0,85 · GD 0,70 · LP 0,55 · PL 0,40 · PO 0,25. Die Werte sind ein Startpunkt und werden im Einstellungsbereich offen angezeigt.

**Gegradete Karten:** Ein belegter Preis kommt nur aus einer externen Quelle (Plug-in) oder als Eigenpreis. Eine Schätzung aus Rohkartenpreisen gibt es dafür nicht, weil Grading-Aufschläge zu stark schwanken.

**Asiatische Karten:** Ob TCGdex dafür Preise liefert, prüft VPS-Lauf 2. Fehlen sie, gibt es keinen belegten Preis. Die App zeigt dann „kein belegter Preis“ und bietet den Eigenpreis an.

Das Preissystem ist **austauschbar** gebaut (`PriceProvider`-Protokoll in `app/providers/`):
- `TcgdexCardmarketProvider`: Standard, kostenlos, belegt.
- `ConditionFactorEstimator`: Schätzung je Zustand. Er greift nur, wenn keine Quelle einen belegten Zustandspreis liefert.
- `ManualPriceProvider`: Eigenpreis.
- **Plug-in-Schnittstelle für weitere Quellen** (`external`):
  - Eine Quelle ist eine Python-Klasse, die das `PriceProvider`-Protokoll erfüllt. Eingebunden wird sie über `PT_EXTRA_PRICE_PROVIDERS` (Liste von Importpfaden, z. B. `meine_quelle.provider:MeinProvider`). Standard ist leer.
  - Vertrag: Eingabe Karte/Produkt + Sprache + Variante + Zustand. Ausgabe `PricePoint` mit Wert, Währung, Zustand, Quelle, Datum und Beleglink. Kein Beleg heißt kein Preis.
  - Absicherung im Kern:
    - Timeout je Abruf.
    - Fehler einer Quelle legen die App nicht lahm.
    - Nach wiederholten Fehlern pausiert die Quelle automatisch, mit Hinweis im Admin-Bereich.
    - Ergebnisse werden 24 Stunden gecacht.
  - Für Inhalt, Rechtmäßigkeit und Nutzungsbedingungen einer eingebundenen Quelle ist ihr Betreiber verantwortlich. Das Projekt liefert selbst keine Quelle mit, die Zugangssperren umgeht.
  - Kandidat für später: die **offizielle Cardmarket-API**, falls ein Zugang beantragt und gewährt wird.

### 5.4 Preis-Snapshots
- Worker `price_snapshot` täglich (nachts):
  - Preise aller Karten in mindestens einer Sammlung oder Merkliste abrufen (nicht den ganzen Katalog) und als `price_point` speichern. Das spart Last und Ratenlimits.
  - Danach pro Nutzer ein `portfolio_snapshot` berechnen.
- Höflicher Umgang mit den APIs: Concurrency-Limit, Retries mit Backoff, Caching, `User-Agent` mit Kontaktadresse.
- Die Kurve wird **ab jetzt aufgezeichnet**. Vergangene Tage lassen sich nicht rekonstruieren, der Info-Text im Dashboard erklärt das.

### 5.5 eBay
- Button „Aktuelle Angebote bei eBay“ öffnet `https://www.ebay.de/sch/i.html?_nkw=<Name+Nummer+Set>&LH_Sold=1&LH_Complete=1`.
- Zusätzlich ein Link zur Cardmarket-Produktseite. Beide sind reine Deep-Links ohne Datenabruf.

### 5.6 Scanner-Pipeline (`app/scanner/`)

*Angepasst nach dem Scanner-Spike, freigegeben am 17.10.2026. Begründung: [`docs/spikes/scanner_auswertung.md`](docs/spikes/scanner_auswertung.md).*

1. **Aufnahme:**
   - **Live-Scan:** Die App zeigt einen Kartenrahmen und schickt nur diesen Ausschnitt.
   - **Galerie-Fotos:** Sie werden komplett geschickt.
2. **Vorverarbeiten:** EXIF-Rotation korrigieren, auf max. 1280 px skalieren.
3. **OCR:** RapidOCR 3 mit PP-OCRv6 (DE/EN/JP/ZH in einem Modell) auf dem Bild bzw. Rahmenausschnitt.
   - **Koreanisch:** eigenes Modell `korean_PP-OCRv5`. Es wird zusätzlich ausgeführt, wenn Hangul vermutet wird oder der erste Durchlauf zu wenig liefert.
   - Konturerkennung mit Entzerrung ist nur noch ein Zusatz für Galerie-Fotos. Ihr Ausschnitt wird bevorzugt, wenn das Seitenverhältnis plausibel ist.
4. **Merkmale extrahieren:**
   - Kartennummer (`110/098`, `No.007`, `SWSH050`).
   - Setcode (`S12`, `SV8a`, `DRI` …).
   - Namenskandidaten (alle Textzeilen).
   - Sprache aus der Schrift (Kana, Hanzi, Hangul, Latein).
5. **Identifikation (Reihenfolge):**
   1. **Setcode + Nummer**: in der Regel eindeutig.
   2. **Nummer + Name unscharf** (Logos wie „ex“, „V“, „VMAX“ fehlen oft im OCR).
   3. **Bildabgleich** (SIFT-Merkmale + RANSAC, im Spike erprobt) gegen die Katalogbilder der Kandidaten **und die eigenen Referenzbilder des Nutzers**. Er ist zugleich Kontrolle und Rettungsweg, wenn kein Text lesbar ist (kleine Screenshots, Glitzerfolie). Schwelle für einen sicheren Treffer: Score ≥ 50 (im Spike: richtige Treffer 214–370).
   - **Eigene Referenzbilder (pro Nutzer):** Bestätigt ein Nutzer einen Treffer oder wählt die Karte selbst aus, wird der Kartenausschnitt seines Fotos samt Merkmalen gespeichert. Die Referenz wirkt nur bei seinen eigenen Scans. So schließen sich Bildlücken (v. a. JP/ZH) mit der Zeit.
6. **Slab-Pfad:** Wird ein Grading-Label erkannt (PSA/BGS/CGC), liest der Scanner Set, Name, Nummer und Note daraus. Die Karte wird als „gegradet“ vorgeschlagen.
7. **Ergebnis:** bester Treffer plus bis zu 4 Alternativen mit **Confidence-Score**. Bei niedriger Confidence zeigt die App „Falsche Karte? Selbst suchen“ und die Kandidatenliste.
8. **Stapel:** mehrere Bilder nacheinander durch dieselbe Pipeline, Ergebnisliste zum Bestätigen und Korrigieren.
9. **Binder-Seite (Beta):** Raster aus Karten erkennen (Konturen oder Gitterannahme 3×3/4×3), jede Zelle einzeln durch die Pipeline. Die Qualität schwankt, deshalb ist es als Beta markiert.
Gradete Karten werden immer zur Bestätigung angezeigt (siehe Schritt 6).

Qualitätsmessung: Ausgangsbasis ist der Testsatz in `scanner_testset/` (7 Fotos, mit Soll-Werten). Er wird schrittweise erweitert, Ziel sind mindestens 200 echte Fotos (verschiedene Sprachen, Licht, Hintergründe, Sleeves) mit erwarteten Karten. Das Skript `scripts/eval_scanner.py` gibt Top-1- und Top-5-Trefferquote aus. **Ziel Top-1 ≥ 85 %** auf deutschen und englischen Karten.

Katalog-Bildindex: Das Herunterladen von über 100.000 Kartenbildern ist teuer. Deshalb wird er **lazy** aufgebaut: Ist eine Karte zum ersten Mal Kandidat eines Scans, wird ihr Bild geholt und nur dessen Merkmale werden gespeichert (umgesetzt in Phase 4, je Karte statt je Set – sparsamer). Ein Vorbefüllen häufiger Sets ist bei Bedarf in Phase 7 möglich.

---

## 6. API (Entwurf, `/api/v1`)

| Bereich | Endpunkte |
|---|---|
| Auth | `POST /auth/register` (mit Einladungscode), `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/reset-password` (Code vom Admin) |
| Katalog | `GET /cards/search?q=&lang=`, `GET /cards/{id}`, `GET /cards/{id}/prices`, `GET /cards/{id}/price-history?source=&variant=&metric=&days=`, `GET /sets`, `GET /products/search` |
| Scan | `POST /scan` (Bild), `POST /scan/batch`, `POST /scan/binder` (Beta), `POST /scan/{id}/confirm`, `GET /scan/references`, `GET /scan/references/{id}/image`, `DELETE /scan/references/{id}` |
| Sammlung | `GET/POST /collection/items` (Filter, Sortierung), `GET/PATCH/DELETE /collection/items/{id}`, `GET /collection/summary`, `GET /collection/sets`, `GET /collection/history`, `GET /collection/export.csv` |
| Eigene Karten/Produkte | `POST /cards`, `GET/POST /products`, Admin: `PATCH/DELETE /admin/cards/{id}`, `PATCH/DELETE /admin/products/{id}` |
| Ordner | `GET/POST /folders`, `PATCH/DELETE /folders/{id}` (`?move_to=`) |
| Merkliste | `GET/POST /wishlist`, `DELETE /wishlist/{id}` |
| Dashboard | `GET /dashboard` (Wert, Veränderung, Kennzahlen, Highlights) |
| Eigenes Konto | `GET/PATCH /me`, `POST /me/password`, `GET /me/sessions`, `DELETE /me/sessions/{id}`, später `GET/PATCH /me/settings` |
| Admin | `GET /admin/users`, `PATCH /admin/users/{id}` (sperren, Rolle), `POST /admin/users/{id}/password-reset`, `GET/POST /admin/invites`, `DELETE /admin/invites/{id}`, `GET /admin/users/{id}/collection/summary|items` (nur lesend, auditiert), `GET /admin/price-sources` |

Konventionen: OpenAPI-Schema aus FastAPI, Pagination per Cursor, einheitliches Fehlerformat, Geldbeträge als `Decimal`/Integer-Cent, Zeitstempel in UTC.

---

## 7. Sicherheit und Datenschutz

- **Passwörter:** Argon2id, Mindestlänge 10, kein Klartext in Logs.
- **Tokens:** Access-Token 15 Minuten, Refresh-Token mit Rotation und Wiederverwendungserkennung, Speicherung nur als Hash.
- **Einladungscodes:** zufällig (≥ 128 Bit), einmalig verwendbar, mit Ablaufdatum, nur als Hash gespeichert.
- **Mandantentrennung:** Repositories erzwingen `user_id`, optional Postgres-RLS. Tests prüfen explizit, dass Nutzer A die Daten von Nutzer B **nie** erhält (IDOR-Tests).
- **Admin-Zugriff:** nur lesend auf fremde Sammlungen. Jeder Zugriff landet im `audit_log`. Die Nutzer sehen einen Hinweis, dass Admins ihre Sammlung einsehen können (Transparenz).
- **Netzwerk:** Das Backend lauscht nur im Tailscale-Netz, nicht auf dem öffentlichen Interface. Die Firewall des VPS blockt alles außer Tailscale-UDP und SSH (oder SSH ebenfalls nur über Tailscale).
- **Härtung:** Rate-Limiting für Login und Scan, Upload-Größe und Dateityp begrenzt, Bilder werden nach der Verarbeitung **nicht gespeichert**, CORS nur auf die App-Origin, Security-Header, Dependency-Scans (`pip-audit`, Dependabot).
- **Secrets:** über `.env` und Docker-Secrets, nie im Repo.
- **Backups:** nächtliches `pg_dump` (verschlüsselt, 14 Tage Aufbewahrung) auf ein zweites Ziel. Das Wiederherstellen wird einmal getestet.
- **DSGVO-Light:** Es werden nur E-Mail und Sammlungsdaten gespeichert. Funktion „Konto und Daten löschen“.

---

## 8. Deployment und Verteilung (kostenlos, vorhandener Ubuntu-VPS)

### 8.1 Server
- Docker Compose mit den Diensten `db` (Postgres), `api`, `worker` und `tailscale` (eigenes Gerät „kartenkiste“, Userspace-Modus, Zustand im Volume `tailscale-state`). Ein Tailscale direkt auf dem VPS (andere Apps) bleibt unberührt.
- Die Serve-Konfiguration terminiert HTTPS mit einem Zertifikat unter `*.ts.net` und leitet auf `api:8000` weiter. Das ist nötig, weil Kamerazugriff im Browser **HTTPS** voraussetzt.
- Das Flutter-Web-Build wird als statische Dateien über denselben Dienst ausgeliefert.

### 8.2 Freunde einbinden
1. Jeder Freund installiert die kostenlose Tailscale-App (iOS und Android) und legt einen Tailscale-Account an.
2. Du teilst den Server per **Node-Sharing** mit ihm (alternativ lädst du ihn in dein Tailnet ein). Beim Free-Plan gelten Nutzer- und Geräte-Limits. **Das prüfe ich in Phase 0** gegen die aktuellen Tailscale-Bedingungen. Node-Sharing umgeht die Nutzergrenze des eigenen Tailnets.
3. Danach öffnet der Freund die App-URL, registriert sich mit dem Einladungscode und installiert die PWA über „Zum Home-Bildschirm“ (iOS) bzw. nutzt die Android-APK.

### 8.3 iOS-Besonderheiten der PWA
- Kamera nur über HTTPS und nur in Safari bzw. der installierten PWA.
- Kein TestFlight, kein App Store nötig.
- Einschränkung: Hintergrund-Verhalten und Push-Nachrichten sind eingeschränkt. Das brauchen wir nicht.

### 8.4 Android
- Signierte Release-APK über einen privaten Download-Link (im Tailnet). Alternativ ebenfalls als PWA.

---

## 9. Roadmap

Alle Aufwandsangaben sind grobe Schätzungen für einen Entwickler mit KI-Unterstützung.

### Phase 0: Spikes und Fundament (ca. 2–3 Tage)
- Repo-Grundgerüst, CI (ruff, mypy, pytest), pre-commit, Docker Compose lokal.
- **Spike Datenquellen:** TCGdex und pokemontcg.io abfragen. Prüfen: Felder, Sprachabdeckung (DE/EN/JP/KO/ZH), Cardmarket-Preisfelder, Rate-Limits, Produkt-Daten (versiegelt), Bild-URLs und -Größen.
- **Spike Tailscale:** Free-Plan-Limits, Node-Sharing, HTTPS-Zertifikat, PWA-Kamera auf iOS und Android mit einem Test-Endpoint.
- **Spike Scanner:** 20 Testfotos durch Konturerkennung und OCR.
- **Ergebnis:** Go/No-Go je Spike und ein aktualisierter Plan.

### Phase 1: Backend-Kern (ca. 1 Woche)
- DB-Modelle und Alembic-Migrationen.
- Auth: Registrierung mit Einladungscode, Login, Refresh-Rotation, Rollen, erster Admin per CLI-Befehl.
- Mandantentrennung und IDOR-Tests.
- Katalog-Sync (Sets und Karten, mehrsprachig) und Suche inklusive Name+Nummer-Parser.
- **Abnahme:** `pytest` grün, Suche `nachtara 215` liefert „Nachtara VMAX · Drachenwandel · 215“.

### Phase 2: Preise (ca. 4–5 Tage)
- `PriceProvider`-Interface, TCGdex-Cardmarket-Provider, Zustandsschätzer, manueller Preis.
- `price_point`-Historie, täglicher Snapshot-Worker, Tiefst- und Höchstpreis.
- Endpunkte für Preise und Preisverlauf.
- **Abnahme:** Preis mit Datum und Link, kein Preis wird erfunden, Schätzungen sind markiert.

### Phase 3: Sammlung, Merkliste, Dashboard (ca. 1 Woche)
- Ordner, Positionen (Menge, Kaufpreis, Notiz, Zustand, Sprache, Eigenpreis), Merkliste.
- `collection_events` und `portfolio_snapshot`, Dashboard-Endpunkt, CSV-Export.
- Rohkarten/Gegradet/Versiegelt-Aufteilung, eigene Produkte.
- **Abnahme:** Werte, Aufteilung und Kurve stimmen mit manuell berechneten Testdaten überein.

### Phase 4: Scanner (ca. 1–1,5 Wochen)
- Pipeline Schritte 1–6 (Einzelkarte), Evaluationsskript mit Testset, Tuning.
- Stapel-Scan, danach Binder-Scan (Beta) und Slab-OCR.
- **Abnahme:** Top-1 ≥ 85 % (DE/EN) auf dem Testset, Latenz ≤ 3 s pro Karte auf dem VPS.

### Phase 5: Flutter-App (ca. 2 Wochen, parallel ab Phase 1 möglich)
- Theme, Navigation (mit zentralem Scan-Button), Auth-Screens.
- Dashboard, Suche, Karten-Detail, Sammlung, Listen, Mehr-Menü.
- Scan-Screen (Kamera, Galerie, manuell), Stapel- und Binder-Modus.
- Admin-Screens: Nutzerliste, Einladungen, Sammlungs-Ansicht.
- PWA-Feinschliff (Manifest, Icons, Offline-Hülle), Android-APK-Build.
- **Abnahme:** Alle Kern-Flows auf iPhone (PWA) und Android durchgespielt.

### Phase 6: Deployment und Härtung (ca. 3–4 Tage)
- VPS einrichten, Compose, Tailscale-Sidecar, HTTPS, Firewall.
- Backups mit Wiederherstellungstest, Monitoring (Healthcheck, einfache Alerts).
- Last- und Sicherheitstests, Dokumentation für Freunde („So kommst du rein“).

### Phase 7: Nachbesserung (laufend)
- Scanner-Qualität verbessern (mehr Testfotos, besseres Matching). Aus Phase 4: Latenz ≤ 3 s auch bei Screenshots/ZH-Karten, Abnahme Top-1 ≥ 85 % DE/EN nachholen.
- Highlights (größter Gewinner und Verlierer), Zustandsfaktoren pro Nutzer, Feinschliff am UI.

**Gesamt:** ca. 7–9 Wochen Kalenderzeit bei Teilzeit, deutlich weniger bei Vollzeit.

---

## 10. Qualitätssicherung

- **Backend:** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest --cov` (Ziel ≥ 85 % für Services und Repositories).
- **Tests:** Unit-Tests für Parser, Preislogik und Scanner-Schritte. Integrationstests gegen echte Postgres-Instanz. Sicherheitstests für Rollen und Mandantentrennung.
- **Scanner-Evaluation:** reproduzierbares Skript mit fester Testfoto-Sammlung (nur privat, nicht im Repo, falls Fotos persönlich sind).
- **Frontend:** `flutter analyze`, Widget- und Golden-Tests.
- **CI:** GitHub Actions bei jedem Push. Merge nur bei grünem Stand.
- **Code-Stil:** Typannotationen überall, Docstrings für öffentliche Funktionen, kleine Module, keine Logik in Routern (nur in `services/`).

---

## 11. Risiken und Gegenmaßnahmen

| Risiko | Auswirkung | Gegenmaßnahme |
|---|---|---|
| Keine freie Quelle für Zustandspreise | Zustandspreise nur geschätzt | Schätzung klar markiert, Eigenpreis, Plug-in-Schnittstelle (z. B. offizielle Cardmarket-API bei Zugang) |
| Externe Plug-in-Quelle fällt aus | Keine externen Preise | Timeout, automatische Pause, Rückfall auf TCGdex + Schätzung, Hinweis im Admin-Bereich |
| TCGdex/pokemontcg.io ändern API oder Limits | Ausfall von Katalog oder Preisen | Provider-Abstraktion, lokale Kopie des Katalogs, Caching |
| OCR bei JP/KO/ZH und bei holografischen Karten schwach | Falsche oder keine Erkennung | Bildabgleich als zweites Signal, Kandidatenliste, „Selbst suchen“ |
| Sprachabdeckung der Datenquellen lückenhaft | Karten fehlen | Phase-0-Spike, manuelles Anlegen von Karten |
| Versiegelte Produkte ohne Datenquelle | Pflege von Hand | Eigene Produkte mit manuellem Preis |
| iOS-PWA-Kamera und Safari-Eigenheiten | Scan-UX schlechter als nativ | Früher Spike in Phase 0, Galerie-Upload als Fallback |
| Tailscale-Free-Limits | Zu viele Freunde nicht möglich | Spike in Phase 0, Node-Sharing, notfalls Headscale (selbst gehostet) |
| Urheberrecht an Kartenbildern | Rechtliches Risiko bei Veröffentlichung | Projekt bleibt privat. Bilder werden nur per Hotlink bzw. Cache genutzt, kein öffentlicher Zugang |
| Ein Nutzer fragt zu viele Scans ab | Last auf dem VPS | Rate-Limit pro Nutzer, Scan-Log |

---

## 12. Annahmen und offene Punkte

Diese Annahmen habe ich getroffen. Sie lassen sich leicht ändern:
1. Die App ist komplett auf **Deutsch**. Mehrsprachigkeit der UI ist nicht geplant.
2. Das Währungs-Format ist EUR. Preise stammen vom europäischen Markt (Cardmarket).
3. Der **erste Admin** wird beim Setup per CLI-Befehl angelegt, weitere Admins ernennt der Admin.
4. Es gibt **kein Wochen-Kontingent** für Scans, nur ein großzügiges Missbrauchs-Limit.
5. Der vorhandene Ubuntu-VPS reicht für Backend, DB und OCR (Richtwert: mindestens 2 vCPU und 4 GB RAM). Docker und Tailscale werden dort installiert.
8. Es gibt höchstens 5–10 Nutzer. Skalierung darüber hinaus ist nicht vorgesehen.
6. Domain: nicht nötig, da die Adresse unter `*.ts.net` über Tailscale läuft.
7. Entwicklung und Tests laufen hier im Repo. Den echten Gerätetest (iPhone und Android) und die VPS-Einrichtung musst du bzw. ihr mitmachen.

Noch zu klären (blockiert den Start nicht, wird in Phase 0 entschieden):
- Welche Sprachen die Datenquellen tatsächlich vollständig liefern (v. a. KO, ZH).
- Ob und woher es versiegelte Produkte gibt.
- Ob die Cardmarket-API für Privatpersonen noch freigeschaltet wird.
- Die Grenzen von Tailscale-Node-Sharing im Free-Plan (bei 5–10 Nutzern wahrscheinlich kein Problem, wird beim Deployment getestet).
- Ob Cardmarket die Angebotsseiten ohne Umgehung abrufbar lässt (wird im Preis-Spike getestet).

---

## 13. Nächste Schritte

1. Plan freigeben oder Änderungswünsche nennen.
2. Phase 0 starten: Repo-Gerüst, CI und die drei Spikes.
3. Danach Phase 1 (Backend-Kern) und parallel das Flutter-Grundgerüst.
