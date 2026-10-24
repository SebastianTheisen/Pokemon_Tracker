import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Dekodierte Bilder im Speicher begrenzen (Standard 100 MB): Handy-Browser beenden Seiten,
  // die zu viel belegen – lange Set-Listen laden Bilder beim Zurückscrollen einfach neu.
  PaintingBinding.instance.imageCache.maximumSizeBytes = 48 << 20;
  await initializeDateFormatting('de_DE');
  runApp(
    // Fehlgeschlagene Anfragen nicht automatisch wiederholen (Riverpod 3 tut das sonst).
    ProviderScope(retry: (_, _) => null, child: const KartenkisteApp()),
  );
}
