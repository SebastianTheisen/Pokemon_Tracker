// „Erste Schritte“: kleine Checkliste für Neue – verschwindet, wenn alles erledigt ist.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/prefs.dart';
import '../../core/providers.dart';
import '../../core/push/push_bridge.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../alerts/alerts_screen.dart';
import '../collection/item_sheet.dart';
import '../wishlist/wishlist_screen.dart';
import 'dashboard_screen.dart';

typedef _Step = ({
  String key,
  IconData icon,
  String title,
  String hint,
  bool done,
  List<Widget> actions,
});

/// Ein Tipp statt drei: neueste Position ohne Kaufpreis gleich zum Bearbeiten öffnen.
Future<void> _enterPurchasePrice(BuildContext context, WidgetRef ref) async {
  CollectionItem? item;
  final ok = await runAction(context, () async {
    final page = await ref
        .read(apiProvider)
        .items(withPurchase: false, sort: 'added_desc', limit: 1);
    item = page.items.firstOrNull;
  });
  if (!ok || !context.mounted) return;
  final target = item;
  if (target == null) {
    context.go('/collection');
    return;
  }
  if (await showItemSheet(context, item: target) != null) invalidateCollection(ref);
}

class FirstSteps extends ConsumerWidget {
  const FirstSteps({required this.summary, super.key});

  final CollectionSummary summary;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prefs = ref.watch(uiPrefsProvider);
    if (!prefs.loaded || prefs.firstStepsHidden) return const SizedBox.shrink();
    final wished = ref.watch(wishlistProvider).value?.isNotEmpty ?? false;
    final alerted = ref.watch(alertsProvider).value?.isNotEmpty ?? false;
    final push = ref.watch(pushStateProvider).value;
    final pushOn = push != null && push.subscribed;
    // Ohne Push-Unterstützung (oder Server ohne Schlüssel) zählt der Schritt nicht.
    final pushPossible =
        push == null || (push.config.publicKey != null && push.status != PushStatus.unsupported);
    final steps = <_Step>[
      (
        key: 'first-card',
        icon: Icons.style,
        title: 'Erste Karte hinzufügen',
        hint: 'Scannen geht am schnellsten – oder per Name suchen.',
        done: summary.items > 0,
        actions: [
          FilledButton.icon(
            key: const Key('first-scan'),
            onPressed: () => context.push('/scan'),
            icon: const Icon(Icons.document_scanner),
            label: const Text('Scannen'),
          ),
          OutlinedButton.icon(
            key: const Key('first-search'),
            onPressed: () => context.go('/search'),
            icon: const Icon(Icons.search),
            label: const Text('Suchen'),
          ),
        ],
      ),
      (
        key: 'first-price',
        icon: Icons.trending_up,
        title: 'Kaufpreis eintragen',
        hint: 'Was hast du bezahlt? Dann siehst du Gewinn oder Verlust.',
        done: summary.hasProfit,
        actions: [
          FilledButton.icon(
            key: const Key('first-price-edit'),
            onPressed: () => _enterPurchasePrice(context, ref),
            icon: const Icon(Icons.edit),
            label: const Text('Jetzt eintragen'),
          ),
        ],
      ),
      (
        key: 'first-wish',
        icon: Icons.favorite_border,
        title: 'Wunschkarte merken',
        hint: 'Auf der Kartenseite „Merkliste“ oder die Glocke für einen Preisalarm.',
        done: wished || alerted,
        actions: [
          OutlinedButton(onPressed: () => context.go('/search'), child: const Text('Karte suchen')),
        ],
      ),
      if (pushPossible)
        (
          key: 'first-push',
          icon: Icons.notifications_outlined,
          title: 'Mitteilungen einschalten',
          hint: 'Damit dein Handy sich meldet, wenn ein Preisalarm auslöst.',
          done: pushOn,
          actions: [
            OutlinedButton(
              onPressed: () => context.push('/alerts'),
              child: const Text('Einschalten'),
            ),
          ],
        ),
    ];
    final done = steps.where((step) => step.done).length;
    if (done == steps.length) return const SizedBox.shrink();
    final next = steps.firstWhere((step) => !step.done);
    return Card(
      key: const Key('first-steps'),
      margin: const EdgeInsets.only(top: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'Erste Schritte',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                  ),
                ),
                Text('$done von ${steps.length}', style: TextStyle(color: AppColors.textMuted)),
                IconButton(
                  key: const Key('first-steps-hide'),
                  tooltip: 'Ausblenden',
                  onPressed: () => ref.read(uiPrefsProvider.notifier).hideFirstSteps(),
                  icon: const Icon(Icons.close, size: 20),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(right: 8, bottom: 8),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: done / steps.length,
                  minHeight: 6,
                  backgroundColor: AppColors.outline,
                ),
              ),
            ),
            for (final step in steps)
              Padding(
                padding: const EdgeInsets.only(top: 6, right: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      step.done ? Icons.check_circle : step.icon,
                      key: Key('${step.key}-${step.done ? 'done' : 'open'}'),
                      color: step.done ? AppColors.gain : AppColors.primary,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            step.title,
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              decoration: step.done ? TextDecoration.lineThrough : null,
                              color: step.done ? AppColors.textMuted : null,
                            ),
                          ),
                          // Nur beim nächsten offenen Schritt Erklärung und Knöpfe – nicht alles auf einmal.
                          if (step.key == next.key) ...[
                            Text(step.hint, style: TextStyle(color: AppColors.textMuted)),
                            const SizedBox(height: 8),
                            Wrap(spacing: 8, runSpacing: 8, children: step.actions),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
