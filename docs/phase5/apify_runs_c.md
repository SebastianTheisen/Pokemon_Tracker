# Spike Apify, Stufe C: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## Cardmarket · Turtok-ex 151 ohne Filter (englische Seite)

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200", "language": "any", "minCondition": "PO", "maxResults": 5}`
- Status: SUCCEEDED  · Dauer 33 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "card-listing": 0, "iq-analysis": 0})
- Ergebnisse: 5
- Felder: ["cardName", "condition", "currency", "eurUsdRate", "language", "price", "priceUsd", "productUrl", "quantity", "sellerComment", "sellerName"]
- Sprachen: {'Italian': 4, 'German': 1} · Zustände: {'GD': 2, 'EX': 3}
  - Blastoise ex MEW #200 · 69.99 · GD · Italian · thenutworldwide
  - Blastoise ex MEW #200 · 71.99 · EX · German · amazingtoys
  - Blastoise ex MEW #200 · 89.88 · GD · Italian · ShopponiStore
  - Blastoise ex MEW #200 · 89.89 · EX · Italian · Arcana-Trieste
  - Blastoise ex MEW #200 · 89.9 · EX · Italian · CardGameCorner
- Erster Eintrag vollständig: `{"cardName": "Blastoise ex MEW #200", "sellerName": "thenutworldwide", "condition": "GD", "language": "Italian", "quantity": 1, "price": 69.99, "currency": "EUR", "priceUsd": 78.49, "sellerComment": null, "eurUsdRate": 1.1215, "productUrl": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200?minCondition=8"}`

## Cardmarket · Turtok-ex 151 deutsch NM, Residential-Proxy DE

- Anbieter: `crawloop/cardmarket-listings-scraper`
- Eingabe: `{"startUrls": [{"url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200"}], "language": "German", "minCondition": "NM", "maxItems": 10, "maxPages": 1, "proxyConfiguration": {"useApifyProxy": true, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "DE"}}`
- Status: TIMED-OUT  · Dauer 300 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-actor-start": 2, "listing": 0})
- Ergebnisse: 0

## Cardmarket · Suche „Blastoise ex“ deutsch NM (Deal-Finder im Angebotsmodus)

- Anbieter: `lowlanddata/cardmarket-deal-finder`
- Eingabe: `{"searchQuery": "Blastoise ex", "minDiscountPct": 0, "languages": ["German"], "minCondition": "NM", "maxProducts": 1, "maxItems": 10}`
- Status: SUCCEEDED 0 offers delivered across 1 products (condition NM+). · Dauer 82 s
- Kosten: 0.005 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 1})
- Ergebnisse: 0

## eBay.de verkauft · Glurak ex 183/165 PSA 10 (mit Nummer)

- Anbieter: `caffein.dev/ebay-sold-listings`
- Eingabe: `{"keywords": ["Glurak 183/165 PSA 10"], "ebaySite": "ebay.de", "daysToScrape": 90, "count": 20}`
- Status: SUCCEEDED Finished! Total 1 requests: 1 succeeded, 0 failed. · Dauer 19 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 2})
- Ergebnisse: 20
- Felder: ["bidCount", "buyingFormat", "category", "categoryId", "condition", "conditionId", "endedAt", "fullResThumbnailUrl", "isBestOfferAccepted", "itemId", "keyword", "listingType", "scrapedAt", "sellerFeedbackPercent", "sellerFeedbackScore", "sellerPositivePercent", "sellerType", "sellerUsername", "shippingCurrency", "shippingPrice", "shippingType", "soldCurrency", "soldPrice", "soldPriceMax", "thumbnailUrl", "title", "totalPrice", "updatedAt", "url"]
- Sprachen: {'None': 20} · Zustände: {'Gebraucht': 9, 'None': 11}
  - Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch · 25.51 · Gebraucht · 2026-10-18 · wow--5737
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 153.00 · 2026-10-18 · 7tkqd-84
  - Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2 · 39.00 · Gebraucht · 2026-10-18 · monsterkarten
  - POKEMON KARTEN 151 DEUTSCH | Alle Karten Auswahl - NEAR MINT · 1.29 · Gebraucht · 2026-10-17 · sleeveede
  - Pokemon GLURAK Sammlung -einzelne Karten zur Auswahl - Deutsch in TOP Zustand · 7.99 · Gebraucht · 2026-10-17 · muebaland
  - Pokémon Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM · 37.99 · Gebraucht · 2026-10-15 · wojciolive
- Erster Eintrag vollständig: `{"title": "Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch", "soldPrice": "25.51", "soldPriceMax": null, "soldCurrency": "EUR", "shippingPrice": null, "shippingCurrency": null, "totalPrice": "25.51", "endedAt": "2026-10-18", "itemId": "407297300047", "url": "https://www.ebay.de/itm/407297300047?nordt=true", "keyword": "Glurak 183/165 PSA 10", "categoryId": "0", "category": null, "shippingType": null, "condition": "Gebraucht", "conditionId": 3000, "sellerUsername": "wow--5737", "sellerPositivePercent": 100, "sellerFeedbackPercent": 100, "sellerFeedbackScore": 513, "scrapedAt": "2026-10-20T22:19:19.646Z", "updatedAt": "2026-10-20T22:19:19.704Z", "listingType": "auction", "isBestOfferAccepted": false, "thumbnailUrl": "https://i.ebayimg.com/images/g/t-UAAeSw0jlq06vV/s-l500.webp", "sellerType": "private", "fullResThumbnailUrl": "https://i.ebayimg.com/images/g/t-UAAeSw0jl…`

## eBay.de verkauft · Glurak ex 183/165 Rohkarte

- Anbieter: `caffein.dev/ebay-sold-listings`
- Eingabe: `{"keywords": ["Glurak ex 183/165 -PSA -BGS -CGC"], "ebaySite": "ebay.de", "daysToScrape": 90, "count": 20}`
- Status: SUCCEEDED Finished! Total 1 requests: 1 succeeded, 0 failed. · Dauer 10 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 2})
- Ergebnisse: 6
- Felder: ["bidCount", "buyingFormat", "category", "categoryId", "condition", "conditionId", "endedAt", "fullResThumbnailUrl", "isBestOfferAccepted", "itemId", "keyword", "listingType", "scrapedAt", "sellerFeedbackPercent", "sellerFeedbackScore", "sellerPositivePercent", "sellerType", "sellerUsername", "shippingCurrency", "shippingPrice", "shippingType", "soldCurrency", "soldPrice", "soldPriceMax", "thumbnailUrl", "title", "totalPrice", "updatedAt", "url"]
- Sprachen: {'None': 6} · Zustände: {'Gebraucht': 6}
  - Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2 · 39.00 · Gebraucht · 2026-10-18 · monsterkarten
  - Pokémon Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM · 37.99 · Gebraucht · 2026-10-15 · wojciolive
  - Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM - Pokemon · 62.00 · Gebraucht · 2026-09-16 · egcd90
  - Pokemon Glurak ex Full Art | Deutsch MEW 183/165 Karmesin & Purpur 151 Near Mint · 54.99 · Gebraucht · 2026-09-08 · tcg-wonder
  - Pokemon Glurak ex Full Art | Deutsch MEW 183/165 Karmesin & Purpur 151 Near Mint · 54.99 · Gebraucht · 2026-09-03 · tcg-wonder
  - Pokemon Glurak ex Karmesin & Purpur 151  183/165 · 49.99 · Gebraucht · 2026-08-11 · jensiline
- Erster Eintrag vollständig: `{"title": "Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2", "soldPrice": "39.00", "soldPriceMax": null, "soldCurrency": "EUR", "shippingPrice": null, "shippingCurrency": null, "totalPrice": "39.00", "endedAt": "2026-10-18", "itemId": "407280793398", "url": "https://www.ebay.de/itm/407280793398?nordt=true", "keyword": "Glurak ex 183/165 -PSA -BGS -CGC", "categoryId": "0", "category": null, "shippingType": null, "condition": "Gebraucht", "conditionId": 3000, "sellerUsername": "monsterkarten", "sellerPositivePercent": 100, "sellerFeedbackPercent": 100, "sellerFeedbackScore": 43, "scrapedAt": "2026-10-20T22:19:30.127Z", "updatedAt": "2026-10-20T22:19:30.178Z", "listingType": "buy_it_now", "isBestOfferAccepted": false, "thumbnailUrl": "https://i.ebayimg.com/images/g/pSgAAeSwUrVqyj01/s-l500.webp", "sellerType": "private", "fullResThumbnailUrl": "https://i.ebayimg…`

**Verbrauch diesen Monat danach: 0.11320839645649991 $ von 5 $**

_Lauf: 2026-10-20 22:19 UTC, Stand 03d955c_
