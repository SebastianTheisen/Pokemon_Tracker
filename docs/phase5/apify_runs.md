# Spike Apify, Stufe B: Testläufe

## Cardmarket · Glurak M6a japanisch NM (Link per idProduct)

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/de/Pokemon/Products?idProduct=907902", "language": "Japanese", "minCondition": "NM", "maxResults": 10}`
- Status: SUCCEEDED  · Dauer 46 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "card-listing": 0, "iq-analysis": 0})
- Ergebnisse: 0

## Cardmarket · Turtok-ex 151 deutsch NM

- Anbieter: `phantom_coder/cardmarket-listings-scraper`
- Eingabe: `{"productUrl": "https://www.cardmarket.com/de/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200", "language": "German", "minCondition": "NM", "maxResults": 10}`
- Status: SUCCEEDED  · Dauer 127 s
- Kosten: 5e-05 $ (Ereignisse: {"apify-actor-start": 1, "card-listing": 0, "iq-analysis": 0})
- Ergebnisse: 0

## Cardmarket · Turtok-ex 151 deutsch NM (zweiter Anbieter)

- Anbieter: `crawloop/cardmarket-listings-scraper`
- Eingabe: `{"startUrls": [{"url": "https://www.cardmarket.com/de/Pokemon/Products/Singles/151/Blastoise-ex-V3-MEW200"}], "language": "German", "minCondition": "NM", "locale": "de", "maxItems": 10, "maxPages": 1}`
- Status: FAILED No Cardmarket listings returned. On Apify use RESIDENTIAL proxy (Cloudflare blocks most datacenter IPs). Check keywords/URLs. · Dauer 96 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-actor-start": 2, "listing": 0})
- Ergebnisse: 0

## eBay.de verkauft · PSA 10 (meistgenutzt)

- Anbieter: `caffein.dev/ebay-sold-listings`
- Eingabe: `{"keywords": ["Glurak ex 151 PSA 10"], "ebaySite": "ebay.de", "daysToScrape": 90, "count": 20}`
- Status: SUCCEEDED Finished! Total 1 requests: 1 succeeded, 0 failed. · Dauer 13 s
- Kosten: 0.0001 $ (Ereignisse: {"apify-default-dataset-item": 0, "apify-actor-start": 2})
- Ergebnisse: 20
- Felder: ["bidCount", "buyingFormat", "category", "categoryId", "condition", "conditionId", "endedAt", "fullResThumbnailUrl", "isBestOfferAccepted", "itemId", "keyword", "listingType", "scrapedAt", "sellerFeedbackPercent", "sellerFeedbackScore", "sellerPositivePercent", "sellerType", "sellerUsername", "shippingCurrency", "shippingPrice", "shippingType", "soldCurrency", "soldPrice", "soldPriceMax", "thumbnailUrl", "title", "totalPrice", "updatedAt", "url"]
- Sprachen: {'None': 20} · Zustände: {'None': 17, 'Gebraucht': 3}
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 153.00 · 2026-10-18 · 7tkqd-84
  - 2023 Pokémon Glurak EX 199/165 - PSA 10 - 151 Mew Set - Deutsch MINT | Charizard · 1800.00 · 2026-10-17 · timbocards
  - PSA 10 Pokemon Karte Charizard EX Mint sv2a 006/165 151 · 74.90 · 2026-10-16 · pokebuds93
  - PSA 10 Pokemon Glumanda MEW 168/165 Karmesin & Purpur 151 Illustration Rare DE · 599.99 · 2026-10-15 · tcg-wonder
  - Pokémon TCG Charizard ex Sv2a Card 151 201/165 JP SAR Holo PSA 10 2023 · 555.00 · 2026-10-14 · srend-0
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 227.00 · 2026-10-12 · 6iv_ditto31
- Erster Eintrag vollständig: `{"title": "Glurak ex 183/165 151 Holo (Deutsch) PSA 10", "soldPrice": "153.00", "soldPriceMax": null, "soldCurrency": "EUR", "shippingPrice": null, "shippingCurrency": null, "totalPrice": "153.00", "endedAt": "2026-10-18", "itemId": "237119206427", "url": "https://www.ebay.de/itm/237119206427?nordt=true", "keyword": "Glurak ex 151 PSA 10", "categoryId": "0", "category": null, "shippingType": null, "condition": null, "conditionId": null, "sellerUsername": "7tkqd-84", "sellerPositivePercent": 100, "sellerFeedbackPercent": 100, "sellerFeedbackScore": 103, "scrapedAt": "2026-10-20T22:10:25.998Z", "updatedAt": "2026-10-20T22:10:26.053Z", "listingType": "auction", "isBestOfferAccepted": false, "thumbnailUrl": "https://i.ebayimg.com/images/g/dnsAAeSwuIlqy7ud/s-l500.webp", "sellerType": "private", "fullResThumbnailUrl": "https://i.ebayimg.com/images/g/dnsAAeSwuIlqy7ud/s-l1600.webp", "buyingForm…`

## eBay.de verkauft · PSA 10 (kostenloser Anbieter, Preisführer je Note)

- Anbieter: `yumitori/ebay-sold-scraper`
- Eingabe: `{"queries": ["Glurak ex 151 PSA 10"], "marketplace": "DE", "days": "90", "maxComps": 20}`
- Status: SUCCEEDED ✅ Done — 20 sold listings across 1/1 keyword(s) · Dauer 11 s
- Kosten: 0.002459596128841241 $ (Ereignisse: {})
- Ergebnisse: 20
- Felder: ["image_url", "item_id", "item_url", "price", "query", "scraped_at", "shipping", "shipping_cost", "sold_date", "title", "total_price"]
- Sprachen: {'None': 20} · Zustände: {'None': 20}
  - Pokémon TCG Charizard ex Sv2a Card 151 201/165 JP SAR Holo PSA 10 2023 · 621.27 · 2026-10-14
  - Glurak ex 183/165 151 Holo (Deutsch) PSA 10 · 253.63 · 2026-10-12
  - Charizard EX SR 185/165 Sv2a - PSA 10 Pokemon Card 151 2023 Japanese · 97.41 · 2026-10-10
  - Charizard/Glurak - 006/165 - UCG 10 No PSA - 151 - Gem Mint · 22.39 · 2026-10-08
  - CGC Pristine 10 Pokemon Charizard Glurak ex 006/165 Card 151 JP Holo 2023 RR PSA · 38.35 · 2026-10-04
  - Pokémon 151 Charizard ex SAR #201 Japanisch PSA 10 Gem Mint (SV2a) · 593.28 · 2026-10-04
- Erster Eintrag vollständig: `{"query": "Glurak ex 151 PSA 10", "title": "Pokémon TCG Charizard ex Sv2a Card 151 201/165 JP SAR Holo PSA 10 2023", "price": 621.27, "shipping": "$6.93", "shipping_cost": 6.93, "total_price": 628.2, "sold_date": "2026-10-14", "image_url": "https://i.ebayimg.com/images/g/v4sAAeSwGTNqxiFQ/s-l1600.png", "item_id": "189055665342", "item_url": "https://www.ebay.com/itm/189055665342", "scraped_at": "2026-10-20T22:10:29.275Z"}`

**Verbrauch diesen Monat danach: 0.0003247137621045113 $ von 5 $**

_Lauf: 2026-10-20 22:10 UTC, Stand 6534292_
