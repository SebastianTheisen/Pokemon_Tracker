// Live-Kamera für den Scanner (Web: web/livescan.js; sonst nicht verfügbar).
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import 'live_camera_stub.dart' if (dart.library.js_interop) 'live_camera_web.dart' as impl;

enum CameraStart { ok, denied, unsupported }

abstract class LiveCamera {
  Future<CameraStart> start();

  void stop();

  /// Bewegung seit der letzten Messung und Abstand zum letzten Foto (je 0–255).
  ({double motion, double change}) measure();

  /// Aktuelles Bild als JPEG (wird als „letztes Foto“ gemerkt).
  Future<Uint8List?> frame();

  /// Kamerabild als Widget.
  Widget preview();
}

LiveCamera createLiveCamera() => impl.createLiveCamera();
