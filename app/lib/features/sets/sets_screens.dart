// Sets: Übersicht der Sets in der Sammlung und Set-Seite mit allen Karten.
//
// * Set: jede Karte zählt einmal (egal welche Fassung).
// * Master-Set: jede Fassung zählt – Hauptfassung und, falls vorhanden, Reverse Holo.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/confetti.dart';
import '../collection/collection_screen.dart';
import '../wishlist/wishlist_screen.dart';

final setProgressProvider = FutureProvider.autoDispose.family<SetProgress, String>(
  (ref, setId) => ref.watch(apiProvider).setProgress(setId),
);

/// „12 / 191“ und Anteil (0…1); ohne Gesamtzahl nur die besessene Anzahl.
(String, double?) _ratio(int owned, int? total) => total == null || total == 0
    ? ('$owned', null)
    : ('$owned / $total', (owned / total).clamp(0, 1).toDouble());

class SetOverviewScreen extends ConsumerWidget {
  const SetOverviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sets = ref.watch(collectionSetsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Sets')),
      body: AsyncBody(
        value: sets,
        onRetry: () => ref.invalidate(collectionSetsProvider),
        builder: (list) => list.isEmpty
            ? const EmptyView(icon: Icons.layers_outlined, message: 'Noch keine Karten.')
            : ListView.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const Divider(),
                itemBuilder: (context, index) => _SetTile(entry: list[index]),
              ),
      ),
    );
  }
}

class _SetTile extends StatelessWidget {
  const _SetTile({required this.entry});

  final SetOverview entry;

  @override
  Widget build(BuildContext context) {
    final total = entry.cardsTotal ?? entry.cardSet.officialCount;
    final (setText, setShare) = _ratio(entry.ownedCards, total);
    final (masterText, _) = _ratio(entry.masterOwned ?? 0, entry.masterTotal);
    return ListTile(
      key: Key('set-${entry.cardSet.id}'),
      onTap: () => context.push('/sets/${entry.cardSet.id}'),
      title: Text('${entry.cardSet.displayName} (${languageTag(entry.cardSet.language)})'),
      trailing: const Icon(Icons.chevron_right),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (entry.cardSet.originalName case final original?) Text(original),
          Text(
            [
              '$setText Karten',
              if (setShare != null) percent(setShare),
              if (entry.masterTotal != null) 'Master $masterText',
              money(entry.value),
            ].join(' · '),
          ),
          if (setShare != null) ...[
            const SizedBox(height: 6),
            LinearProgressIndicator(value: setShare),
          ],
        ],
      ),
    );
  }
}

enum _Show { all, missing, owned }

class SetDetailScreen extends ConsumerStatefulWidget {
  const SetDetailScreen({required this.setId, super.key});

  final String setId;

  @override
  ConsumerState<SetDetailScreen> createState() => _SetDetailScreenState();
}

class _SetDetailScreenState extends ConsumerState<SetDetailScreen> {
  _Show _show = _Show.all;

  /// Master-Ansicht: „fehlt“ heißt dann auch „Reverse Holo fehlt“.
  bool _master = false;

  bool _missing(CardProgress card) => _master ? !card.masterComplete : !card.owned;

  Future<void> _wishMissing(SetProgress progress) async {
    final ids = [
      for (final card in progress.cards)
        if (_missing(card) && !card.onWishlist) card.card.id,
    ];
    if (ids.isEmpty) {
      showMessage(context, 'Alle fehlenden Karten sind schon auf der Merkliste.');
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('${ids.length} ${ids.length == 1 ? 'Karte' : 'Karten'} auf die Merkliste?'),
        content: const Text('Alle fehlenden Karten dieses Sets, die noch nicht gemerkt sind.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            key: const Key('wish-missing-confirm'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Merken'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    var added = 0;
    final ok = await runAction(
      context,
      () async => added = await ref.read(apiProvider).addManyToWishlist(ids),
    );
    if (!ok || !mounted) return;
    ref
      ..invalidate(setProgressProvider(widget.setId))
      ..invalidate(wishlistProvider);
    showMessage(context, '$added ${added == 1 ? 'Karte' : 'Karten'} auf die Merkliste gesetzt.');
  }

  @override
  Widget build(BuildContext context) {
    final progress = ref.watch(setProgressProvider(widget.setId));
    return Scaffold(
      appBar: AppBar(
        title: Text(progress.value?.cardSet.displayName ?? 'Set'),
        actions: [
          IconButton(
            key: const Key('set-analytics'),
            tooltip: 'Set-Analyse (Wert, Bewegungen, Stabilität)',
            onPressed: () => context.push('/sets/${widget.setId}/analytics'),
            icon: const Icon(Icons.insights),
          ),
        ],
      ),
      body: AsyncBody(
        value: progress,
        onRetry: () => ref.invalidate(setProgressProvider(widget.setId)),
        builder: (data) {
          final cards = [
            for (final card in data.cards)
              if (switch (_show) {
                _Show.all => true,
                _Show.missing => _missing(card),
                _Show.owned => !_missing(card),
              })
                card,
          ];
          final complete = data.cardsTotal > 0 && data.cardsOwned >= data.cardsTotal;
          final scroll = CustomScrollView(
            slivers: [
              if (complete)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: Text(
                      data.masterTotal > 0 && data.masterOwned >= data.masterTotal
                          ? 'Master-Set komplett! 🏆'
                          : 'Set komplett! 🎉',
                      key: const Key('set-complete'),
                      style: Theme.of(context).textTheme.titleLarge
                          ?.copyWith(fontWeight: FontWeight.w800, color: AppColors.gain),
                    ),
                  ),
                ),
              SliverToBoxAdapter(child: _header(data)),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                sliver: cards.isEmpty
                    ? SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.only(top: 32),
                          child: Text(
                            _show == _Show.missing ? 'Nichts fehlt – komplett! 🎉' : 'Keine.',
                            textAlign: TextAlign.center,
                          ),
                        ),
                      )
                    : SliverGrid(
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 110,
                          mainAxisSpacing: 12,
                          crossAxisSpacing: 10,
                          childAspectRatio: 0.52,
                        ),
                        delegate: SliverChildBuilderDelegate(
                          childCount: cards.length,
                          (context, index) => _CardCell(
                            card: cards[index],
                            dimmed: _missing(cards[index]),
                            master: _master,
                          ),
                        ),
                      ),
              ),
            ],
          );
          // Feiern wie in Dex: Konfetti, wenn das Set voll ist.
          return complete ? Stack(children: [scroll, const ConfettiBurst()]) : scroll;
        },
      ),
    );
  }

  Widget _header(SetProgress data) {
    final (setText, setShare) = _ratio(data.cardsOwned, data.cardsTotal);
    final (masterText, masterShare) = _ratio(data.masterOwned, data.masterTotal);
    final missingCost = parseAmount(_master ? data.missingValue : data.missingSetValue) ?? 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (data.cardSet.originalName case final original?)
            Text(original, style: TextStyle(color: AppColors.textMuted)),
          _ProgressRow(
            key: const Key('progress-set'),
            label: 'Set',
            text: setText,
            share: setShare ?? 0,
          ),
          _ProgressRow(
            key: const Key('progress-master'),
            label: 'Master-Set',
            text: masterText,
            share: masterShare ?? 0,
            hint: 'inkl. Reverse Holo',
          ),
          if (missingCost > 0)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Fehlende Karten ≈ ${money(_master ? data.missingValue : data.missingSetValue)} '
                '(Near Mint, soweit Preise bekannt)',
                key: const Key('missing-cost'),
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
            ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (final (show, label) in [
                (_Show.all, 'Alle'),
                (_Show.missing, 'Fehlt'),
                (_Show.owned, 'Habe ich'),
              ])
                ChoiceChip(
                  key: Key('show-${show.name}'),
                  label: Text(label),
                  selected: _show == show,
                  onSelected: (_) => setState(() => _show = show),
                ),
              FilterChip(
                key: const Key('master-toggle'),
                label: const Text('Master'),
                tooltip: 'Reverse Holo zählt extra',
                selected: _master,
                onSelected: (value) => setState(() => _master = value),
              ),
            ],
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              key: const Key('wish-missing'),
              onPressed: () => _wishMissing(data),
              icon: const Icon(Icons.favorite_border),
              label: const Text('Fehlende auf die Merkliste'),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProgressRow extends StatelessWidget {
  const _ProgressRow({
    required this.label,
    required this.text,
    required this.share,
    this.hint,
    super.key,
  });

  final String label;
  final String text;
  final double share;
  final String? hint;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w700)),
            // Hinweis kürzt sich auf schmalen Handys statt die Zeile zu sprengen.
            Expanded(
              child: Text(
                hint == null ? '' : '  $hint',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
            ),
            Text('$text · ${percent(share)}'),
          ],
        ),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(value: share, minHeight: 8),
        ),
      ],
    ),
  );
}

/// Kartenbild; fehlende abgeblendet. Abzeichen: Anzahl, Reverse Holo, Merkliste.
class _CardCell extends StatelessWidget {
  const _CardCell({required this.card, required this.dimmed, required this.master});

  final CardProgress card;
  final bool dimmed;
  final bool master;

  @override
  Widget build(BuildContext context) {
    final count = card.ownedNormal + card.ownedReverse;
    return InkWell(
      key: Key('set-card-${card.card.id}'),
      borderRadius: BorderRadius.circular(8),
      onTap: () => context.push('/card/${card.card.id}'),
      child: LayoutBuilder(
        builder: (context, constraints) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                Opacity(
                  opacity: dimmed ? 0.3 : 1,
                  child: CardImage(url: card.card.image(), width: constraints.maxWidth),
                ),
                if (count > 0)
                  Positioned(right: 4, top: 4, child: Tag('×$count', color: AppColors.gain)),
                if (master && card.reverse)
                  Positioned(
                    left: 4,
                    bottom: 4,
                    child: Tag(
                      card.ownedReverse > 0 ? 'R ✓' : 'R',
                      color: card.ownedReverse > 0 ? AppColors.gain : AppColors.warning,
                    ),
                  ),
                if (card.onWishlist)
                  Positioned(
                    left: 4,
                    top: 4,
                    child: Icon(
                      Icons.favorite,
                      size: 16,
                      color: AppColors.loss,
                      shadows: [Shadow(blurRadius: 4)],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              card.card.number,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
            ),
            Text(
              card.nmValue == null ? card.card.displayName : money(card.nmValue),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: AppColors.textMuted, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

final setAnalyticsProvider = FutureProvider.autoDispose.family<SetAnalytics, String>(
  (ref, setId) => ref.watch(apiProvider).setAnalytics(setId),
);

/// Set-Analyse: Setwert, Veränderung (≈ 30 Tage), Stabilität, Gewinner/Verlierer, Top-Karten.
class SetAnalyticsScreen extends ConsumerWidget {
  const SetAnalyticsScreen({required this.setId, super.key});

  final String setId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final analytics = ref.watch(setAnalyticsProvider(setId));
    return Scaffold(
      appBar: AppBar(title: Text(analytics.value?.cardSet.displayName ?? 'Set-Analyse')),
      body: AsyncBody(
        value: analytics,
        onRetry: () => ref.invalidate(setAnalyticsProvider(setId)),
        builder: (data) => data.cardsPriced == 0
            ? const EmptyView(
                icon: Icons.insights,
                message: 'Für dieses Set gibt es noch keine Cardmarket-Preise.',
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                children: [
                  _AnalyticsHeader(data: data),
                  if (data.gainers.isNotEmpty) ...[
                    const SectionTitle('Größte Gewinner (≈ 30 Tage)'),
                    for (final card in data.gainers) _MarketTile(card: card),
                  ],
                  if (data.losers.isNotEmpty) ...[
                    const SectionTitle('Größte Verlierer (≈ 30 Tage)'),
                    for (final card in data.losers) _MarketTile(card: card),
                  ],
                  const SectionTitle('Wertvollste Karten'),
                  for (final card in data.topCards) _MarketTile(card: card, showChange: false),
                  Padding(
                    padding: EdgeInsets.only(top: 12),
                    child: Text(
                      'Quelle: Cardmarket-Preisführer (täglich). Veränderung = Trend gegenüber '
                      'dem Durchschnitt der letzten 30 Tage; Stabilität = typische Abweichung des '
                      'Tagesdurchschnitts vom 30-Tage-Schnitt (Karten ab 1 €).',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _AnalyticsHeader extends StatelessWidget {
  const _AnalyticsHeader({required this.data});

  final SetAnalytics data;

  @override
  Widget build(BuildContext context) {
    final change = data.change;
    final changeColor = change == null || change == 0
        ? AppColors.textMuted
        : (change > 0 ? AppColors.gain : AppColors.loss);
    final (stabilityIcon, stabilityColor) = switch (data.stability) {
      'ruhig' => (Icons.waves, AppColors.gain),
      'bewegt' => (Icons.bolt, AppColors.warning),
      _ => (Icons.show_chart, AppColors.primary),
    };
    return Card(
      key: const Key('analytics-header'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Setwert (Trend, je Karte einmal)', style: TextStyle(color: AppColors.textMuted)),
            Text(
              money(data.setValue),
              style: Theme.of(context).textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            if (change != null)
              Text(
                '${signedPercent(change)} gegenüber Ø 30 Tage',
                key: const Key('analytics-change'),
                style: TextStyle(color: changeColor, fontWeight: FontWeight.w600),
              ),
            const SizedBox(height: 8),
            Text('Master-Set inkl. Reverse Holo: ${money(data.masterValue)}'),
            Text(
              '${data.cardsPriced} von ${data.cardsTotal} Karten mit Preis',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            if (data.stability case final stability?) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(stabilityIcon, color: stabilityColor, size: 20),
                  const SizedBox(width: 6),
                  Text(
                    'Preise $stability'
                    '${data.volatility == null ? '' : ' (± ${percent(data.volatility!)})'}',
                    key: const Key('analytics-stability'),
                    style: TextStyle(color: stabilityColor, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _MarketTile extends StatelessWidget {
  const _MarketTile({required this.card, this.showChange = true});

  final MarketCard card;
  final bool showChange;

  @override
  Widget build(BuildContext context) {
    final change = card.change;
    final color = change == null || change == 0
        ? AppColors.textMuted
        : (change > 0 ? AppColors.gain : AppColors.loss);
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      onTap: () => context.push('/card/${card.card.id}'),
      leading: CardImage(url: card.card.image(), width: 32),
      title: Text(card.card.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          'Nr. ${card.card.number}',
          if (showChange && card.avg30 != null) '${money(card.avg30)} → ${money(card.trend)}',
        ].join(' · '),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(card.trend), style: const TextStyle(fontWeight: FontWeight.w700)),
          if (showChange && change != null)
            Text(signedPercent(change), style: TextStyle(color: color, fontSize: 12)),
        ],
      ),
    );
  }
}
