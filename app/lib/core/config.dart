// Adresse des Backends.
//
// * Web (PWA): Die App wird vom Backend selbst ausgeliefert → gleiche Adresse.
// * Android: beim Bauen festlegen, z. B.
//   `flutter build apk --dart-define=API_BASE_URL=https://kartenkiste.<tailnet>.ts.net`
import 'package:flutter/foundation.dart';

const _configured = String.fromEnvironment('API_BASE_URL');

String apiBaseUrl() {
  if (_configured.isNotEmpty) {
    return _configured.endsWith('/')
        ? _configured.substring(0, _configured.length - 1)
        : _configured;
  }
  if (kIsWeb) return Uri.base.origin;
  return 'http://10.0.2.2:8000'; // Android-Emulator → Rechner
}

const appName = 'Kartenkiste';
