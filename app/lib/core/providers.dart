// Zentrale Provider: API-Client und Sitzung.
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import 'api.dart';
import 'camera/live_camera.dart';
import 'config.dart';
import 'device/device.dart';
import 'push/push_bridge.dart';
import 'token_store.dart';

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// Benachrichtigungen dieses Geräts (Web-Push); in Tests ersetzbar.
final pushBridgeProvider = Provider<PushBridge>((ref) => createPushBridge());

/// Live-Kamera des Scanners (Web); in Tests ersetzbar.
final liveCameraProvider = Provider<LiveCamera>((ref) => createLiveCamera());

/// Neigung, Teilen, Installieren (Web); in Tests ersetzbar.
final deviceProvider = Provider<DeviceBridge>((ref) => createDeviceBridge());

final apiProvider = Provider<Api>(
  (ref) => Api(baseUrl: apiBaseUrl(), tokens: ref.watch(tokenStoreProvider)),
);

/// Angemeldeter Nutzer (`null` = abgemeldet). Lädt beim Start die gespeicherte Sitzung.
class SessionController extends AsyncNotifier<User?> {
  Api get _api => ref.read(apiProvider);

  @override
  Future<User?> build() async {
    _api.onSessionExpired = () => state = const AsyncData(null);
    try {
      return await _api.restoreSession();
    } on ApiException {
      return null;
    }
  }

  Future<void> login(String email, String password) async {
    state = AsyncData(await _api.login(email.trim(), password));
  }

  Future<void> register({
    required String inviteCode,
    required String email,
    required String password,
    required String displayName,
  }) async {
    state = AsyncData(
      await _api.register(
        inviteCode: inviteCode.trim(),
        email: email.trim(),
        password: password,
        displayName: displayName.trim(),
      ),
    );
  }

  Future<void> refreshUser() async => state = AsyncData(await _api.me());

  Future<void> logout() async {
    await _api.logout();
    state = const AsyncData(null);
  }
}

final sessionProvider = AsyncNotifierProvider<SessionController, User?>(SessionController.new);

/// Wie lange geladene Daten nach dem letzten Zuschauer noch gelten. Verhindert, dass beim
/// Scrollen oder Reiterwechsel ständig neu geladen wird (Abschnitt kurz leer → Inhalt springt).
/// Änderungen laden trotzdem sofort neu – dort wird gezielt `invalidate` aufgerufen.
const providerCache = Duration(minutes: 2);

extension CacheFor on Ref {
  void cacheFor(Duration duration) {
    final link = keepAlive();
    final timer = Timer(duration, link.close);
    onDispose(timer.cancel);
  }
}

/// Für Provider in Kurzform: `(ref) => cached(ref, ref.watch(apiProvider).x())`.
T cached<T>(Ref ref, T value) {
  ref.cacheFor(providerCache);
  return value;
}
