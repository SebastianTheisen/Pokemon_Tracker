import 'dart:typed_data';

import 'device.dart';

DeviceBridge createDeviceBridge() => const NoDevice();

/// Ohne Browser (Tests, Android-App ohne Web-Funktionen): nichts davon verfügbar.
class NoDevice implements DeviceBridge {
  const NoDevice();

  @override
  Future<bool> requestTilt() async => false;

  @override
  Stream<({double beta, double gamma})> tilt() => const Stream.empty();

  @override
  Future<ShareOutcome> shareImage(Uint8List png, String filename, String text) async =>
      ShareOutcome.failed;

  @override
  InstallState installState() => InstallState.none;

  @override
  Future<bool> install() async => false;
}
