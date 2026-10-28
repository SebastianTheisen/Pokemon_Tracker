import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import 'live_camera.dart';

LiveCamera createLiveCamera() => const NoLiveCamera();

/// Ohne Browser: keine Live-Kamera (der normale Scanner bleibt).
class NoLiveCamera implements LiveCamera {
  const NoLiveCamera();

  @override
  Future<CameraStart> start() async => CameraStart.unsupported;

  @override
  void stop() {}

  @override
  ({double motion, double change}) measure() => (motion: 255, change: 0);

  @override
  Future<Uint8List?> frame({LiveGuide? guide}) async => null;

  @override
  Widget preview() => const SizedBox.shrink();
}
