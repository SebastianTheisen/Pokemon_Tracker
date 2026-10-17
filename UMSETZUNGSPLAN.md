# Umsetzungsplan: Pokémon-Karten-Tracker (Arbeitstitel „Pokemon Tracker“)

Eine private Sammel-App im Stil von SCNDX: Pokémon-Karten scannen, Sammlung verwalten, belegte Marktpreise sehen. Sie ist für den Freundeskreis gedacht und wird nicht veröffentlicht.

Stand: 17.10.2026 · Status: **Phase 0 läuft**

---

## 0. Projektstatus (wird laufend gepflegt)

| Phase | Status | Notiz |
|---|---|---|
| 0 – Spikes und Fundament | 🟡 fast fertig | Alle Spikes ausgewertet. **Wartet auf:** 3 Entscheidungen (siehe Phase-0-Aufgaben), dann Abschluss |
| 1 – Backend-Kern | ⚪ offen | |
| 2 – Preise | ⚪ offen | |
| 3 – Sammlung, Merkliste, Dashboard | ⚪ offen | |
| 4 – Scanner | ⚪ offen | |
| 5 – Flutter-App | ⚪ offen | |
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
- [ ] ❓ Entscheidung Nutzer: pokemontcg.io streichen (Preise veraltet, Daten in TCGdex aktuell)?
- [ ] ❓ Entscheidung Nutzer: eigene Referenzbilder aus bestätigten Scans (schließt Bildlücken im Katalog)?
- [ ] ❓ Entscheidung Nutzer: fehlende Karten selbst anlegen können?
- [ ] Abschluss Phase 0: Go/No-Go je Spike festhalten, Plan anpassen, Phase 1 freigeben
- [ ] Spike Tailscale: laut Absprache verschoben, wird beim Deployment (Phase 6) getestet

**Regel:** Phase 1 beginnt erst, wenn alle Spike-Ergebnisse vorliegen und ausgewertet sind.

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

---

## 1. Festgelegte Entscheidungen

| Thema | Entscheidung |
|---|---|
| Frontend | **Flutter** (Dart): Android-APK plus **PWA (Flutter Web)** für iPhone |
| Backend | **Python 3.12**, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, PostgreSQL |
| Scanner | Serverseitig in Python: OpenCV (Kartenerkennung) + OCR + Bild-Matching, alles lokal und kostenlos |
| Karten-/Preisdaten | **TCGdex** (mehrsprachig, Cardmarket-Preisfelder) und **pokemontcg.io** als Ergänzung. Preise gelten nur mit Quelle, Datum und Link |
| Hosting | **Vorhandener VPS (Ubuntu)** mit Docker Compose |
| Nutzerzahl | **5–10 Nutzer** (Freundeskreis) |
| Zugang für Freunde | **Tailscale** (Free-Plan). Das Backend ist nicht öffentlich erreichbar, Freunde nutzen Node-Sharing |
| Nutzerverwaltung | Einladungscode + E-Mail/Passwort. Rollen: `user` und `admin` |
| Datenschutz | Jeder sieht nur seine Sammlung. Der Admin sieht die Nutzerliste und darf jede Sammlung **lesend** einsehen (mit Audit-Log) |
| Zustandspreise | TCGdex-Trend als NM-Referenz × Zustandsfaktor (als Schätzung markiert), Eigenpreis, Plug-in-Schnittstelle für weitere Quellen (Abschnitt 5.3) |
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
| `invite_codes` | code_hash, created_by, expires_at, used_by, used_at, revoked_at |
| `refresh_tokens` | id, user_id, token_hash, expires_at, revoked_at, replaced_by (Rotation) |
| `sets` | id, external_id, name_de/en/…, series, release_date, total_cards, logo_url |
| `cards` | id, external_id, set_id, number, language, name, name_de/en, rarity, image_url, search_vector (tsvector), phash |
| `products` | id, set_id, kind (`booster`, `bundle`, `etb`, `display`, `case` …), language, name, image_url, is_custom, created_by (für eigene Produkte) |
| `price_points` | id, item_type (`card`/`product`), item_id, source, kind (`verified`/`estimated`), condition (nullable), currency, value, fetched_at, source_url |
| `folders` | id, user_id, name, sort_order |
| `collection_items` | id, user_id, folder_id, item_type, card_id/product_id, language, condition, quantity, purchase_price, note, custom_price, grading_company, grade, added_at |
| `collection_events` | id, user_id, item_id, delta_quantity, value_at_event, created_at (Basis für die markierten Punkte) |
| `portfolio_snapshots` | id, user_id, date, total_value, raw_value, graded_value, sealed_value, item_count |
| `wishlist_items` | id, user_id, card_id/product_id, created_at |
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
- **Quelle:** TCGdex (REST, mehrsprachig, Karten mit Bild-URLs) als Hauptquelle. pokemontcg.io ergänzt die Daten, die dort besser sind.
- Worker `catalog_sync`:
  - Initialer Import aller Sets und Karten pro Sprache. Danach tägliche Inkremente anhand neuer Sets.
  - Volltextsuche über Postgres (`tsvector` + `pg_trgm`) für Tippfehler und gemischte DE/EN-Namen.
- Der Suchparser trennt Name und Nummer: `nachtara 215` → Name ≈ „nachtara“, Nummer = 215. Dazu kommen Formate wie `125/SM-P`, `215/203` und `SV9 12`.
- **Phase-0-Spike:** Die tatsächlichen Felder und Limits von TCGdex und pokemontcg.io prüfen (siehe Abschnitt 9). Dort liegt auch die Entscheidung, ob eine Quelle genügt.

### 5.2 Versiegelte Produkte
- Für Booster, Displays und Boxen ist **keine freie, strukturierte Quelle bekannt**. Das wird in Phase 0 geprüft.
- Fallback: Produkte lassen sich **selbst anlegen** (Name, Set, Typ, Bild) und mit **manuellem Preis** führen. Ein kleiner Seed-Katalog gängiger Produkttypen je Set kann ergänzt werden.

### 5.3 Preise: belegt, geschätzt, manuell
Grundregel wie im Original: **Wir erfinden keine Preise.** Jede Zahl trägt Typ, Quelle, Datum und Link.

*Entscheidung 17.10.2026 nach dem Datenquellen-Spike: Cardmarket blockt schon die erste direkte Anfrage per Cloudflare. Umgesetzt werden deshalb (a) Preise aus TCGdex plus markierte Schätzung und (b) eine Plug-in-Schnittstelle für weitere Preisquellen. Ein eigener Cardmarket-Abruf (mit oder ohne Tor) ist nicht Teil des Projekts.*

| Preis-Art | Herkunft | Anzeige |
|---|---|---|
| `verified` | TCGdex-Felder `pricing.cardmarket.*` (siehe unten), Datum aus `updated`, Link aus `idProduct` | „Cardmarket · Stand TT.MM.JJJJ“ + Link zur Produktseite |
| `estimated` | NM-Referenzpreis × Zustandsfaktor | deutlich als **„Schätzung“** markiert, nie als belegt summiert |
| `manual` | Eigener Preis des Nutzers | „Dein Preis“ |
| `external` | Optionale Plug-in-Quelle (siehe unten) | Name der Quelle + Datum + Link, wie vom Plug-in geliefert |

**TCGdex-Felder und ihre Verwendung** (je Variante: normal bzw. `*-holo` für Holo/Reverse):

| Feld | Anzeige in der App | Verwendung |
|---|---|---|
| `trend` | **Marktpreis (Trend)** | Hauptwert und **NM-Referenz** für die Schätzung. Fallback: `avg30`, dann `avg` |
| `low` | **Günstigstes Angebot** (beliebiger Zustand) | Info, nicht als NM-Preis verwenden. Im Spike: 220 € bei 1.806 € Trend |
| `avg1`, `avg7`, `avg30` | Durchschnitt 1/7/30 Tage | Detailansicht und Preisverlauf |

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
   3. **Bildabgleich** (pHash/Embedding) gegen die Katalogbilder der Kandidaten. Er ist zugleich Kontrolle und Rettungsweg, wenn kein Text lesbar ist (kleine Screenshots, Glitzerfolie).
6. **Slab-Pfad:** Wird ein Grading-Label erkannt (PSA/BGS/CGC), liest der Scanner Set, Name, Nummer und Note daraus. Die Karte wird als „gegradet“ vorgeschlagen.
7. **Ergebnis:** bester Treffer plus bis zu 4 Alternativen mit **Confidence-Score**. Bei niedriger Confidence zeigt die App „Falsche Karte? Selbst suchen“ und die Kandidatenliste.
8. **Stapel:** mehrere Bilder nacheinander durch dieselbe Pipeline, Ergebnisliste zum Bestätigen und Korrigieren.
9. **Binder-Seite (Beta):** Raster aus Karten erkennen (Konturen oder Gitterannahme 3×3/4×3), jede Zelle einzeln durch die Pipeline. Die Qualität schwankt, deshalb ist es als Beta markiert.
Gradete Karten werden immer zur Bestätigung angezeigt (siehe Schritt 6).

Qualitätsmessung: Ausgangsbasis ist der Testsatz in `scanner_testset/` (7 Fotos, mit Soll-Werten). Er wird schrittweise erweitert, Ziel sind mindestens 200 echte Fotos (verschiedene Sprachen, Licht, Hintergründe, Sleeves) mit erwarteten Karten. Das Skript `scripts/eval_scanner.py` gibt Top-1- und Top-5-Trefferquote aus. **Ziel Top-1 ≥ 85 %** auf deutschen und englischen Karten.

Katalog-Bildindex: Das Herunterladen von über 100.000 Kartenbildern ist teuer. Deshalb wird er **lazy** aufgebaut: Beim ersten Treffer eines Sets werden die Bilder dieses Sets in kleiner Auflösung geholt und gehasht. Ein Hintergrundjob füllt die häufigsten Sets vor.

---

## 6. API (Entwurf, `/api/v1`)

| Bereich | Endpunkte |
|---|---|
| Auth | `POST /auth/register` (mit Einladungscode), `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/change-password` |
| Katalog | `GET /cards/search?q=&lang=`, `GET /cards/{id}`, `GET /cards/{id}/prices?condition=`, `GET /cards/{id}/price-history`, `GET /sets`, `GET /products/search` |
| Scan | `POST /scan` (Bild), `POST /scan/batch`, `POST /scan/binder` |
| Sammlung | `GET /collection` (Filter, Sortierung, Gruppierung), `POST /collection/items`, `PATCH /collection/items/{id}`, `DELETE /collection/items/{id}`, `GET /collection/summary`, `GET /collection/history`, `GET /collection/export.csv` |
| Ordner | `GET/POST/PATCH/DELETE /folders` |
| Merkliste | `GET/POST/DELETE /wishlist` |
| Dashboard | `GET /dashboard` (Wert, Veränderung, Kennzahlen, Highlights) |
| Einstellungen | `GET/PATCH /me`, `GET/PATCH /me/settings` |
| Admin | `GET /admin/users`, `PATCH /admin/users/{id}` (sperren), `GET /admin/users/{id}/collection` (nur lesend), `POST /admin/invites`, `DELETE /admin/invites/{id}` |

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
- Docker Compose mit den Diensten `db` (Postgres), `api`, `worker` und `tailscale` (Sidecar).
- `tailscale serve` terminiert HTTPS mit einem Zertifikat unter `*.ts.net`. Das ist nötig, weil Kamerazugriff im Browser **HTTPS** voraussetzt.
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
- Scanner-Qualität verbessern (mehr Testfotos, besseres Matching).
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
