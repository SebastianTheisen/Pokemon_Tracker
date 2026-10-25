// Fremde Bilder über den eigenen Server laden: verkleinert und ohne CORS-Sonderweg.
//
// Hintergrund: Bildserver ohne CORS-Freigabe (z. B. pokemon-card.com) zwingen die Web-App,
// jedes Bild als eigenes HTML-Element einzubetten. In einem Set mit 200 Karten kostete das
// gemessen > 500 MB – iPhones beenden die App dann und starten sie neu.
import 'config.dart';

/// Adresse über `/api/v1/images` (Breite in physischen Pixeln) – `null`: direkt laden
/// (eigene Adressen, kein https).
String? proxiedImageUrl(String url, {required double logicalWidth, required double pixelRatio}) {
  final uri = Uri.tryParse(url);
  if (uri == null || uri.scheme != 'https') return null;
  final base = apiBaseUrl();
  if (url.startsWith(base)) return null;
  // Vorschaubilder: höchstens doppelte Pixeldichte – auf 3×-Displays kaum zu sehen, spart
  // aber mehr als die Hälfte Speicher je Bild.
  final ratio = logicalWidth < 200 && pixelRatio > 2 ? 2.0 : pixelRatio;
  final width = (logicalWidth * ratio).ceil().clamp(16, 2000);
  return '$base/api/v1/images?url=${Uri.encodeQueryComponent(url)}&w=$width';
}

/// Set-Logo als Bilddatei: TCGdex liefert Adressen ohne Endung (`…/logo` → `…/logo.webp`).
String setLogoUrl(String url) {
  final uri = Uri.tryParse(url);
  final last = uri?.pathSegments.lastOrNull ?? '';
  return uri?.host == 'assets.tcgdex.net' && !last.contains('.') ? '$url.webp' : url;
}
