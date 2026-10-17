# Phase 4 – Ergebnisse vom VPS

- Datum: 2026-10-17 15:59 UTC
- Git-Stand: 61a94a2
- Health: `{"status":"ok","version":"0.1.0","database":"ok"}`
- Migration: `0004_scanner (head)`
- Worker: `worker running`
- Neue Tabellen: card_reference_images, scan_log
- Scanner-Volume: beschreibbar
- Scan-Protokoll nach der Evaluation (Erwartung 0): 0
- Merkmal-Cache-Dateien: 35

## OCR-Modelle

```
Standardmodell (PP-OCRv6): 2 Zeilen erkannt
Koreanisches Modell: 2 Zeilen erkannt
#18 [api base 10/11] RUN /srv/.venv/bin/python -m app.cli scanner-warmup --korean     || echo "WARNUNG: koreanisches OCR-Modell konnte nicht geladen werden"
#18 4.688 Standardmodell (PP-OCRv6): 2 Zeilen erkannt
#18 8.748 Koreanisches Modell: 2 Zeilen erkannt
#30 [worker base 10/11] RUN /srv/.venv/bin/python -m app.cli scanner-warmup --korean     || echo "WARNUNG: koreanisches OCR-Modell konnte nicht geladen werden"
```

## Speicher

```
pokemon_tracker-worker-1 75.29MiB / 11.68GiB
pokemon_tracker-api-1 89.67MiB / 11.68GiB
```

## Evaluation

- Kalt (erste Messung, lädt Katalogbilder): [`scan_eval_kalt.md`](scan_eval_kalt.md)
- Warm (mit Cache, entspricht dem Alltag): [`scan_eval_warm.md`](scan_eval_warm.md)

## Kennzahlen

- Fotos: 7 (davon 1 nicht im Katalog)
- **Top-1:** 5/6 (83 %)
- Top-5 (richtige Karte unter Treffer + Alternativen): 5/6 (83 %)
- Nicht im Katalog, richtig als unsicher erkannt: 1/1 (100 %)
- **Sicher, aber falsch:** 0
- Zeit pro Foto: Ø 2.71 s, max 4.57 s

## Abnahme (Plan Phase 4)

- Top-1 DE/EN: 1/1 (100 %) – Ziel ≥ 85 % ✅ (zu wenige Fotos für eine belastbare Aussage)
- Latenz ≤ 3 s: ❌ (max 4.57 s)


## Zugriffsschutz und Upload-Grenze

| Anfrage | HTTP | Erwartung |
|---|---|---|
| POST /api/v1/scan | 401 | 401 |
| POST /api/v1/scan/batch | 401 | 401 |
| POST /api/v1/scan/binder | 401 | 401 |
| GET /api/v1/scan/references | 401 | 401 |
| POST /api/v1/scan mit 40 MB | 413 | 413 |
