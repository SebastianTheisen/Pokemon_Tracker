# Recherche: weitere kostenlose Quellen für Kartendaten und Preise (18.10.2026)

Stand der Recherche: Websuche. Die Anbieterseiten selbst waren aus der Entwicklungsumgebung
nicht abrufbar. Die Angaben stammen deshalb aus Dokumentationsauszügen, Vergleichsartikeln
und GitHub-Projekten. Vor dem Einbau prüft ein Spike auf dem VPS jede Quelle direkt.

## Bereits genutzt

| Quelle | Inhalt | Kosten |
|---|---|---|
| TCGdex | Katalog alle Sprachen, Cardmarket- (EUR) und TCGplayer-Preise (USD) | frei, ohne Schlüssel |
| pokemontcg.io-Datensatz (GitHub) | englische Kartenbilder | frei |
| pokemon.com, pokemon-card.com, asia.pokemon-card.com | offizielle Bilder DE/EN/JP/TW | frei (nur Adressen, privat) |

## Kandidaten

| Quelle | Was | Kostenlos | Sprachen | Bewertung |
|---|---|---|---|---|
| **TCGCSV** (tcgcsv.com) | Täglicher Abzug aller TCGplayer-Preise (Market/Low/Mid/High, USD), JSON/CSV; Archiv seit 02/2024 | ja, ohne Schlüssel | EN (Kategorie 3), **Japan (Kategorie 85)** | **Top:** einzige freie Quelle mit Marktpreisen japanischer Karten plus Verlauf. Lücke: einige JP-Promos ohne Preis |
| **PokéWallet** (pokewallet.io) | TCGplayer- und Cardmarket-Preise, Kartendatenbank | Gratis-Schlüssel: 100/h, 1.000/Tag | EN, JP (Cardmarket bei JP leer) | gut als zweite Quelle bzw. Gegenprüfung |
| **PokemonPriceTracker** | TCGplayer, eBay-Verkäufe, **PSA-/BGS-Preise (gegradet)**, Verlauf | Gratis-Schlüssel: 100 Credits/Tag, Verlauf nur 3 Tage | EN, JP | interessant für **gegradete Karten** (eBay-Verkäufe) |
| **PokeTrace** | TCGplayer, eBay-Verkäufe, Cardmarket | Gratis: 250/Tag, nur US-Rohpreise | EN | wenig Mehrwert gegenüber TCGdex |
| tcgapi.dev | Preise inkl. JP, Verlauf (wöchentlich) | Gratis: 100/Tag | EN, JP | Reserve |
| TCG Price Lookup | Preise inkl. Pokémon Japan | Gratis-Stufe (nicht kommerziell), Grenze unklar | EN, JP | Reserve |
| pokemontcg.io API v2 | Karten + TCGplayer/Cardmarket-Preise | Gratis-Schlüssel 20.000/Tag | EN | geht in Scrydex auf, Zukunft unsicher; im Phase-1-Test Fehler 500 |

## Nicht geeignet

| Quelle | Grund |
|---|---|
| Cardmarket-API | nur gewerbliche Verkäufer, Anträge derzeit geschlossen; Webseite mit Cloudflare gesperrt |
| TCGplayer-API | für neue Entwickler geschlossen (TCGCSV ist der freie Weg zu diesen Daten) |
| eBay Marketplace Insights (Verkaufspreise) | nur für ausgewählte Partner; Browse-API (frei) zeigt nur laufende Angebote |
| PriceCharting, Scrydex | nur mit Bezahl-Abo |
| Japanische Shops (Yuyu-tei, Cardrush, Hareruya, SNKRDUNK) | keine offizielle API, nur Scraper Dritter (kostenpflichtig) |
| Korea | weiterhin keine Quelle (pokemoncard.co.kr-Schnittstelle abgeschaltet, TCGdex: Koreanisch „kommt bald“) |

## Vorschlag

1. **TCGCSV als Preis-Plug-in:** täglich USD-Marktpreise für englische und **japanische** Karten,
   Verlauf aus dem Archiv. Zuordnung TCGplayer-Produkt ↔ Katalogkarte über Set, Nummer und Name.
   Kein Schlüssel nötig.
2. **PokemonPriceTracker für gegradete Karten:** eBay-Verkaufspreise für PSA/BGS. Das passt zu
   den gegradeten Karten in den Sammlungen. Braucht einen kostenlosen Schlüssel (in die `.env`
   auf dem VPS). 100 Credits/Tag reichen bei 5–10 Nutzern nur für Karten in Sammlungen.
3. **PokéWallet als Gegenprüfung**, optional: zweite Quelle für TCGplayer/Cardmarket, falls
   TCGdex einmal ausfällt.

Alle Preise weiter nach der Regel „kein Beleg, kein Preis“: Quelle, Datum und Link.
