import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/config.dart';
import 'core/prefs.dart';
import 'core/theme.dart';
import 'router.dart';

final _lightTheme = buildTheme(Brightness.light);
final _darkTheme = buildTheme(Brightness.dark);

class KartenkisteApp extends ConsumerWidget {
  const KartenkisteApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: appName,
    debugShowCheckedModeBanner: false,
    theme: _lightTheme,
    darkTheme: _darkTheme,
    // Folgt dem Handy, außer unter Einstellungen fest gewählt.
    themeMode: ref.watch(uiPrefsProvider.select((prefs) => prefs.themeMode)),
    locale: const Locale('de', 'DE'),
    supportedLocales: const [Locale('de', 'DE')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    routerConfig: ref.watch(routerProvider),
    builder: (context, child) => _Palette(child: child ?? const SizedBox.shrink()),
  );
}

/// Stellt [AppColors] auf das aktive Erscheinungsbild. Beim Wechsel (Handy-Einstellung oder
/// Wahl in der App) werden alle Bildschirme einmal neu gezeichnet – auch die, die ihre Farben
/// nicht über `Theme.of` beziehen.
class _Palette extends StatelessWidget {
  const _Palette({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (AppColors.use(Theme.of(context).brightness)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        void rebuild(Element element) {
          element.markNeedsBuild();
          element.visitChildren(rebuild);
        }

        if (context.mounted) (context as Element).visitChildren(rebuild);
      });
    }
    return child;
  }
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
