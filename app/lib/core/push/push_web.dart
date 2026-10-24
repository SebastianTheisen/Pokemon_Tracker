// Web: ruft window.kartenkistePush aus web/push.js auf.
import 'dart:convert';
import 'dart:js_interop';

import 'push_bridge.dart';

@JS('kartenkistePush')
external _JsPush? get _jsPush;

extension type _JsPush(JSObject _) implements JSObject {
  external JSPromise<JSString> status();
  external JSPromise<JSString> endpoint();
  external JSPromise<JSString> subscribe(JSString publicKey);
  external JSPromise<JSString> unsubscribe();
}

PushBridge createPushBridge() => const _WebPush();

class _WebPush implements PushBridge {
  const _WebPush();

  @override
  Future<PushStatus> status() async {
    final js = _jsPush;
    if (js == null) return PushStatus.unsupported;
    return parsePushStatus((await js.status().toDart).toDart);
  }

  @override
  Future<String?> endpoint() async {
    final js = _jsPush;
    if (js == null) return null;
    final value = (await js.endpoint().toDart).toDart;
    return value.isEmpty ? null : value;
  }

  @override
  Future<Map<String, Object?>> subscribe(String publicKey) async {
    final js = _jsPush;
    if (js == null) throw const PushException('Benachrichtigungen werden nicht unterstützt.');
    final result = (await js.subscribe(publicKey.toJS).toDart).toDart;
    if (result.startsWith('error:')) {
      final reason = result.substring(6);
      throw PushException(switch (reason) {
        'denied' =>
          'Benachrichtigungen sind für Kartenkiste blockiert – in den Einstellungen '
              'des Handys erlauben.',
        'default' => 'Benachrichtigungen wurden nicht erlaubt.',
        _ => 'Anmelden fehlgeschlagen: $reason',
      });
    }
    return (jsonDecode(result) as Map).cast<String, Object?>();
  }

  @override
  Future<String?> unsubscribe() async {
    final js = _jsPush;
    if (js == null) return null;
    final value = (await js.unsubscribe().toDart).toDart;
    return value.isEmpty ? null : value;
  }
}
