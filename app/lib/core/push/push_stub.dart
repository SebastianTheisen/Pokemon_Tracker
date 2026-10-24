// Ohne Browser (Tests, Android-App): keine Web-Benachrichtigungen.
import 'push_bridge.dart';

PushBridge createPushBridge() => const _NoPush();

class _NoPush implements PushBridge {
  const _NoPush();

  @override
  Future<PushStatus> status() async => PushStatus.unsupported;

  @override
  Future<String?> endpoint() async => null;

  @override
  Future<Map<String, Object?>> subscribe(String publicKey) async =>
      throw const PushException('Benachrichtigungen gibt es nur in der Web-App.');

  @override
  Future<String?> unsubscribe() async => null;
}
