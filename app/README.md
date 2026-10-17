# Kartenkiste (Flutter-App)

Android-APK und PWA (Flutter Web) für das Backend in `../backend`. Status und Plan: [`../UMSETZUNGSPLAN.md`](../UMSETZUNGSPLAN.md).

## Entwicklung

```bash
cd app
flutter pub get
flutter analyze
flutter test
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

- **Web:** Die App wird vom Backend unter `/` ausgeliefert (gleiche Adresse, kein CORS). `API_BASE_URL` ist dann nicht nötig.
- **Android:** `flutter build apk --dart-define=API_BASE_URL=https://kartenkiste.<tailnet>.ts.net`
- Auf dem VPS baut `bash deploy/phase5_app.sh` beides im Container `app-builder`.
- Icons neu erzeugen: `../backend/.venv/bin/python tool/make_icons.py`

## Aufbau

| Ordner | Inhalt |
|---|---|
| `lib/core` | Theme, Konfiguration, API-Client (Token-Erneuerung), Provider, Formatierung |
| `lib/models` | Datenmodelle der API |
| `lib/features` | Screens: Anmeldung, Übersicht, Suche, Karte, Sammlung, Merkliste, Scanner, Mehr, Admin |
| `lib/widgets` | Gemeinsame Bausteine (Kartenbild, Chart, Fehleranzeige …) |
| `test` | Widget- und API-Tests mit Attrappen (kein Netzwerk) |
