// Tausch-Rechner: „Ich gebe“ gegen „Ich bekomme“ – Werte live, speichern, später vergleichen.
//
// Der Entwurf lebt app-weit (tradeDraftProvider): Karten kommen aus der eigenen Sammlung,
// aus dem Showcase eines Freundes oder aus der Suche. Die Sammlung ändert sich dabei nicht.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../search/search_screen.dart';

class TradeDraft extends Notifier<List<TradeDraftLine>> {
  @override
  List<TradeDraftLine> build() => const [];

  /// Hinzufügen; gleiche Quelle auf gleicher Seite erhöht die Menge (bis zur Höchstmenge).
  void add(TradeDraftLine line) {
    final index = state.indexWhere((existing) => existing.sameSource(line));
    if (index < 0) {
      state = [...state, line];
      return;
    }
    setQuantity(index, state[index].quantity + line.quantity);
  }

  void setQuantity(int index, int quantity) {
    final line = state[index];
    final max = line.maxQuantity;
    final clamped = quantity.clamp(1, max ?? 999);
    state = [
      for (var i = 0; i < state.length; i++) i == index ? line.withQuantity(clamped) : state[i],
    ];
  }

  void removeAt(int index) => state = [...state]..removeAt(index);

  void clear() => state = const [];
}

final tradeDraftProvider = NotifierProvider<TradeDraft, List<TradeDraftLine>>(TradeDraft.new);

/// Bewertung des Entwurfs (neu bei jeder Änderung).
final tradeValueProvider = FutureProvider.autoDispose<TradeValue?>((ref) async {
  final lines = ref.watch(tradeDraftProvider);
  if (lines.isEmpty) return null;
  return ref.watch(apiProvider).evaluateTrade(lines);
});

final savedTradesProvider = FutureProvider.autoDispose<List<SavedTrade>>(
  (ref) => ref.watch(apiProvider).trades(),
);

/// Position (eigene oder vom Freund) in den Tausch legen und kurz bestätigen.
void addItemToTrade(BuildContext context, WidgetRef ref, CollectionItem item, String side) {
  ref
      .read(tradeDraftProvider.notifier)
      .add(TradeDraftLine(side: side, itemId: item.id, maxQuantity: item.quantity));
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text('${item.title} → ${side == 'give' ? '„Ich gebe“' : '„Ich bekomme“'}'),
        // Mit Knopf blieb der Hinweis sonst stehen, bis man ihn wegtippt.
        persist: false,
        action: SnackBarAction(
          label: 'Zum Tausch',
          onPressed: () => GoRouter.of(context).push('/trade'),
        ),
      ),
    );
}

class TradeScreen extends ConsumerWidget {
  const TradeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => DefaultTabController(
    length: 2,
    child: Scaffold(
      appBar: AppBar(
        title: const Text('Tausch-Rechner'),
        bottom: const TabBar(
          tabs: [
            Tab(key: Key('tab-trade-draft'), text: 'Rechner'),
            Tab(key: Key('tab-trade-saved'), text: 'Gespeichert'),
          ],
        ),
      ),
      body: const TabBarView(children: [_DraftView(), _SavedView()]),
    ),
  );
}

class _DraftView extends ConsumerWidget {
  const _DraftView();

  Future<void> _addMine(BuildContext context, WidgetRef ref) async {
    final item = await showModalBottomSheet<CollectionItem>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => const _MyItemPicker(),
    );
    if (item != null) {
      ref
          .read(tradeDraftProvider.notifier)
          .add(TradeDraftLine(side: 'give', itemId: item.id, maxQuantity: item.quantity));
    }
  }

  Future<void> _addCard(BuildContext context, WidgetRef ref, String side) async {
    final card = await showModalBottomSheet<CardInfo>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => SizedBox(
        height: MediaQuery.sizeOf(sheetContext).height * 0.85,
        child: CardSearch(
          autofocus: true,
          onSelect: (card) => Navigator.of(sheetContext).pop(card),
        ),
      ),
    );
    if (card != null) {
      ref.read(tradeDraftProvider.notifier).add(TradeDraftLine(side: side, cardId: card.id));
    }
  }

  Future<void> _save(BuildContext context, WidgetRef ref) async {
    final answer = await showDialog<({String partner, String note})>(
      context: context,
      builder: (_) => const _SaveDialog(),
    );
    if (answer == null || !context.mounted) return;
    final (:partner, :note) = answer;
    final lines = ref.read(tradeDraftProvider);
    final ok = await runAction(
      context,
      () => ref
          .read(apiProvider)
          .saveTrade(
            lines,
            partner: partner.isEmpty ? null : partner,
            note: note.isEmpty ? null : note,
          ),
    );
    if (!ok || !context.mounted) return;
    ref
      ..invalidate(savedTradesProvider)
      ..read(tradeDraftProvider.notifier).clear();
    showMessage(
      context,
      'Tausch gespeichert. Die Sammlung bleibt unverändert – Karten danach selbst '
      'hinzufügen bzw. entfernen.',
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(tradeDraftProvider);
    final value = ref.watch(tradeValueProvider);
    final result = value.value;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        if (result != null) _Summary(value: result, onSave: () => _save(context, ref)),
        for (final (side, title, emptyText) in [
          ('give', 'Ich gebe', 'Noch nichts – aus deiner Sammlung wählen.'),
          ('get', 'Ich bekomme', 'Noch nichts – Karte suchen oder beim Freund auswählen.'),
        ]) ...[
          SectionTitle(title),
          if (!draft.any((line) => line.side == side))
            Text(emptyText, style: TextStyle(color: AppColors.textMuted)),
          for (var i = 0; i < draft.length; i++)
            if (draft[i].side == side)
              _LineTile(
                index: i,
                line: draft[i],
                value: result != null && i < result.lines.length ? result.lines[i] : null,
              ),
          Wrap(
            spacing: 8,
            children: [
              if (side == 'give')
                TextButton.icon(
                  key: const Key('trade-add-mine'),
                  onPressed: () => _addMine(context, ref),
                  icon: const Icon(Icons.collections_bookmark_outlined),
                  label: const Text('Aus meiner Sammlung'),
                ),
              TextButton.icon(
                key: Key('trade-add-card-$side'),
                onPressed: () => _addCard(context, ref, side),
                icon: const Icon(Icons.search),
                label: const Text('Karte suchen'),
              ),
              if (side == 'get')
                TextButton.icon(
                  onPressed: () => context.push('/friends'),
                  icon: const Icon(Icons.people_outline),
                  label: const Text('Bei Freunden'),
                ),
            ],
          ),
        ],
        if (value.isLoading && draft.isNotEmpty)
          const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()),
        if (value.hasError) Text('${value.error}', style: TextStyle(color: AppColors.loss)),
        const SizedBox(height: 16),
        if (draft.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => ref.read(tradeDraftProvider.notifier).clear(),
              icon: const Icon(Icons.clear_all),
              label: const Text('Alles leeren'),
            ),
          ),
      ],
    );
  }
}

/// Mit wem und Notiz – besitzt seine Eingabefelder selbst (sicher beim Schließen).
class _SaveDialog extends StatefulWidget {
  const _SaveDialog();

  @override
  State<_SaveDialog> createState() => _SaveDialogState();
}

class _SaveDialogState extends State<_SaveDialog> {
  final _partner = TextEditingController();
  final _note = TextEditingController();

  @override
  void dispose() {
    _partner.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tausch speichern'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TextField(
          key: const Key('trade-partner'),
          controller: _partner,
          decoration: const InputDecoration(labelText: 'Mit wem? (optional)'),
        ),
        TextField(
          key: const Key('trade-note'),
          controller: _note,
          decoration: const InputDecoration(labelText: 'Notiz (optional)'),
        ),
      ],
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(
        key: const Key('trade-save-confirm'),
        onPressed: () =>
            Navigator.of(context).pop((partner: _partner.text.trim(), note: _note.text.trim())),
        child: const Text('Speichern'),
      ),
    ],
  );
}

/// Gebe / Bekomme / Differenz – grün, wenn der Tausch für mich gut ist.
class _Summary extends StatelessWidget {
  const _Summary({required this.value, required this.onSave});

  final TradeValue value;

  /// Oben statt unten: Hinweise am unteren Rand verdecken den Knopf sonst.
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    final diff = parseAmount(value.difference) ?? 0;
    final color = diff > 0 ? AppColors.gain : (diff < 0 ? AppColors.loss : AppColors.textMuted);
    return Card(
      key: const Key('trade-summary'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: _Amount(label: 'Ich gebe', amount: value.giveValue),
                ),
                Expanded(
                  child: _Amount(label: 'Ich bekomme', amount: value.getValue),
                ),
              ],
            ),
            const Divider(),
            Text(
              diff == 0
                  ? 'Ausgeglichen'
                  // Aus deiner Sicht: + = du bekommst mehr Wert, − = du gibst mehr Wert ab.
                  : '${signedMoney(value.difference)} für dich · '
                        '${diff > 0 ? 'du bekommst mehr' : 'du gibst mehr'}',
              key: const Key('trade-difference'),
              textAlign: TextAlign.center,
              style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.w700),
            ),
            if (value.unvalued > 0)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${value.unvalued} ohne bekannten Wert – zählen nicht mit.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.warning, fontSize: 12),
                ),
              ),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const Key('trade-save'),
              onPressed: onSave,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Tausch speichern'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Amount extends StatelessWidget {
  const _Amount({required this.label, required this.amount});

  final String label;
  final String amount;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Text(label, style: TextStyle(color: AppColors.textMuted)),
      Text(money(amount), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
    ],
  );
}

class _LineTile extends ConsumerWidget {
  const _LineTile({required this.index, required this.line, this.value});

  final int index;
  final TradeDraftLine line;
  final TradeLineValue? value;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.read(tradeDraftProvider.notifier);
    return ListTile(
      key: Key('trade-line-$index'),
      contentPadding: EdgeInsets.zero,
      leading: CardImage(url: cardImageUrl(value?.imageUrl), width: 36),
      title: Text(value?.label ?? '…', maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        value == null
            ? ''
            : value!.unitValue == null
            ? 'kein Wert'
            : '${line.quantity} × ${money(value!.unitValue)} = ${money(value!.total)}',
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: 'Weniger',
            onPressed: line.quantity > 1
                ? () => draft.setQuantity(index, line.quantity - 1)
                : () => draft.removeAt(index),
            icon: Icon(line.quantity > 1 ? Icons.remove : Icons.delete_outline),
          ),
          Text('${line.quantity}'),
          IconButton(
            key: Key('trade-more-$index'),
            tooltip: 'Mehr',
            onPressed: line.maxQuantity != null && line.quantity >= line.maxQuantity!
                ? null
                : () => draft.setQuantity(index, line.quantity + 1),
            icon: const Icon(Icons.add),
          ),
        ],
      ),
    );
  }
}

final _myItemsProvider = FutureProvider.autoDispose.family<ItemPage, String>(
  (ref, query) => ref.watch(apiProvider).items(query: query, sort: 'value_desc', limit: 100),
);

/// Eigene Positionen zum Geben auswählen (mit Suche).
class _MyItemPicker extends ConsumerStatefulWidget {
  const _MyItemPicker();

  @override
  ConsumerState<_MyItemPicker> createState() => _MyItemPickerState();
}

class _MyItemPickerState extends ConsumerState<_MyItemPicker> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(_myItemsProvider(_query));
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.85,
      child: Column(
        children: [
          const SectionTitle('Aus meiner Sammlung'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: TextField(
              key: const Key('trade-pick-search'),
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Name',
                isDense: true,
              ),
              onSubmitted: (text) => setState(() => _query = text.trim()),
            ),
          ),
          Expanded(
            child: AsyncBody(
              value: items,
              builder: (page) => ListView(
                children: [
                  for (final item in page.items)
                    ListTile(
                      key: Key('trade-pick-${item.id}'),
                      leading: CardImage(url: item.image, width: 36, contain: item.card == null),
                      title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text('${item.label} · ×${item.quantity}'),
                      trailing: Text(money(item.value.unitValue)),
                      onTap: () => Navigator.of(context).pop(item),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SavedView extends ConsumerWidget {
  const _SavedView();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final trades = ref.watch(savedTradesProvider);
    return AsyncBody(
      value: trades,
      onRetry: () => ref.invalidate(savedTradesProvider),
      builder: (list) => list.isEmpty
          ? const EmptyView(icon: Icons.swap_horiz, message: 'Noch keine gespeicherten Tausche.')
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [for (final trade in list) _SavedTile(trade: trade)],
            ),
    );
  }
}

class _SavedTile extends ConsumerWidget {
  const _SavedTile({required this.trade});

  final SavedTrade trade;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final then = trade.differenceThen;
    final now = parseAmount(trade.now.difference) ?? 0;
    Color colorOf(double value) =>
        value > 0 ? AppColors.gain : (value < 0 ? AppColors.loss : AppColors.textMuted);
    return Card(
      key: Key('trade-${trade.id}'),
      child: ExpansionTile(
        title: Text(
          [?trade.partner, date(trade.createdAt)].join(' · '),
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Text.rich(
          TextSpan(
            children: [
              const TextSpan(text: 'damals '),
              TextSpan(
                text: signedMoney(then.toStringAsFixed(2)),
                style: TextStyle(color: colorOf(then)),
              ),
              const TextSpan(text: ' · heute '),
              TextSpan(
                text: signedMoney(trade.now.difference),
                style: TextStyle(color: colorOf(now), fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ),
        children: [
          if (trade.note case final note?)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Align(alignment: Alignment.centerLeft, child: Text(note)),
            ),
          for (final line in trade.now.lines)
            ListTile(
              dense: true,
              leading: Icon(
                line.side == 'give' ? Icons.arrow_upward : Icons.arrow_downward,
                color: line.side == 'give' ? AppColors.loss : AppColors.gain,
              ),
              title: Text(line.label, maxLines: 2, overflow: TextOverflow.ellipsis),
              trailing: Text('${line.quantity} × ${money(line.unitValue)}'),
            ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () async {
                if (await runAction(context, () => ref.read(apiProvider).deleteTrade(trade.id))) {
                  ref.invalidate(savedTradesProvider);
                }
              },
              icon: const Icon(Icons.delete_outline),
              label: const Text('Löschen'),
            ),
          ),
        ],
      ),
    );
  }
}
