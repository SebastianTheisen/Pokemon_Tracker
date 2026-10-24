// Datei speichern (Web: Browser-Download über web/download.js; sonst nicht verfügbar).
import 'download_stub.dart' if (dart.library.js_interop) 'download_web.dart' as impl;

/// Gibt `false` zurück, wenn Speichern hier nicht möglich ist.
bool saveTextFile(String filename, String text, {String mime = 'text/plain;charset=utf-8'}) =>
    impl.saveTextFile(filename, text, mime);
