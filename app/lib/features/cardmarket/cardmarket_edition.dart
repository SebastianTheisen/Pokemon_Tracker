// Cardmarket-Ausgabe (Sprachfassung) einer Karte anzeigen und ändern – im Scan-Ergebnis und
// auf der Kartenseite.
//
// Cardmarket führt manche Sets in mehreren Sprachfassungen gleichzeitig (z. B. 30th
// Celebration japanisch und vereinfacht-chinesisch). TCGdex erwischt dabei manchmal die
// falsche. Wählt jemand hier die richtige, gilt sie für das ganze Set und alle Nutzer.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../card/card_detail_screen.dart';

final cardmarketChoiceProvider = FutureProvider.autoDispose.family<CardmarketChoice, String>(
  (ref, cardId) => ref.watch(apiProvider).cardmarketChoice(cardId),
);

/// Zeile „Cardmarket-Ausgabe“ – nur sichtbar, wenn es Sprachfassungen zur Auswahl gibt.
class CardmarketEditionTile extends ConsumerWidget {
  const CardmarketEditionTile({required this.cardId, this.padding = EdgeInsets.zero, super.key});

  final String cardId;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      switch (ref.watch(cardmarketChoiceProvider(cardId))) {
        AsyncData(:final value) when value.hasAlternatives => Padding(
          padding: padding,
          child: _tile(context, value),
        ),
        _ => const SizedBox.shrink(),
      };

  Widget _tile(BuildContext context, CardmarketChoice choice) {
    final selected = choice.selected;
    final color = choice.uncertain ? AppColors.warning : AppColors.textMuted;
    final subtitle = switch (choice.reason) {
      _ when selected != null => '${selected.expansionTitle} · ${_origin(choice)}',
      'unmapped' => 'In der gewählten Ausgabe nicht gefunden',
      _ => 'Noch nicht zugeordnet',
    };
    return Material(
      color: choice.uncertain ? AppColors.warning.withValues(alpha: 0.12) : AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      child: ListTile(
        key: const Key('cardmarket-edition'),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        leading: Icon(
          choice.uncertain ? Icons.help_outline : Icons.storefront_outlined,
          color: color,
        ),
        title: Text(choice.uncertain ? 'Cardmarket-Sprachfassung prüfen' : 'Cardmarket-Ausgabe'),
        subtitle: Text(subtitle),
        trailing: const Text('Ändern', style: TextStyle(color: AppColors.primary)),
        onTap: () => showCardmarketEditionSheet(context, cardId),
      ),
    );
  }
}

String _origin(CardmarketChoice choice) => switch ((choice.reason, choice.setSource)) {
  ('card', _) => 'für diese Karte gewählt',
  (_, 'user') => 'von euch gewählt',
  (_, 'builtin') => 'geprüft',
  (_, 'matched') => 'über die Kartennamen zugeordnet',
  _ => 'laut TCGdex',
};

Future<void> showCardmarketEditionSheet(BuildContext context, String cardId) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => CardmarketEditionSheet(cardId: cardId),
    );

/// Auswahl der richtigen Sprachfassung: ansehen, benennen, übernehmen.
class CardmarketEditionSheet extends ConsumerStatefulWidget {
  const CardmarketEditionSheet({required this.cardId, super.key});

  final String cardId;

  @override
  ConsumerState<CardmarketEditionSheet> createState() => _CardmarketEditionSheetState();
}

class _CardmarketEditionSheetState extends ConsumerState<CardmarketEditionSheet> {
  int? _picked;
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final choice = ref.watch(cardmarketChoiceProvider(widget.cardId));
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: AsyncBody(
          value: choice,
          onRetry: () => ref.invalidate(cardmarketChoiceProvider(widget.cardId)),
          builder: _content,
        ),
      ),
    );
  }

  Widget _content(CardmarketChoice choice) {
    final picked = _picked ?? choice.selected?.productId;
    final unchanged = picked == choice.selected?.productId;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Cardmarket-Ausgabe wählen',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(
            'Cardmarket führt diese Karte in mehreren Sprachfassungen. Zum Prüfen öffnen und '
            'die richtige wählen – das gilt dann für alle Karten dieses Sets und für alle.',
            style: TextStyle(color: AppColors.textMuted),
          ),
          if (choice.uncertain)
            Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'Die aktuelle Zuordnung stammt nur von TCGdex und kann falsch sein.',
                style: TextStyle(color: AppColors.warning),
              ),
            ),
          const SizedBox(height: 8),
          for (final option in choice.options)
            _OptionTile(
              option: option,
              picked: option.productId == picked,
              onPick: _busy ? null : () => setState(() => _picked = option.productId),
              onLabel: _busy ? null : () => _label(option),
            ),
          const SizedBox(height: 12),
          FilledButton(
            key: const Key('cardmarket-edition-save'),
            // Gleiche Auswahl bestätigen ist sinnvoll, solange sie nur von TCGdex stammt.
            onPressed: _busy || picked == null || (unchanged && !choice.uncertain)
                ? null
                : () => _save(picked),
            child: Text(unchanged ? 'Bestätigen' : 'Übernehmen'),
          ),
        ],
      ),
    );
  }

  Future<void> _save(int productId) async {
    setState(() => _busy = true);
    CardmarketChoice? result;
    final ok = await runAction(context, () async {
      result = await ref.read(apiProvider).chooseCardmarket(widget.cardId, productId);
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (!ok) return;
    ref
      ..invalidate(cardmarketChoiceProvider(widget.cardId))
      ..invalidate(pricesProvider(widget.cardId));
    final affected = result?.cardsAffected ?? 1;
    final message = result?.setChanged ?? false
        ? 'Für das ganze Set übernommen ($affected Karten) – Preise werden neu geladen.'
        : 'Gespeichert – Preise werden neu geladen.';
    Navigator.of(context).pop();
    showMessage(context, message);
  }

  Future<void> _label(CardmarketOption option) async {
    final label = await showTextInput(
      context,
      title: 'Ausgabe ${option.expansionId} benennen',
      initial: option.expansionLabel ?? '',
      label: 'z. B. Japanisch',
      helper: 'Steht nicht bei Cardmarket im Download – gilt für alle.',
      confirm: 'Speichern',
    );
    if (label == null || !mounted) return;
    final ok = await runAction(
      context,
      () => ref.read(apiProvider).labelCardmarketExpansion(option.expansionId, label),
    );
    if (ok) ref.invalidate(cardmarketChoiceProvider(widget.cardId));
  }
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({
    required this.option,
    required this.picked,
    required this.onPick,
    required this.onLabel,
  });

  final CardmarketOption option;
  final bool picked;
  final VoidCallback? onPick;
  final VoidCallback? onLabel;

  @override
  Widget build(BuildContext context) {
    final prices = [
      if (option.trend != null) 'Trend ${money(option.trend)}',
      if (option.low != null) 'ab ${money(option.low)}',
    ];
    final details = [
      prices.isEmpty ? 'kein Preis' : prices.join(' · '),
      if (option.expansionSize != null) '${option.expansionSize} Karten in der Ausgabe',
    ].join(' · ');
    return ListTile(
      key: Key('cardmarket-option-${option.productId}'),
      contentPadding: EdgeInsets.zero,
      onTap: onPick,
      leading: Icon(
        picked ? Icons.radio_button_checked : Icons.radio_button_unchecked,
        color: picked ? AppColors.primary : AppColors.textMuted,
      ),
      title: Wrap(
        spacing: 6,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(option.expansionTitle, style: const TextStyle(fontWeight: FontWeight.w600)),
          if (option.selected) Tag('aktuell', color: AppColors.gain),
          if (option.fromTcgdex) Tag('TCGdex', color: AppColors.textMuted),
        ],
      ),
      subtitle: Text('${option.name}\n$details'),
      isThreeLine: true,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: 'Auf Cardmarket ansehen',
            icon: const Icon(Icons.open_in_new),
            onPressed: () => openLink(context, option.url),
          ),
          IconButton(
            key: Key('cardmarket-label-${option.expansionId}'),
            tooltip: 'Ausgabe benennen',
            icon: const Icon(Icons.edit_outlined),
            onPressed: onLabel,
          ),
        ],
      ),
    );
  }
}
