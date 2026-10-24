// Benachrichtigungen auf diesem Gerät (Web-Push der PWA) – plattformneutrale Schnittstelle.
import 'push_stub.dart' if (dart.library.js_interop) 'push_web.dart' as impl;

/// Stand der Benachrichtigungen auf diesem Gerät.
enum PushStatus {
  /// Browser kann kein Web-Push.
  unsupported,

  /// iPhone/iPad im Browser: erst „Zum Home-Bildschirm“, dann aus dem Symbol öffnen.
  install,

  /// Benachrichtigungen wurden für Kartenkiste abgelehnt (nur in den Systemeinstellungen änderbar).
  denied,

  /// Erlaubt.
  granted,

  /// Noch nicht gefragt.
  notAsked,
}

class PushException implements Exception {
  const PushException(this.message);

  final String message;

  @override
  String toString() => message;
}

abstract class PushBridge {
  Future<PushStatus> status();

  /// Endpunkt dieses Geräts, wenn angemeldet.
  Future<String?> endpoint();

  /// Erlaubnis holen und anmelden → Abo wie `PushSubscription.toJSON()`.
  Future<Map<String, Object?>> subscribe(String publicKey);

  /// Abmelden → bisheriger Endpunkt (für den Server).
  Future<String?> unsubscribe();
}

PushBridge createPushBridge() => impl.createPushBridge();

PushStatus parsePushStatus(String value) => switch (value) {
  'install' => PushStatus.install,
  'denied' => PushStatus.denied,
  'granted' => PushStatus.granted,
  'default' => PushStatus.notAsked,
  _ => PushStatus.unsupported,
};
