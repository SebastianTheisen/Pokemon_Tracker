// Startseite: Sammlungswert auf einen Blick, großer Scan-Knopf, Karten als Bilder-Reihen.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/value_chart.dart';
import '../alerts/alerts_screen.dart';
import '../../core/prefs.dart';
import '../collection/owned.dart';
import 'first_steps.dart';

final dashboardProvider = FutureProvider.autoDispose<CollectionSummary>(
  (ref) => ref.watch(apiProvider).dashboard(),
);

final collectionHistoryProvider = FutureProvider.autoDispose<CollectionHistory>(
  (ref) => ref.watch(apiProvider).collectionHistory(),
);

/// Wertvollste bzw. zuletzt hinzugefügte Positionen für die Bilder-Reihen.
final showcaseProvider = FutureProvider.autoDispose.family<List<CollectionItem>, String>(
  (ref, sort) async => (await ref.watch(apiProvider).items(sort: sort, limit: 12)).items,
);

/// Gewinner und Verlierer der letzten 7 Tage (eigene Rohkarten, Cardmarket-Trend).
final moversProvider = FutureProvider.autoDispose<Movers>((ref) => ref.watch(apiProvider).movers());

/// Kennzahlen eines Ordners (`null` = ganze Sammlung) – für den Kopf der Sammlung.
final folderSummaryProvider = FutureProvider.autoDispose.family<CollectionSummary, String?>(
  (ref, folderId) => ref.watch(apiProvider).dashboard(folderId: folderId),
);

/// Alle Ordner als Portfolios (Wert, Kaufpreise, Gewinn).
final folderSummariesProvider = FutureProvider.autoDispose<List<FolderSummary>>(
  (ref) => ref.watch(apiProvider).folderSummaries(),
);

/// Nach Änderungen an der Sammlung alle abhängigen Anzeigen neu laden.
void invalidateCollection(WidgetRef ref) => ref
  ..invalidate(dashboardProvider)
  ..invalidate(folderSummaryProvider)
  ..invalidate(folderSummariesProvider)
  ..invalidate(collectionHistoryProvider)
  ..invalidate(showcaseProvider)
  ..invalidate(ownedProvider)
  ..invalidate(moversProvider);

/// Farbe für Gewinn (grün), Verlust (rot) oder neutral.
Color profitColor(String? amount, {Color? neutral}) {
  final value = parseAmount(amount) ?? 0;
  return value > 0
      ? AppColors.gain
      : value < 0
      ? AppColors.loss
      : neutral ?? AppColors.textMuted;
}

/// „+50,00 € (+20,0 %)“ – Gewinn gegenüber dem Kaufpreis.
String profitText(String profit, String? profitPercent) {
  final pct = parseAmount(profitPercent);
  return pct == null
      ? signedMoney(profit)
      : '${signedMoney(profit)} (${signedPercent(pct, isPercent: true)})';
}

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(sessionProvider).value;
    final summary = ref.watch(dashboardProvider);
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () async {
            invalidateCollection(ref);
            await ref.read(dashboardProvider.future);
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              // Suchen steckt in der unteren Leiste und in den Schnellzugriffen – kein dritter Knopf.
              Text(
                'Hallo ${user?.displayName ?? ''} 👋',
                style: Theme.of(context).textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              AsyncBody(
                value: summary,
                onRetry: () => invalidateCollection(ref),
                builder: (data) =>
                    data.items == 0 ? const _WelcomeHero() : _ValueHero(summary: data),
              ),
              // Für Neue: Checkliste mit dem jeweils nächsten Schritt (ausblendbar).
              if (summary.value case final data?) FirstSteps(summary: data),
              // Reihenfolge: Wert → Heute → Bewegungen → Schnellzugriffe → Karten. Scannen
              // steckt im runden Knopf unten; die große Kachel nur bei leerer Kiste ohne Checkliste.
              if (summary.value case final data? when data.items == 0) ...[
                if (ref.watch(uiPrefsProvider).firstStepsHidden) ...[
                  const SizedBox(height: 16),
                  _ScanCallToAction(onTap: () => context.push('/scan')),
                  const _EmptyHint(),
                ],
              ] else ...[
                const _TodayCard(),
                const _MoversSection(),
                const SizedBox(height: 20),
                const _QuickActions(),
                if (summary.value case final data? when data.hasProfit)
                  _ProfitSection(summary: data),
                const _Showcase(title: 'Wertvollste Karten', sort: 'value_desc'),
                const _Showcase(title: 'Zuletzt hinzugefügt', sort: 'added_desc'),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ValueHero extends ConsumerStatefulWidget {
  const _ValueHero({required this.summary});

  final CollectionSummary summary;

  @override
  ConsumerState<_ValueHero> createState() => _ValueHeroState();
}

class _ValueHeroState extends ConsumerState<_ValueHero> {
  /// Finger auf der Kurve: Wert dieses Tages statt des aktuellen.
  ChartPoint? _scrub;

  @override
  Widget build(BuildContext context) {
    final summary = widget.summary;
    final change = parseAmount(summary.changeSinceAdded) ?? 0;
    final history = ref.watch(collectionHistoryProvider).value;
    final scrub = _scrub;
    return InkWell(
      onTap: () => context.go('/collection'),
      borderRadius: BorderRadius.circular(24),
      child: Ink(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
        decoration: BoxDecoration(
          gradient: AppColors.scanGradient,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              scrub == null ? 'Sammlungswert' : 'Sammlungswert am ${date(scrub.date)}',
              key: const Key('hero-label'),
              style: TextStyle(color: Colors.white.withValues(alpha: 0.85)),
            ),
            const SizedBox(height: 4),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: scrub != null
                  ? Text(
                      money(scrub.value.toStringAsFixed(2)),
                      key: const Key('hero-scrub-value'),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 38,
                        fontWeight: FontWeight.w800,
                      ),
                    )
                  : CountUpMoney(
                      value: parseAmount(summary.totalValue) ?? 0,
                      key: const Key('total-value'),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 38,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (change != 0)
                  Container(
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      '${change > 0 ? '▲' : '▼'} ${signedMoney(summary.changeSinceAdded)}',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                    ),
                  ),
                Flexible(
                  child: Text(
                    '${summary.items} ${summary.items == 1 ? 'Karte' : 'Karten'} · '
                    '${summary.sets} ${summary.sets == 1 ? 'Set' : 'Sets'}',
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.85)),
                  ),
                ),
              ],
            ),
            if (summary.hasProfit)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  'Investiert ${money(summary.invested)} · Gewinn '
                  '${profitText(summary.profit, summary.profitPercent)}',
                  key: const Key('hero-profit'),
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.9), fontSize: 13),
                ),
              ),
            ValueChart(
              height: 70,
              onDark: true,
              emptyHint: false,
              onScrub: (point) => setState(() => _scrub = point),
              points: [
                for (final point in history?.points ?? const <ValuePoint>[])
                  ChartPoint(point.date, parseAmount(point.totalValue) ?? 0),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Leere Kiste: statt „0,00 €“ ein Willkommen, das sagt, was hier gleich passiert.
class _WelcomeHero extends StatelessWidget {
  const _WelcomeHero();

  @override
  Widget build(BuildContext context) => Container(
    key: const Key('welcome-hero'),
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      gradient: AppColors.scanGradient,
      borderRadius: BorderRadius.circular(24),
    ),
    child: Row(
      children: [
        const Icon(Icons.auto_awesome, color: Colors.white, size: 36),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Willkommen in deiner Kartenkiste!',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                'Füge deine erste Karte hinzu – hier siehst du dann, was deine Sammlung wert ist.',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.9)),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _ScanCallToAction extends StatelessWidget {
  const _ScanCallToAction({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: AppColors.surface,
    borderRadius: BorderRadius.circular(20),
    child: InkWell(
      key: const Key('home-scan'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.outline),
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 26,
              backgroundColor: AppColors.primary,
              child: Icon(Icons.photo_camera, color: Colors.white, size: 26),
            ),
            SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Karte scannen',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Foto machen – Preis sofort sehen',
                    style: TextStyle(color: AppColors.textMuted),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: AppColors.textMuted),
          ],
        ),
      ),
    ),
  );
}

/// Schnellzugriffe (wie Collectr): Wege, die nicht schon in der unteren Leiste stecken.
class _QuickActions extends StatelessWidget {
  const _QuickActions();

  static const _actions = [
    (
      key: 'quick-sealed',
      icon: Icons.inventory_2_outlined,
      label: 'Versiegelt',
      path: '/sealed/add',
    ),
    (key: 'quick-sets', icon: Icons.layers_outlined, label: 'Sets', path: '/sets'),
    (key: 'quick-trade', icon: Icons.swap_horiz, label: 'Tausch', path: '/trade'),
    (key: 'quick-alerts', icon: Icons.notifications_outlined, label: 'Alarme', path: '/alerts'),
  ];

  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (final (index, action) in _actions.indexed) ...[
        if (index > 0) const SizedBox(width: 8),
        Expanded(
          child: Material(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            child: InkWell(
              key: Key(action.key),
              borderRadius: BorderRadius.circular(16),
              onTap: () => context.push(action.path),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Column(
                  children: [
                    Icon(action.icon, color: AppColors.primary),
                    const SizedBox(height: 4),
                    Text(
                      action.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    ],
  );
}

/// „Heute“: Veränderung seit dem letzten Tageswert und frisch ausgelöste Preisalarme.
/// Erscheint nur, wenn es etwas zu sagen gibt.
class _TodayCard extends ConsumerWidget {
  const _TodayCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final points = ref.watch(collectionHistoryProvider).value?.points ?? const <ValuePoint>[];
    final alerts = ref.watch(alertsProvider).value ?? const <PriceAlert>[];
    final since = DateTime.now().subtract(const Duration(days: 3));
    final fired = [
      for (final alert in alerts)
        if (!alert.active && (alert.triggeredAt?.isAfter(since) ?? false)) alert,
    ];
    final change = points.length < 2
        ? null
        : (parseAmount(points.last.totalValue) ?? 0) -
              (parseAmount(points[points.length - 2].totalValue) ?? 0);
    if ((change == null || change.abs() < 0.01) && fired.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Card(
        key: const Key('today-card'),
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Heute', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              if (change != null && change.abs() >= 0.01)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        const TextSpan(text: 'Seit gestern '),
                        TextSpan(
                          text: signedMoney(change.toStringAsFixed(2)),
                          style: TextStyle(
                            color: change > 0 ? AppColors.gain : AppColors.loss,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    key: const Key('today-change'),
                  ),
                ),
              for (final alert in fired.take(3))
                ListTile(
                  key: Key('today-alert-${alert.id}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  onTap: () => context.push('/alerts'),
                  leading: Icon(Icons.notifications_active, color: AppColors.warning),
                  title: Text(alert.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    'Preisalarm: ${money(alert.triggeredValue)} – '
                    '${alert.above ? 'über' : 'unter'} deinem Ziel ${money(alert.target)}',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyHint extends StatelessWidget {
  const _EmptyHint();

  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.only(top: 40),
    child: EmptyView(
      icon: Icons.style,
      message: 'Deine Kiste ist noch leer.\nScanne deine erste Karte oder suche sie.',
    ),
  );
}

/// Waagerechte Reihe aus Kartenbildern mit Wert.
class _Showcase extends ConsumerWidget {
  const _Showcase({required this.title, required this.sort});

  final String title;
  final String sort;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(showcaseProvider(sort)).value ?? const <CollectionItem>[];
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 24, bottom: 10),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
              ),
              TextButton(onPressed: () => context.go('/collection'), child: const Text('Alle')),
            ],
          ),
        ),
        SizedBox(
          height: 228, // Bild (104 × 88/63) + Wert + Name, mit Luft für größere Schrift
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: items.length,
            separatorBuilder: (_, _) => const SizedBox(width: 12),
            itemBuilder: (context, index) => ItemThumb(item: items[index], width: 104),
          ),
        ),
      ],
    );
  }
}

/// Kartenbild mit Name und Wert darunter (Startseite und Sammlungs-Raster).
class ItemThumb extends StatelessWidget {
  const ItemThumb({
    required this.item,
    this.width = 104,
    this.onTap,
    this.onLongPress,
    this.selected,
    super.key,
  });

  final CollectionItem item;
  final double width;

  /// Statt die Karte zu öffnen (z. B. Aktionsmenü in der Sammlung).
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// Auswahlmodus: `true`/`false` zeigt einen Haken bzw. Kreis; `null` = kein Auswahlmodus.
  final bool? selected;

  @override
  Widget build(BuildContext context) {
    final card = item.card;
    return SizedBox(
      width: width,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap ?? (card == null ? null : () => context.push('/card/${card.id}')),
        onLongPress: onLongPress,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                Opacity(
                  opacity: selected == false ? 0.55 : 1,
                  child: CardImage(url: item.image, width: width, contain: card == null),
                ),
                if (selected case final isSelected?)
                  Positioned(
                    left: 4,
                    top: 4,
                    child: Icon(
                      isSelected ? Icons.check_circle : Icons.radio_button_unchecked,
                      key: Key('select-${item.id}'),
                      color: isSelected ? AppColors.primary : Colors.white,
                      shadows: const [Shadow(blurRadius: 4)],
                    ),
                  ),
                // Wie bei Collectr: Bewegung der letzten 7 Tage direkt am Bild.
                if (item.trend7dPct != null)
                  Positioned(
                    left: 4,
                    bottom: 4,
                    child: TrendBadge(percent: item.trend7dPct, solid: true),
                  ),
                if (item.quantity > 1 || item.kind == 'graded')
                  Positioned(
                    right: 4,
                    top: 4,
                    child: Tag(
                      item.kind == 'graded' ? item.label : '×${item.quantity}',
                      color: AppColors.accent,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(money(item.value.totalValue), style: const TextStyle(fontWeight: FontWeight.w700)),
            if (item.value.profit case final profit?)
              Text(signedMoney(profit), style: TextStyle(color: profitColor(profit), fontSize: 12)),
            Text(
              item.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

/// „Seit dem Kauf“: bester und schlechtester Kauf (nur Positionen mit Kaufpreis).
class _ProfitSection extends StatelessWidget {
  const _ProfitSection({required this.summary});

  final CollectionSummary summary;

  @override
  Widget build(BuildContext context) {
    final entries = [?summary.bestProfit, ?summary.worstProfit];
    if (entries.isEmpty) return const SizedBox.shrink();
    return Column(
      key: const Key('profit-section'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Die Gesamtsumme steht schon oben im Wert-Kasten – hier nur die Ausreißer.
        Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 4),
          child: Text(
            'Bester und schlechtester Kauf',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        for (final item in entries) _ProfitTile(item: item),
      ],
    );
  }
}

class _ProfitTile extends StatelessWidget {
  const _ProfitTile({required this.item});

  final CollectionItem item;

  @override
  Widget build(BuildContext context) {
    final value = item.value;
    final color = profitColor(value.profit);
    final pct = value.profitPercent;
    final card = item.card;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      onTap: card == null ? null : () => context.push('/card/${card.id}'),
      leading: CardImage(url: item.image, width: 32, contain: card == null),
      title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          '${money(value.cost)} → ${money(value.totalValue)}',
          if (item.quantity > 1) '${item.quantity}×',
        ].join(' · '),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            signedMoney(value.profit),
            style: TextStyle(color: color, fontWeight: FontWeight.w700),
          ),
          if (pct != null) Text(signedPercent(pct), style: TextStyle(color: color, fontSize: 12)),
        ],
      ),
    );
  }
}

/// „Bewegungen (7 Tage)“: größte Gewinner und Verlierer – nur wenn es welche gibt.
class _MoversSection extends ConsumerWidget {
  const _MoversSection();

  static const _shown = 3;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final movers = ref.watch(moversProvider).value;
    if (movers == null || movers.isEmpty) return const SizedBox.shrink();
    return Column(
      key: const Key('movers'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 4),
          child: Text(
            'Bewegungen (${movers.days} Tage)',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        for (final mover in [...movers.gainers.take(_shown), ...movers.losers.take(_shown)])
          _MoverTile(mover: mover),
      ],
    );
  }
}

class _MoverTile extends StatelessWidget {
  const _MoverTile({required this.mover});

  final Mover mover;

  @override
  Widget build(BuildContext context) {
    final up = !mover.change.startsWith('-');
    final color = up ? AppColors.gain : AppColors.loss;
    final pct = mover.changePct.replaceAll('.', ',');
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      onTap: () => context.push('/card/${mover.card.id}'),
      leading: CardImage(url: mover.card.image(), width: 32),
      title: Text(mover.card.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          '${money(mover.before)} → ${money(mover.now)}',
          if (mover.quantity > 1) '${mover.quantity}×',
          if (mover.variant == 'reverse') 'Reverse Holo',
        ].join(' · '),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            signedMoney(mover.change),
            style: TextStyle(color: color, fontWeight: FontWeight.w700),
          ),
          Text('${up ? '+' : ''}$pct %', style: TextStyle(color: color, fontSize: 12)),
        ],
      ),
    );
  }
}
