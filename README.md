# Pokemon Tracker

Private Sammel-App für Pokémon-Karten: scannen, Sammlung verwalten, belegte Marktpreise sehen.

- Plan und aktueller Status: [`UMSETZUNGSPLAN.md`](UMSETZUNGSPLAN.md)
- Backend (Python/FastAPI): [`backend/`](backend/)
- App (Flutter): folgt in Phase 5

## Schnellstart (lokal, Docker)

```bash
cp .env.example .env   # Werte anpassen
docker compose up --build
curl http://127.0.0.1:8000/api/v1/health
```
