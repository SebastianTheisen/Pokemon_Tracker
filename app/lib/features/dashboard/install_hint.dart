// „Als App installieren“: auf dem iPhone nur so mit Mitteilungen und ohne Browser-Leiste.
// Android/Chrome: echter Installieren-Knopf; iPhone: Anleitung in drei Schritten.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/device/device.dart';
import '../../core/prefs.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';

class InstallHint extends ConsumerStatefulWidget {
  const InstallHint({super.key});

  @override
  ConsumerState<InstallHint> createState() => _InstallHintState();
}

class _InstallHintState extends ConsumerState<InstallHint> {
  late InstallState _state = ref.read(deviceProvider).installState();

  Future<void> _install() async {
    final accepted = await ref.read(deviceProvider).install();
    if (!mounted) return;
    setState(() => _state = ref.read(deviceProvider).installState());
    if (accepted) showMessage(context, 'Kartenkiste ist jetzt auf deinem Startbildschirm.');
  }

  @override
  Widget build(BuildContext context) {
    final prefs = ref.watch(uiPrefsProvider);
    if (!prefs.loaded ||
        prefs.installHintHidden ||
        (_state != InstallState.prompt && _state != InstallState.ios)) {
      return const SizedBox.shrink();
    }
    return Card(
      key: const Key('install-hint'),
      margin: const EdgeInsets.only(top: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: AppColors.scanGradient,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.install_mobile, color: Colors.white),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Als App installieren', style: TextStyle(fontWeight: FontWeight.w700)),
                  Text(
                    _state == InstallState.ios
                        ? 'Startet wie eine App und kann dir Preisalarme schicken.'
                        : 'Startet wie eine App – ohne Browser-Leiste.',
                    style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  FilledButton(
                    key: const Key('install-action'),
                    onPressed: _state == InstallState.ios
                        ? () => showIosInstallGuide(context)
                        : _install,
                    child: Text(_state == InstallState.ios ? 'So geht’s' : 'Installieren'),
                  ),
                ],
              ),
            ),
            IconButton(
              key: const Key('install-hide'),
              tooltip: 'Ausblenden',
              onPressed: () => ref.read(uiPrefsProvider.notifier).hideInstallHint(),
              icon: const Icon(Icons.close, size: 20),
            ),
          ],
        ),
      ),
    );
  }
}

/// Anleitung für Safari auf iPhone/iPad (dort gibt es keinen Installieren-Knopf).
Future<void> showIosInstallGuide(BuildContext context) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true, // so hoch wie nötig – auch bei großer Schrift
  builder: (_) => SafeArea(
    child: SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
      child: Column(
        key: const Key('ios-install-guide'),
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'In drei Schritten auf den Home-Bildschirm',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),
          for (final (index, step) in const [
            (Icons.ios_share, 'Unten in Safari auf „Teilen“ tippen (Quadrat mit Pfeil nach oben).'),
            (
              Icons.add_box_outlined,
              '„Zum Home-Bildschirm“ wählen – evtl. etwas nach unten scrollen.',
            ),
            (
              Icons.check_circle_outline,
              'Oben rechts „Hinzufügen“. Danach die Kartenkiste über das neue Symbol öffnen.',
            ),
          ].indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  CircleAvatar(
                    radius: 14,
                    backgroundColor: AppColors.primary,
                    child: Text(
                      '${index + 1}',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Icon(step.$1, color: AppColors.primary),
                  const SizedBox(width: 12),
                  Expanded(child: Text(step.$2)),
                ],
              ),
            ),
          Text(
            'Tipp: Mitteilungen (Preisalarme) gibt es auf dem iPhone nur in der installierten App.',
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
        ],
      ),
    ),
  ),
);
