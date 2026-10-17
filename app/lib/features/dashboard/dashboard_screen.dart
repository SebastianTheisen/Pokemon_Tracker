// Übersicht: Sammlungswert mit Kurve, Schnellaktionen, Kennzahlen, Highlights.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/value_chart.dart';

final dashboardProvider = FutureProvider.autoDispose<CollectionSummary>(
  (ref) => ref.watch(apiProvider).dashboard(),
);

final collectionHistoryProvider = FutureProvider.autoDispose<CollectionHistory>(
  (ref) => ref.watch(apiProvider).collectionHistory(),
);

/// Nach Änderungen an der Sammlung alle abhängigen Anzeigen neu laden.
void invalidateCollection(WidgetRef ref) => ref
  ..invalidate(dashboardProvider)
  ..invalidate(collectionHistoryProvider);

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(sessionProvider).value;
    final summary = ref.watch(dashboardProvider);
    return Scaffold(
      appBar: AppBar(title: Text('Hallo ${user?.displayName ?? ''}')),
      body: RefreshIndicator(
        onRefresh: () async {
          invalidateCollection(ref);
          await ref.read(dashboardProvider.future);
        },
        child: ListView(
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
              child: TextField(
                readOnly: true,
                onTap: () => context.go('/search'),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Karte suchen – Preis mit Beleg',
                ),
              ),
            ),
            const SizedBox(height: 16),
            AsyncBody(
              value: summary,
              onRetry: () => invalidateCollection(ref),
              builder: (data) => _SummaryContent(summary: data),
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryContent extends ConsumerWidget {
  const _SummaryContent({required this.summary});

  final CollectionSummary summary;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final change = parseAmount(summary.changeSinceAdded) ?? 0;
    final history = ref.watch(collectionHistoryProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Sammlungswert', style: TextStyle(color: AppColors.textMuted)),
                  const SizedBox(height: 4),
                  Text(
                    money(summary.totalValue),
                    key: const Key('total-value'),
                    style: Theme.of(context).textTheme.headlineMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${signedMoney(summary.changeSinceAdded)} seit dem Hinzufügen',
                    style: TextStyle(
                      color: change > 0
                          ? AppColors.gain
                          : change < 0
                          ? AppColors.loss
                          : AppColors.textMuted,
                    ),
                  ),
                  if ((parseAmount(summary.estimatedValue) ?? 0) > 0)
                    Text(
                      'davon geschätzt: ${money(summary.estimatedValue)}',
                      style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                  const SizedBox(height: 12),
                  history.maybeWhen(
                    data: (data) => ValueChart(
                      points: [
                        for (final point in data.points)
                          ChartPoint(
                            point.date,
                            parseAmount(point.totalValue) ?? 0,
                            highlighted: point.isLive,
                          ),
                      ],
                    ),
                    orElse: () => const SizedBox(height: 160),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          height: 92,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            children: [
              _QuickAction(Icons.document_scanner, 'Scannen', () => context.push('/scan')),
              _QuickAction(Icons.burst_mode, 'Stapel', () => context.push('/scan/batch')),
              _QuickAction(Icons.grid_view, 'Binder', () => context.push('/scan/binder')),
              _QuickAction(Icons.collections_bookmark, 'Sammlung', () => context.go('/collection')),
              _QuickAction(Icons.favorite, 'Merkliste', () => context.go('/lists')),
            ],
          ),
        ),
        const SectionTitle('Kennzahlen'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _Stat('${summary.items}', 'Karten'),
              const SizedBox(width: 8),
              _Stat('${summary.sets}', 'Sets'),
              const SizedBox(width: 8),
              _Stat(money(summary.topItem?.value.unitValue), 'höchster Wert'),
            ],
          ),
        ),
        if (summary.unvaluedPositions > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(
              '${summary.unvaluedPositions} Positionen ohne Wert (kein belegter Preis – '
              'Eigenpreis eintragen)',
              style: const TextStyle(color: AppColors.warning, fontSize: 12),
            ),
          ),
        const SectionTitle('Aufteilung'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _Stat(money(summary.raw.value), 'Rohkarten'),
              const SizedBox(width: 8),
              _Stat(money(summary.graded.value), 'Gegradet'),
              const SizedBox(width: 8),
              _Stat(money(summary.sealed.value), 'Versiegelt'),
            ],
          ),
        ),
        const SectionTitle('Highlights'),
        if (summary.topItem == null)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'Noch keine Karten – scanne deine erste Karte!',
              style: TextStyle(color: AppColors.textMuted),
            ),
          ),
        if (summary.topItem case final item?) _Highlight('Top-Karte', item),
        if (summary.biggestGain case final item?) _Highlight('Größter Gewinner', item),
        if (summary.biggestLoss case final item?) _Highlight('Größter Verlierer', item),
      ],
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction(this.icon, this.label, this.onTap);

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 4),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Ink(
        width: 84,
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppColors.outline),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: AppColors.primary),
            const SizedBox(height: 6),
            Text(label, style: const TextStyle(fontSize: 12)),
          ],
        ),
      ),
    ),
  );
}

class _Stat extends StatelessWidget {
  const _Stat(this.value, this.label);

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FittedBox(
              child: Text(value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            ),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
          ],
        ),
      ),
    ),
  );
}

class _Highlight extends StatelessWidget {
  const _Highlight(this.title, this.item);

  final String title;
  final CollectionItem item;

  @override
  Widget build(BuildContext context) {
    final change = parseAmount(item.value.change);
    return ListTile(
      onTap: item.card == null ? null : () => context.push('/card/${item.card!.id}'),
      leading: CardImage(url: item.card?.image(), width: 40),
      title: Text(item.title),
      subtitle: Text(title, style: const TextStyle(color: AppColors.textMuted)),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(item.value.unitValue), style: const TextStyle(fontWeight: FontWeight.w600)),
          if (change != null && change != 0)
            Text(
              signedMoney(item.value.change),
              style: TextStyle(fontSize: 12, color: change > 0 ? AppColors.gain : AppColors.loss),
            ),
        ],
      ),
    );
  }
}
