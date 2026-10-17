# Spike: Datenquellen

## TCGdex – Sprachabdeckung

| Sprache | Sets | Beispielkarte vorhanden |
|---|---|---|
| de | 155 | ja |
| en | 220 | ja |
| ja | 186 | nein |
| ko | 95 | nein |
| zh-cn | 57 | nein |
| zh-tw | 98 | nein |

## TCGdex – Beispielkarte (de)

Name: **Nachtara VMAX**, Set: Drachenwandel, Nummer: 215
Bild-Basis-URL: `https://assets.tcgdex.net/de/swsh/swsh7/215`

Felder:

- `category`
- `id`
- `illustrator`
- `image`
- `localId`
- `name`
- `rarity`
- `set.cardCount.official`
- `set.cardCount.total`
- `set.id`
- `set.logo`
- `set.name`
- `set.symbol`
- `variants.firstEdition`
- `variants.holo`
- `variants.normal`
- `variants.reverse`
- `variants.wPromo`
- `variants_detailed`
- `dexId`
- `hp`
- `types`
- `evolveFrom`
- `stage`
- `abilities`
- `attacks`
- `weaknesses`
- `retreat`
- `regulationMark`
- `legal.standard`
- `legal.expanded`
- `updated`
- `pricing.cardmarket.updated`
- `pricing.cardmarket.unit`
- `pricing.cardmarket.idProduct`
- `pricing.cardmarket.avg`
- `pricing.cardmarket.low`
- `pricing.cardmarket.trend`
- `pricing.cardmarket.avg1`
- `pricing.cardmarket.avg7`
- `pricing.cardmarket.avg30`
- `pricing.cardmarket.avg-holo`
- `pricing.cardmarket.low-holo`
- `pricing.cardmarket.trend-holo`
- `pricing.cardmarket.avg1-holo`
- `pricing.cardmarket.avg7-holo`
- `pricing.cardmarket.avg30-holo`
- `pricing.tcgplayer.unit`
- `pricing.tcgplayer.updated`
- `pricing.tcgplayer.holofoil.productId`
- `pricing.tcgplayer.holofoil.lowPrice`
- `pricing.tcgplayer.holofoil.midPrice`
- `pricing.tcgplayer.holofoil.highPrice`
- `pricing.tcgplayer.holofoil.marketPrice`
- `pricing.tcgplayer.holofoil.directLowPrice`

Preisblock (Rohdaten):

```json
{
  "cardmarket": {
    "updated": "2026-10-16T08:51:36.595Z",
    "unit": "EUR",
    "idProduct": 574273,
    "avg": 1830.92,
    "low": 220,
    "trend": 1805.9,
    "avg1": 1150,
    "avg7": 2249.8,
    "avg30": 1772.15,
    "avg-holo": null,
    "low-holo": null,
    "trend-holo": 0,
    "avg1-holo": null,
    "avg7-holo": null,
    "avg30-holo": null
  },
  "tcgplayer": {
    "unit": "USD",
    "updated": "2026-10-15T08:51:55.117Z",
    "holofoil": {
      "productId": 246723,
      "lowPrice": 1699.99,
      "midPrice": 2264.7,
      "highPrice": 23406.19,
      "marketPrice": 2264.7,
      "directLowPrice": 2850
    }
  }
}
```

## TCGdex – asiatische Karten: Preise und Bilder (Stichprobe)

| Sprache | Set | Karte | Bild | Cardmarket-Preis | TCGplayer-Preis |
|---|---|---|---|---|---|
| ja | M-P (メガ プロモカード) | チコリータ · 001 | nein | trend 1.73 EUR | nein |
| ja | M-P (メガ プロモカード) | ラプラスex · 002 | nein | trend 2.22 EUR | nein |
| ja | M3 (ムニキスゼロ) | イトマル · 001 | nein | trend 0.02 EUR | nein |
| ja | M3 (ムニキスゼロ) | アリアドス · 002 | nein | trend 0.03 EUR | nein |
| zh-tw | SC1b (劍&盾 SET B) | 綠毛蟲 · 001 | nein | nein | nein |
| zh-tw | SC1b (劍&盾 SET B) | 鐵甲蛹 · 002 | nein | nein | nein |
| zh-tw | SDP (皮卡丘) | 皮卡丘V · 001 | ja | nein | nein |
| zh-tw | SDP (皮卡丘) | 小貓怪 · 002 | ja | nein | nein |
| zh-cn | SV9a (熱風競技場) | <阿響的>凱羅斯 · 001 | nein | nein | nein |
| zh-cn | SV9a (熱風競技場) | 蜻蜻蜓 · 002 | nein | trend 0.71 EUR | nein |
| zh-cn | SV7 (星晶奇跡) | 芭瓢蟲 · 001 | nein | trend 0.03 EUR | nein |
| zh-cn | SV7 (星晶奇跡) | 安瓢蟲 · 002 | nein | trend 0.19 EUR | nein |

## TCGdex – Bildabruf (`https://assets.tcgdex.net/de/swsh/swsh7/215`)

| Variante | HTTP | Größe | Typ |
|---|---|---|---|
| `low.webp` | 200 | 27 KB | image/webp |
| `high.webp` | 200 | 112 KB | image/webp |
| `high.png` | 200 | 326 KB | image/png |

## pokemontcg.io – Beispielkarte (en)

Name: **Umbreon VMAX**, Set: Evolving Skies
Rate-Limit-Header: `keiner`

Cardmarket-Block:

```json
{
  "url": "https://prices.pokemontcg.io/cardmarket/swsh7-215",
  "updatedAt": "2025/11/18",
  "prices": {
    "averageSellPrice": 1609.94,
    "lowPrice": 400.0,
    "trendPrice": 1579.48,
    "germanProLow": 0.0,
    "suggestedPrice": 0.0,
    "reverseHoloSell": 0.0,
    "reverseHoloLow": 0.0,
    "reverseHoloTrend": 0.0,
    "lowPriceExPlus": 975.0,
    "avg1": 790.0,
    "avg7": 1674.5,
    "avg30": 1538.35,
    "reverseHoloAvg1": 0.0,
    "reverseHoloAvg7": 0.0,
    "reverseHoloAvg30": 0.0
  }
}
```

## Cardmarket – Erreichbarkeit (1 Anfrage)

URL: `https://www.cardmarket.com/de/Pokemon/Products/Singles`
HTTP-Status: 403
Server-Header: `cloudflare`
Hinweise auf Bot-Sperre: Just a moment

