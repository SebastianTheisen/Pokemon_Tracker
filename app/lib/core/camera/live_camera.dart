// Live-Kamera für den Scanner (Web: web/livescan.js; sonst nicht verfügbar).
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import 'live_camera_stub.dart' if (dart.library.js_interop) 'live_camera_web.dart' as impl;

enum CameraStart { ok, denied, unsupported }

/// Kartenrahmen in der Vorschau, als Anteile der Ansicht – zum Zeichnen und zum Zuschneiden
/// des Fotos (nur der Rahmen plus Rand geht zum Server: weniger Hintergrund, schnellere
/// Erkennung, und der Ausschnitt dient als Bestätigung).
class LiveGuide {
  const LiveGuide({
    required this.centerX,
    required this.centerY,
    required this.widthFraction,
    this.aspect = 88 / 63,
    this.margin = 0.12,
  });

  final double centerX;
  final double centerY;

  /// Breite des Rahmens als Anteil der Ansichtsbreite.
  final double widthFraction;

  /// Höhe : Breite (Karte 88 : 63).
  final double aspect;

  /// Zusätzlicher Rand beim Zuschneiden (Anteil der Rahmengröße je Seite).
  final double margin;

  Rect rect(Size size) {
    final width = size.width * widthFraction;
    return Rect.fromCenter(
      center: Offset(size.width * centerX, size.height * centerY),
      width: width,
      height: width * aspect,
    );
  }
}

const liveGuide = LiveGuide(centerX: 0.5, centerY: 0.45, widthFraction: 0.72);

abstract class LiveCamera {
  Future<CameraStart> start();

  void stop();

  /// Bewegung seit der letzten Messung und Abstand zum letzten Foto (je 0–255).
  ({double motion, double change}) measure();

  /// Aktuelles Bild als JPEG (wird als „letztes Foto“ gemerkt), zugeschnitten auf [guide].
  Future<Uint8List?> frame({LiveGuide? guide});

  /// Kamerabild als Widget.
  Widget preview();
}

LiveCamera createLiveCamera() => impl.createLiveCamera();
