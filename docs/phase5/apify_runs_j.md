# Spike Apify, Stufe J: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## Set-Seite · incognito_mode collection

- Anbieter: `incognito_mode/pricecharting-collection-scraper`
- Eingabefelder: ["collections", "includePriceHistory", "includeProducts", "maxConcurrency", "maxItems", "maxProductsPerCollection", "maxRunSecs", "proxyConfiguration", "requestDelaySecs"]
- Eingabe: `{"collections": ["https://www.pricecharting.com/console/pokemon-korean-electric-breaker", "https://www.pricecharting.com/console/pokemon-chinese-gem-pack"], "maxItems": 400}`
- Status: SUCCEEDED Scraped 2/2 collection(s) · Dauer 6 s
- Kosten: 5e-05 $ (Ereignisse: {"collection-result": 0, "collection-result-bulk": 0, "apify-actor-start": 1})
- Ergebnisse: 2
- Felder: ["breadcrumb", "category", "collectionName", "collectionUrl", "consoleUid", "currency", "currentMedian", "currentValue", "medianHistory", "priceColumns", "productCount", "products", "scrapedAt", "source", "valueHistory"]
- Sprachen: {'None': 2} · Zustände: {'None': 2}
  - Pokemon Chinese Gem Pack · {"used": "Ungraded", "cib": "Grade 9", "new": "PSA 10"}
  - Pokemon Korean Electric Breaker · {"used": "Ungraded", "cib": "Grade 9", "new": "PSA 10"}
- Erster Eintrag vollständig: `{"collectionUrl": "https://www.pricecharting.com/console/pokemon-chinese-gem-pack", "collectionName": "Pokemon Chinese Gem Pack", "category": "pokemon-cards", "consoleUid": "G79200", "breadcrumb": ["Trading Cards", "Pokemon Card", "Pokemon Chinese Gem Pack"], "currency": "USD", "priceColumns": {"used": "Ungraded", "cib": "Grade 9", "new": "PSA 10"}, "productCount": 118, "currentValue": 13.19, "currentMedian": 1.98, "valueHistory": [{"date": "2025-04-02", "price": 8.22}, {"date": "2025-05-02", "price": 10.12}, {"date": "2025-06-02", "price": 10.03}, {"date": "2025-07-02", "price": 11.03}, {"date": "2025-08-02", "price": 17.28}, {"date": "2025-09-02", "price": 16.5}, {"date": "2025-10-02", "price": 17.15}, {"date": "2025-11-02", "price": 16.12}, {"date": "2025-12-02", "price": 14.11}, {"date": "2026-01-02", "price": 13.4}, {"date": "2026-02-02", "price": 13.94}, {"date": "2026-03-02", "price": 14.4}, {"date": "2026-05-02", "price": 14.57}, {"date": "2026-06-02", "price": 16.17}, {"date": "2026-07-02", "price": 17.32}, {"date": "2026-08-02", "price": 14.31}, {"date": "2026-09-02", "price": 13.59}, {"date": "2026-10-02", "price": 13.19}], "medianHistory": [{"date": "2025-04-02", "price": 2.9}, {"date": "2025-05-02", "price": 2.87}, {"date": "2025-06-02", "price": 2.42}, {"date": "2025-07-02", "price": 2.98}, {"date": "2025-08-02", "price": 2.86}, {"date": "2025-09-02", "price": 2.46}, {"date": "2025-10-02", "price": 2.42}, {"date": "2025-11-02", "price": 2.4}, {"date": "2025-12-02", "price": 2.11}, {"date": "2026-01-02", "price": 2.22}, {"date": "2026-02-02", "price": 2.29}, {"date": "2026-03-02", "price": 2.39}, {"date": "2026-05-02", "price": 2.25}, {"date": "2026-06-02", "price": 2.05}, {"date": "2026-07-02", "price": 2.12}, {"date": "2026-08-02", "price": 2.08}, {"date": "2026-09-02", "price": 1.99}, {"date": "2026-10-02", "price": 1.98}], "products": [{"productId": 8927090, "productName": "Captain Pikachu #709", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/captain-pikachu-709", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/lolpggjyb7lkkt3a/1600.jpg", "prices": {"used": 202.43, "cib": 223, "new": 582.92}}, {"productId": 8710188, "productName": "Pikachu [Full Art] #708", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/pikachu-full-art-708", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/eq7gov42b66gh3lg/1600.jpg", "prices": {"used": 20.03, "cib": 39.23, "new": 74.27}}, {"productId": 8710136, "productName": "Sprigatito [Horizons Full Art] #109", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/sprigatito-horizons-full-art-109", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/27bvljvln66ixpot/1600.jpg", "prices": {"used": 37.99, "cib": 44, "new": 112}}, {"productId": 8710186, "productName": "Pikachu [Shiny] #706", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/pikachu-shiny-706", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/mtxobcikzpgyxjpn/1600.jpg", "prices": {"used": 8.05, "cib": 18.87, "new": 77.23}}, {"productId": 8710185, "productName": "Captain Pikachu [Masterball] #705", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/captain-pikachu-masterball-705", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/cpjtdyujdejkdlvt/1600.jpg", "prices": {"used": 3.95, "cib": 28, "new": 68.5}}, {"productId": 8710153, "productName": "Fuecoco [Horizons Full Art] #309", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/fuecoco-horizons-full-art-309", "imageUrl": "https://storage.googleapis.com/images.pricecharting.com/otvf75zwclt4o5zx/1600.jpg", "prices": {"used": 22.32, "cib": 32.91, "new": 92.09}}, {"productId": 8710180, "productName": "Captain Pikachu #701", "url": "https://www.pricecharting.com/game/pokemon-chinese-gem-pack/captain-pikachu-701", "imageUrl": "https://storage.googleapis.com/images.pricecharting.co…`

## Set-Seite · crawloop

- Anbieter: `crawloop/pricecharting-scraper`
- Eingabefelder: ["category", "concurrency", "detailLevel", "includeCollectionStats", "includeFullPrices", "includeImages", "includePopulation", "includePriceHistory", "includeRecentSales", "maxItems", "mode", "proxyConfiguration", "requestDelaySecs", "searchQueries", "startUrls"]
  - `mode`: ["auto", "search", "product_urls", "collection_urls", "mixed_urls"] (Standard auto)
  - `detailLevel`: ["listings", "details"] (Standard details)
  - `category`: ["all", "video-games", "pokemon-cards", "magic-cards", "yugioh-cards", "lorcana-cards", "one-piece-cards", "digimon-cards", "dragon-ball-cards", "marvel-cards", "star-wars-cards", "other-tcg-cards", … (Standard all)
- Eingabe: `{"startUrls": [{"url": "https://www.pricecharting.com/console/pokemon-korean-electric-breaker"}, {"url": "https://www.pricecharting.com/console/pokemon-chinese-gem-pack"}], "mode": "collection_urls", "maxItems": 400, "includeImages": true, "includeFullPrices": true}`
- Status: SUCCEEDED  · Dauer 176 s
- Kosten: 0.045 $ (Ereignisse: {"apify-actor-start": 1, "listing-result": 0, "product-result": 0, "collection-result": 1})
- Ergebnisse: 12
- Felder: ["category", "collectionName", "collectionUrl", "consoleUid", "currency", "currentMedian", "currentValue", "medianHistory", "priceColumns", "recordType", "scrapedAt", "valueHistory"]
- Sprachen: {'None': 12} · Zustände: {'None': 12}
  - Prices for Pokemon Korean Electric Breaker Pokemon Cards · {"loose": "Grade 9", "cib": "PSA 10", "new": "New / PSA 10"}
  - 10064378 · {"loose": 2.99, "cib": null, "new": null, "graded": 12.99, "boxOnly": 14, "manualOnly": 3…
  - 10064476 · {"loose": 182.44, "cib": null, "new": null, "graded": 157.5, "boxOnly": 173, "manualOnly"…
  - 10064436 · {"loose": 6.9, "cib": null, "new": null, "graded": 20.83, "boxOnly": 23, "manualOnly": 49…
  - 10064440 · {"loose": 6.28, "cib": null, "new": null, "graded": 21.5, "boxOnly": 24, "manualOnly": 50…
  - 10064447 · {"loose": 4.2, "cib": null, "new": null, "graded": 16.59, "boxOnly": 18, "manualOnly": 47…
- Erster Eintrag vollständig: `{"recordType": "collection", "collectionUrl": "https://www.pricecharting.com/console/pokemon-korean-electric-breaker", "collectionName": "Prices for Pokemon Korean Electric Breaker Pokemon Cards", "category": "pokemon-cards", "consoleUid": "G82642", "priceColumns": {"loose": "Grade 9", "cib": "PSA 10", "new": "New / PSA 10"}, "currentValue": 713, "currentMedian": 199, "valueHistory": [{"date": "2025-08-02", "price": 1828}, {"date": "2025-09-02", "price": 723}, {"date": "2025-10-02", "price": 716}, {"date": "2025-11-02", "price": 696}, {"date": "2025-12-02", "price": 700}, {"date": "2026-01-02", "price": 695}, {"date": "2026-02-02", "price": 756}, {"date": "2026-03-02", "price": 705}, {"date": "2026-05-02", "price": 633}, {"date": "2026-06-02", "price": 663}, {"date": "2026-07-02", "price": 730}, {"date": "2026-08-02", "price": 713}, {"date": "2026-09-02", "price": 708}, {"date": "2026-10-02", "price": 713}], "medianHistory": [{"date": "2025-08-02", "price": 400}, {"date": "2025-09-02", "price": 284}, {"date": "2025-10-02", "price": 264}, {"date": "2025-11-02", "price": 230}, {"date": "2025-12-02", "price": 222}, {"date": "2026-01-02", "price": 220}, {"date": "2026-02-02", "price": 200}, {"date": "2026-03-02", "price": 200}, {"date": "2026-05-02", "price": 200}, {"date": "2026-06-02", "price": 200}, {"date": "2026-07-02", "price": 200}, {"date": "2026-08-02", "price": 200}, {"date": "2026-09-02", "price": 200}, {"date": "2026-10-02", "price": 199}], "currency": "USD", "scrapedAt": "2026-10-21T20:43:20Z"}`

## Echte Kosten je Lauf (30 s nach dem letzten Lauf)

- Set-Seite · incognito_mode collection: **0.020050000000000002 $** {}
- Set-Seite · crawloop: **0.1 $** {}

**Verbrauch diesen Monat danach: 1.5671130941926117 $ von 8 $**

_Lauf: 2026-10-21 20:46 UTC, Stand edba81b_
