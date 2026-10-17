import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/config.dart';
import 'core/theme.dart';
import 'router.dart';

class KartenkisteApp extends ConsumerWidget {
  const KartenkisteApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: appName,
    debugShowCheckedModeBanner: false,
    theme: buildTheme(),
    darkTheme: buildTheme(),
    themeMode: ThemeMode.dark,
    locale: const Locale('de', 'DE'),
    supportedLocales: const [Locale('de', 'DE')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    routerConfig: ref.watch(routerProvider),
  );
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
