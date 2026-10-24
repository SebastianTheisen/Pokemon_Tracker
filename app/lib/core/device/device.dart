// Gerätefunktionen (Web: web/device.js; sonst ohne Wirkung): Neigung, Teilen, Installieren.
import 'dart:typed_data';

import 'device_stub.dart' if (dart.library.js_interop) 'device_web.dart' as impl;

/// Ergebnis beim Teilen eines Bildes.
enum ShareOutcome { shared, downloaded, cancelled, failed }

/// Stand der Installation als App.
enum InstallState {
  /// Läuft schon als installierte App.
  installed,

  /// Browser bietet die Installation an (Android/Chrome) – ein Tipp genügt.
  prompt,

  /// iPhone/iPad in Safari: über „Teilen → Zum Home-Bildschirm“.
  ios,

  /// Keine Installation möglich oder nötig (z. B. Desktop ohne Angebot).
  none,
}

abstract class DeviceBridge {
  /// Erlaubnis für den Neigungssensor (iPhone: nur nach einem Tipp).
  Future<bool> requestTilt();

  /// Neigung vor/zurück und links/rechts in Grad, solange abonniert.
  Stream<({double beta, double gamma})> tilt();

  Future<ShareOutcome> shareImage(Uint8List png, String filename, String text);

  InstallState installState();

  Future<bool> install();
}

DeviceBridge createDeviceBridge() => impl.createDeviceBridge();
