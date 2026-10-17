// Zentrale Provider: API-Client und Sitzung.
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import 'api.dart';
import 'config.dart';
import 'token_store.dart';

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

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
