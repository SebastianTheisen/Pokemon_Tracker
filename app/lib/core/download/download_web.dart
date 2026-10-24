import 'dart:js_interop';

@JS('kartenkisteDownload')
external JSBoolean? _download(JSString filename, JSString text, JSString mime);

bool saveTextFile(String filename, String text, String mime) {
  try {
    return _download(filename.toJS, text.toJS, mime.toJS)?.toDart ?? false;
  } on Object {
    return false; // Skript nicht geladen (z. B. alter Cache)
  }
}
