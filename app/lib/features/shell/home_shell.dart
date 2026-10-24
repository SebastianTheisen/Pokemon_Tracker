// Untere Navigation: Übersicht, Sammlung, zentraler Scan-Button, Suche, Merkliste, Mehr.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/prefs.dart';
import '../../core/theme.dart';
import '../onboarding/onboarding.dart';

class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({required this.shell, super.key});

  final StatefulNavigationShell shell;

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  bool _onboardingShown = false;

  /// Beim ersten Start (je Gerät) einmal die Anleitung – erst wenn die Einstellungen geladen sind.
  void _maybeShowOnboarding(UiPrefs prefs) {
    if (_onboardingShown || !prefs.loaded || prefs.onboarded) return;
    _onboardingShown = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await showOnboarding(context);
      ref.read(uiPrefsProvider.notifier).finishOnboarding();
    });
  }

  static const _tabs = [
    (icon: Icons.dashboard_outlined, active: Icons.dashboard, label: 'Übersicht'),
    (
      icon: Icons.collections_bookmark_outlined,
      active: Icons.collections_bookmark,
      label: 'Sammlung',
    ),
    (icon: Icons.search, active: Icons.search, label: 'Suche'),
    (icon: Icons.favorite_border, active: Icons.favorite, label: 'Merkliste'),
    (icon: Icons.more_horiz, active: Icons.more_horiz, label: 'Mehr'),
  ];

  @override
  Widget build(BuildContext context) {
    _maybeShowOnboarding(ref.watch(uiPrefsProvider));
    final shell = widget.shell;
    Widget tab(int index) {
      final item = _tabs[index];
      final selected = shell.currentIndex == index;
      final color = selected ? AppColors.primary : AppColors.textMuted;
      return Expanded(
        child: InkWell(
          key: Key('tab-${item.label}'),
          onTap: () => shell.goBranch(index, initialLocation: index == shell.currentIndex),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 2),
            // Verkleinert bei großer Systemschrift statt überzulaufen.
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(selected ? item.active : item.icon, color: color),
                  const SizedBox(height: 2),
                  Text(item.label, style: TextStyle(fontSize: 11, color: color)),
                ],
              ),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      body: shell,
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border(top: BorderSide(color: AppColors.outline)),
        ),
        child: SafeArea(
          child: SizedBox(
            height: 64, // feste Höhe: „Center“ würde sonst den ganzen Bildschirm belegen
            child: Row(
              children: [
                tab(0),
                tab(1),
                Expanded(
                  child: Center(child: _ScanButton(onTap: () => context.push('/scan'))),
                ),
                tab(2),
                tab(3),
                tab(4),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ScanButton extends StatelessWidget {
  const _ScanButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: 'Karte scannen',
    child: GestureDetector(
      key: const Key('scan-button'),
      onTap: onTap,
      child: Container(
        width: 56,
        height: 56,
        decoration: BoxDecoration(
          gradient: AppColors.scanGradient,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: AppColors.accent.withValues(alpha: 0.4),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: const Icon(Icons.document_scanner, color: Colors.white),
      ),
    ),
  );
}
