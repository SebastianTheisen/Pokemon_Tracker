// Web: ruft window.kartenkisteDevice aus web/device.js auf.
import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'device.dart';
import 'device_stub.dart';

@JS('kartenkisteDevice')
external _JsDevice? get _jsDevice;

extension type _JsDevice(JSObject _) implements JSObject {
  external JSPromise<JSBoolean> tiltPermission();
  external void tiltStart(JSFunction callback);
  external void tiltStop();
  external JSPromise<JSString> shareImage(JSUint8Array bytes, JSString filename, JSString text);
  external JSString installState();
  external JSPromise<JSBoolean> install();
}

DeviceBridge createDeviceBridge() => _jsDevice == null ? const NoDevice() : const _WebDevice();

class _WebDevice implements DeviceBridge {
  const _WebDevice();

  _JsDevice get _js => _jsDevice!;

  @override
  Future<bool> requestTilt() async {
    try {
      return (await _js.tiltPermission().toDart).toDart;
    } on Object {
      return false;
    }
  }

  @override
  Stream<({double beta, double gamma})> tilt() {
    late final StreamController<({double beta, double gamma})> controller;
    controller = StreamController(
      onListen: () => _js.tiltStart(
        ((JSNumber beta, JSNumber gamma) => controller.add((
          beta: beta.toDartDouble,
          gamma: gamma.toDartDouble,
        ))).toJS,
      ),
      onCancel: () => _js.tiltStop(),
    );
    return controller.stream;
  }

  @override
  Future<ShareOutcome> shareImage(Uint8List png, String filename, String text) async {
    try {
      final result = (await _js.shareImage(png.toJS, filename.toJS, text.toJS).toDart).toDart;
      return ShareOutcome.values.asNameMap()[result] ?? ShareOutcome.failed;
    } on Object {
      return ShareOutcome.failed;
    }
  }

  @override
  InstallState installState() {
    try {
      return InstallState.values.asNameMap()[_js.installState().toDart] ?? InstallState.none;
    } on Object {
      return InstallState.none;
    }
  }

  @override
  Future<bool> install() async {
    try {
      return (await _js.install().toDart).toDart;
    } on Object {
      return false;
    }
  }
}
