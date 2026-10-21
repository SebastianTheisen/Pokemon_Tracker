# Spike Apify, Stufe E: Testläufe

- Verfügbare Proxy-Gruppen im Tarif: ['BUYPROXIES94952', 'GOOGLE_SERP', 'RESIDENTIAL', 'UNBLOCKER']

## eBay.de · caffein.dev Rohkarte (Ausschluss im Suchbegriff)

- Anbieter: `caffein.dev/ebay-sold-listings`
- Eingabe: `{"keywords": ["Glurak ex 183/165 -PSA -BGS -CGC"], "ebaySite": "ebay.de", "daysToScrape": 90, "count": 20}`
- Status: SUCCEEDED Finished! Total 1 requests: 1 succeeded, 0 failed. · Dauer 5 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 2})
- Ergebnisse: 20
- Felder: ["bidCount", "buyingFormat", "category", "categoryId", "condition", "conditionId", "endedAt", "fullResThumbnailUrl", "isBestOfferAccepted", "itemId", "keyword", "listingType", "scrapedAt", "sellerFeedbackPercent", "sellerFeedbackScore", "sellerPositivePercent", "sellerType", "sellerUsername", "shippingCurrency", "shippingPrice", "shippingType", "soldCurrency", "soldPrice", "soldPriceMax", "thumbnailUrl", "title", "totalPrice", "updatedAt", "url"]
- Sprachen: {'None': 20} · Zustände: {'Gebraucht': 20}
  - Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch · 25.51 · Gebraucht · 2026-10-18 · wow--5737
  - Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2 · 39.00 · Gebraucht · 2026-10-18 · monsterkarten
  - Pokémon 151 Glurak EX 183/165 · 34.50 · Gebraucht · 2026-10-18 · schloch83
  - Pokemon GLURAK Sammlung -einzelne Karten zur Auswahl - Deutsch in TOP Zustand · 7.99 · Gebraucht · 2026-10-17 · muebaland
  - Pokémon Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM · 37.99 · Gebraucht · 2026-10-15 · wojciolive
  - Pokémon TCG Glurak Charizard ex 151 MEW 183/165 Englisch Full Art · 32.00 · Gebraucht · 2026-10-13 · poketobi27
- Erster Eintrag vollständig: `{"title": "Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch", "soldPrice": "25.51", "soldPriceMax": null, "soldCurrency": "EUR", "shippingPrice": null, "shippingCurrency": null, "totalPrice": "25.51", "endedAt": "2026-10-18", "itemId": "407297300047", "url": "https://www.ebay.de/itm/407297300047?nordt=true", "keyword": "Glurak ex 183/165 -PSA -BGS -CGC", "categoryId": "0", "category": null, "shippingType": null, "condition": "Gebraucht", "conditionId": 3000, "sellerUsername": "wow--5737", "sellerPositivePercent": 100, "sellerFeedbackPercent": 100, "sellerFeedbackScore": 513, "scrapedAt": "2026-10-21T14:44:28.627Z", "updatedAt": "2026-10-21T14:44:28.709Z", "listingType": "auction", "isBestOfferAccepted": false, "thumbnailUrl": "https://i.ebayimg.com/images/g/t-UAAeSw0jlq06vV/s-l500.webp", "sellerType": "private", "fullResThumbnailUrl": "https://i.ebayimg.com/images/g/…`

## eBay.de · epicscrapers Rohkarte (Ausschlusswörter)

- Anbieter: `epicscrapers/ebay-sold-listings-api`
- Eingabe: `{"keywords": ["Glurak ex 183/165"], "excludeKeywords": ["PSA", "BGS", "CGC"], "site": "ebay.de", "maxItems": 20, "days": 90}`
- Status: SUCCEEDED Done: saved 20 sold listing(s) for 1 search(es) on ebay.de. See SUMMARY in the key-value store. · Dauer 6 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "apify-default-dataset-item": 0})
- Ergebnisse: 20
- Felder: ["bestOfferAccepted", "bidCount", "buyerProtectionFee", "categoryId", "categoryName", "condition", "conditionDetails", "currency", "displayedPrice", "freeReturns", "hasBestOffer", "imageUrl", "isPromoted", "itemLocation", "listingId", "listingType", "quantitySold", "returnsAccepted", "searchQuery", "searchUrl", "seller", "sellerType", "shippingIsEstimate", "shippingPrice", "shippingText", "site", "soldAt", "soldDateText", "soldPrice", "title", "totalPrice", "url"]
- Sprachen: {'None': 20} · Zustände: {'Gebraucht': 20}
  - Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch · 25.51 · Gebraucht · Verkauft 18. Okt 2026 · {"username": "wow--5737", "feedbackScore": 513, "feedbackPercent": 100, "isStore": false}
  - Pokémon TCG Glurak ex EX 183/165 Deutsch Holo 151 Double Rare KP 330 Phase 2 · 39 · Gebraucht · Verkauft 18. Okt 2026 · {"username": "monsterkarten", "feedbackScore": 44, "feedbackPercent": 100, "isStore": fal…
  - Pokémon 151 Glurak EX 183/165 · 34.5 · Gebraucht · Verkauft 18. Okt 2026 · {"username": "schloch83", "feedbackScore": 266, "feedbackPercent": 100, "isStore": false}
  - Pokémon Glurak / Charizard ex Full Art 183/165 Karmesin & Purpur 151 DE NM · 37.99 · Gebraucht · Verkauft 15. Okt 2026 · {"username": "wojciolive", "feedbackScore": 46, "feedbackPercent": 100, "isStore": false}
  - Pokémon TCG Glurak ex 183/165 – Edition 151 Holo Ultra Rare DE 330 KP · 33 · Gebraucht · Verkauft 11. Okt 2026 · {"username": "marml7106", "feedbackScore": 212, "feedbackPercent": 100, "isStore": false}
  - Pokémon TCG Glurak ex 183/165 Deutsch Holo Full Art KP 330 Phase 2 PLANETA · 32 · Gebraucht · Verkauft 2. Okt 2026 · {"username": "monsterkarten", "feedbackScore": 44, "feedbackPercent": 100, "isStore": fal…
- Erster Eintrag vollständig: `{"searchQuery": "Glurak ex 183/165", "searchUrl": null, "site": "ebay.de", "listingId": "407297300047", "title": "Pokémon Glurak ex 183/165 Full Art – Karmesin & Purpur 151 – Deutsch", "url": "https://www.ebay.de/itm/407297300047", "imageUrl": "https://i.ebayimg.com/images/g/t-UAAeSw0jlq06vV/s-l225.jpg", "soldPrice": 25.51, "currency": "EUR", "displayedPrice": 25.51, "buyerProtectionFee": null, "shippingPrice": null, "shippingIsEstimate": false, "shippingText": "Keine Angaben zum Versand", "totalPrice": null, "listingType": "auction", "bidCount": 6, "bestOfferAccepted": false, "condition": "Gebraucht", "conditionDetails": null, "categoryId": "183454", "categoryName": null, "soldAt": "2026-10-18T00:00:00.000Z", "soldDateText": "Verkauft 18. Okt 2026", "seller": {"username": "wow--5737", "feedbackScore": 513, "feedbackPercent": 100, "isStore": false}, "sellerType": null, "itemLocation": n…`

## Cardmarket-Suche · „Blastoise ex“ (Produkt-ID und Seite?)

- Anbieter: `lulzasaur/cardmarket-scraper`
- Eingabe: `{"searchQueries": ["Blastoise ex"], "game": "Pokemon", "maxResults": 30}`
- Status: SUCCEEDED Finished! Total 1 requests: 0 succeeded, 1 failed. · Dauer 91 s
- Kosten: 0.0002 $ (Ereignisse: {"apify-actor-start": 4, "apify-default-dataset-item": 0})
- Ergebnisse: 0

## Cardmarket-Suche · „Charizard“ 30th (Produkt-ID und Seite?)

- Anbieter: `lulzasaur/cardmarket-scraper`
- Eingabe: `{"searchQueries": ["Charizard 30th"], "game": "Pokemon", "maxResults": 30}`
- Status: SUCCEEDED Finished! Total 1 requests: 0 succeeded, 1 failed. · Dauer 83 s
- Kosten: 0.0002 $ (Ereignisse: {"apify-actor-start": 4, "apify-default-dataset-item": 0})
- Ergebnisse: 0

## Echte Kosten je Lauf (30 s nach dem letzten Lauf)

- eBay.de · caffein.dev Rohkarte (Ausschluss im Suchbegriff): **0.0801 $** {}
- eBay.de · epicscrapers Rohkarte (Ausschlusswörter): **0.07005 $** {}
- Cardmarket-Suche · „Blastoise ex“ (Produkt-ID und Seite?): **0.0002 $** {}
- Cardmarket-Suche · „Charizard“ 30th (Produkt-ID und Seite?): **0.0002 $** {}

**Verbrauch diesen Monat danach: 0.732186631376252 $ von 8 $**

_Lauf: 2026-10-21 14:48 UTC, Stand 101766d_
