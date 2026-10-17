# Phase 3 – Ergebnisse vom VPS

- Datum: 2026-10-17 13:45 UTC
- Git-Stand: a0c9965
- Health: `{"status":"ok","version":"0.1.0","database":"ok"}`
- Migration: `0003_collection (head)`
- Worker: `worker running`
- Neue Tabellen: collection_events, collection_items, folders, portfolio_snapshots, products, wishlist_items
- Übrig gebliebene Probe-Ordner (Erwartung 0): 0

## Probe-Sammlung (echte Preise, zurückgerollt)

```
raw    2× Nachtara VMAX [NM]: 3611.80 € (estimated, median(trend, avg7, avg30) = 1805.90 × 1.00)
graded 1× Team Rockets Mewtu-ex [10]: 900.00 € (manual)
raw    1× Glurak [LP]: 232.87 € (estimated, median(trend, avg7, avg30) = 423.40 × 0.55)
sealed 1× Probe-Display [-]: 150.00 € (manual)
Gesamt: 4894.67 € · davon geschätzt 3844.67 € · roh 3844.67 € · gegradet 900.00 € · versiegelt 150.00 € · 4 Positionen / 5 Stück / 3 Sets
CSV-Export: 4 Zeilen
Probe zurückgerollt – keine Daten gespeichert.
```

## Zugriffsschutz ohne Anmeldung (Erwartung 401)

| Endpunkt | HTTP |
|---|---|
| /api/v1/folders | 401 |
| /api/v1/collection/items | 401 |
| /api/v1/collection/summary | 401 |
| /api/v1/collection/history | 401 |
| /api/v1/collection/export.csv | 401 |
| /api/v1/wishlist | 401 |
| /api/v1/dashboard | 401 |
| /api/v1/products | 401 |
