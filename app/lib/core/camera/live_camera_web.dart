// Web: window.kartenkisteCamera aus web/livescan.js; das <video> wird als Plattform-Ansicht
// eingebettet (ein einziges Element – unkritisch, anders als viele Bild-Elemente).
import 'dart:js_interop';
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';

import 'live_camera.dart';
import 'live_camera_stub.dart';

@JS('kartenkisteCamera')
external _JsCamera? get _jsCamera;

extension type _JsCamera(JSObject _) implements JSObject {
  external JSObject createVideo();
  external JSPromise<JSString> start();
  external void stop();
  external JSString measure(
    JSNumber centerX,
    JSNumber centerY,
    JSNumber widthFraction,
    JSNumber aspect,
    JSNumber margin,
  );
  external JSUint8Array? lastCrop();
  external JSPromise<JSUint8Array?> frame(
    JSNumber centerX,
    JSNumber centerY,
    JSNumber widthFraction,
    JSNumber aspect,
    JSNumber margin,
  );
}

const _viewType = 'kartenkiste-camera';

/// Ohne Rahmen: ganzes Bild (Breite 0 = nicht zuschneiden, keine Kartenprüfung).
const _wholeImage = LiveGuide(centerX: 0.5, centerY: 0.5, widthFraction: 0);
bool _registered = false;

LiveCamera createLiveCamera() => _jsCamera == null ? const NoLiveCamera() : const _WebCamera();

class _WebCamera implements LiveCamera {
  const _WebCamera();

  _JsCamera get _js => _jsCamera!;

  @override
  Future<CameraStart> start() async {
    try {
      final result = (await _js.start().toDart).toDart;
      return CameraStart.values.asNameMap()[result] ?? CameraStart.unsupported;
    } on Object {
      return CameraStart.unsupported;
    }
  }

  @override
  void stop() => _js.stop();

  @override
  ({double motion, double change, bool card}) measure({LiveGuide? guide}) {
    final g = guide ?? _wholeImage;
    final parts = _js
        .measure(g.centerX.toJS, g.centerY.toJS, g.widthFraction.toJS, g.aspect.toJS, g.margin.toJS)
        .toDart
        .split(',');
    return (
      motion: double.tryParse(parts.first) ?? 255,
      change: parts.length > 1 ? double.tryParse(parts[1]) ?? 0 : 0,
      card: parts.length > 2 && parts[2] == '1',
    );
  }

  @override
  Uint8List? lastCrop() => _js.lastCrop()?.toDart;

  @override
  Future<Uint8List?> frame({LiveGuide? guide}) async {
    final g = guide ?? _wholeImage;
    final bytes = await _js
        .frame(g.centerX.toJS, g.centerY.toJS, g.widthFraction.toJS, g.aspect.toJS, g.margin.toJS)
        .toDart;
    return bytes?.toDart;
  }

  @override
  Widget preview() {
    if (!_registered) {
      ui_web.platformViewRegistry.registerViewFactory(_viewType, (_) => _js.createVideo());
      _registered = true;
    }
    return const HtmlElementView(viewType: _viewType);
  }
}
