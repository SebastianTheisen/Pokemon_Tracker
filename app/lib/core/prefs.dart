// Einstellungen dieses Geräts (nicht im Konto): Ansicht der Sammlung, Design, Anleitung gesehen.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class PrefsStore {
  Future<Map<String, String>> readAll();
  Future<void> write(String key, String value);
}

class SecurePrefsStore implements PrefsStore {
  const SecurePrefsStore([this._storage = const FlutterSecureStorage()]);

  static const _prefix = 'pref_';
  final FlutterSecureStorage _storage;

  @override
  Future<Map<String, String>> readAll() async => {
    for (final entry in (await _storage.readAll()).entries)
      if (entry.key.startsWith(_prefix)) entry.key.substring(_prefix.length): entry.value,
  };

  @override
  Future<void> write(String key, String value) => _storage.write(key: '$_prefix$key', value: value);
}

/// Für Tests (und als Rückfall, falls der Speicher nicht lesbar ist).
class MemoryPrefsStore implements PrefsStore {
  MemoryPrefsStore([Map<String, String>? values]) : values = values ?? {};

  final Map<String, String> values;

  @override
  Future<Map<String, String>> readAll() async => Map.of(values);

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

final prefsStoreProvider = Provider<PrefsStore>((ref) => const SecurePrefsStore());

@immutable
class UiPrefs {
  const UiPrefs({
    this.loaded = false,
    this.listView = false,
    this.themeMode = ThemeMode.system,
    this.onboarded = false,
  });

  /// Erst nach dem Laden entscheiden (sonst blitzt z. B. die Anleitung kurz auf).
  final bool loaded;

  /// Sammlung als Liste statt Raster.
  final bool listView;
  final ThemeMode themeMode;

  /// Erst-Start-Anleitung gesehen.
  final bool onboarded;

  UiPrefs copyWith({bool? loaded, bool? listView, ThemeMode? themeMode, bool? onboarded}) =>
      UiPrefs(
        loaded: loaded ?? this.loaded,
        listView: listView ?? this.listView,
        themeMode: themeMode ?? this.themeMode,
        onboarded: onboarded ?? this.onboarded,
      );
}

class UiPrefsController extends Notifier<UiPrefs> {
  PrefsStore get _store => ref.read(prefsStoreProvider);

  @override
  UiPrefs build() {
    _load();
    return const UiPrefs();
  }

  Future<void> _load() async {
    Map<String, String> values;
    try {
      values = await _store.readAll();
    } on Object {
      values = const {}; // z. B. gesperrter Browser-Speicher: mit Standardwerten weiter
    }
    state = UiPrefs(
      loaded: true,
      listView: values['list_view'] == 'true',
      themeMode: ThemeMode.values.asNameMap()[values['theme']] ?? ThemeMode.system,
      onboarded: values['onboarded'] == 'true',
    );
  }

  Future<void> _save(String key, String value) async {
    try {
      await _store.write(key, value);
    } on Object {
      // Nicht speicherbar: gilt dann nur bis zum Schließen der App.
    }
  }

  void setListView({required bool value}) {
    state = state.copyWith(listView: value);
    _save('list_view', '$value');
  }

  void setThemeMode(ThemeMode mode) {
    state = state.copyWith(themeMode: mode);
    _save('theme', mode.name);
  }

  void finishOnboarding() {
    state = state.copyWith(onboarded: true);
    _save('onboarded', 'true');
  }
}

final uiPrefsProvider = NotifierProvider<UiPrefsController, UiPrefs>(UiPrefsController.new);
