// Filter der Sammlung: Ordner, Art, Text, Sortierung und erweiterte Filter (Blatt „Filter“).
import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../widgets/common.dart';

/// Platzhalter für `copyWith`: „unverändert“ (im Unterschied zu `null` = Filter löschen).
const Object _keep = Object();

@immutable
class ItemFilter {
  const ItemFilter({
    this.folderId,
    this.kind,
    this.query = '',
    this.sort = 'value_desc',
    this.language,
    this.condition,
    this.minValue,
    this.maxValue,
    this.withPurchase,
  });

  final String? folderId;
  final String? kind;
  final String query;
  final String sort;

  /// Erweiterte Filter (Blatt „Filter“).
  final String? language;
  final String? condition;

  /// Gesamtwert der Position in Euro (Server-Format „12.50“).
  final String? minValue;
  final String? maxValue;

  /// `true` nur mit Kaufpreis, `false` nur ohne.
  final bool? withPurchase;

  /// Anzahl aktiver erweiterter Filter (für das Abzeichen am Filter-Knopf).
  int get extraCount => [
    language,
    condition,
    minValue,
    maxValue,
    withPurchase,
  ].where((value) => value != null).length;

  ItemFilter copyWith({
    Object? folderId = _keep,
    Object? kind = _keep,
    String? query,
    String? sort,
    Object? language = _keep,
    Object? condition = _keep,
    Object? minValue = _keep,
    Object? maxValue = _keep,
    Object? withPurchase = _keep,
  }) => ItemFilter(
    folderId: identical(folderId, _keep) ? this.folderId : folderId as String?,
    kind: identical(kind, _keep) ? this.kind : kind as String?,
    query: query ?? this.query,
    sort: sort ?? this.sort,
    language: identical(language, _keep) ? this.language : language as String?,
    condition: identical(condition, _keep) ? this.condition : condition as String?,
    minValue: identical(minValue, _keep) ? this.minValue : minValue as String?,
    maxValue: identical(maxValue, _keep) ? this.maxValue : maxValue as String?,
    withPurchase: identical(withPurchase, _keep) ? this.withPurchase : withPurchase as bool?,
  );

  /// Erweiterte Filter zurücksetzen (Ordner, Art, Text und Sortierung bleiben).
  ItemFilter clearExtras() => ItemFilter(folderId: folderId, kind: kind, query: query, sort: sort);

  List<Object?> get _fields => [
    folderId,
    kind,
    query,
    sort,
    language,
    condition,
    minValue,
    maxValue,
    withPurchase,
  ];

  @override
  bool operator ==(Object other) =>
      other is ItemFilter &&
      Iterable<int>.generate(_fields.length).every((i) => _fields[i] == other._fields[i]);

  @override
  int get hashCode => Object.hashAll(_fields);
}

/// Blatt „Filter“: Sprache, Zustand, Wertspanne, Kaufpreis. Gibt den neuen Filter zurück.
Future<ItemFilter?> showItemFilterSheet(BuildContext context, ItemFilter filter) =>
    showModalBottomSheet<ItemFilter>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _FilterSheet(filter: filter),
    );

class _FilterSheet extends StatefulWidget {
  const _FilterSheet({required this.filter});

  final ItemFilter filter;

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late String? _language = widget.filter.language;
  late String? _condition = widget.filter.condition;
  late bool? _withPurchase = widget.filter.withPurchase;
  late final _min = TextEditingController(text: _display(widget.filter.minValue));
  late final _max = TextEditingController(text: _display(widget.filter.maxValue));

  static String _display(String? amount) => amount?.replaceAll('.', ',') ?? '';

  @override
  void dispose() {
    _min.dispose();
    _max.dispose();
    super.dispose();
  }

  /// Betrag aus dem Feld: `null` = leer; ungültig → Hinweis und Abbruch.
  (bool ok, String? value) _amount(TextEditingController controller) {
    final value = normalizeAmount(controller.text);
    if (value == null) return (true, null);
    final parsed = double.tryParse(value);
    if (parsed == null || parsed < 0) return (false, null);
    return (true, value);
  }

  void _apply() {
    final (minOk, min) = _amount(_min);
    final (maxOk, max) = _amount(_max);
    if (!minOk || !maxOk) {
      showMessage(context, 'Wert bitte als Zahl eingeben, z. B. 10 oder 99,90');
      return;
    }
    if (min != null && max != null && double.parse(min) > double.parse(max)) {
      showMessage(context, '„von“ ist größer als „bis“.');
      return;
    }
    Navigator.of(context).pop(
      widget.filter.copyWith(
        language: _language,
        condition: _condition,
        minValue: min,
        maxValue: max,
        withPurchase: _withPurchase,
      ),
    );
  }

  Widget _chips<T>(
    String keyPrefix,
    Map<T?, String> options,
    T? selected,
    ValueChanged<T?> onSelected,
  ) => Wrap(
    spacing: 8,
    runSpacing: 4,
    children: [
      for (final MapEntry(:key, :value) in options.entries)
        ChoiceChip(
          key: Key('$keyPrefix-${key ?? 'all'}'),
          label: Text(value),
          selected: selected == key,
          onSelected: (_) => setState(() => onSelected(key)),
        ),
    ],
  );

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
    child: SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          const SectionTitle('Filter'),
          const Text('Sprache'),
          const SizedBox(height: 6),
          _chips<String>(
            'filter-language',
            {
              null: 'Alle',
              for (final language in languageLabels.keys) language: languageTag(language),
            },
            _language,
            (value) => _language = value,
          ),
          const SizedBox(height: 16),
          const Text('Zustand (nur Rohkarten)'),
          const SizedBox(height: 6),
          _chips<String>(
            'filter-condition',
            {null: 'Alle', for (final condition in conditionLabels.keys) condition: condition},
            _condition,
            (value) => _condition = value,
          ),
          const SizedBox(height: 16),
          const Text('Wert der Position'),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: TextField(
                  key: const Key('filter-min'),
                  controller: _min,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'von',
                    suffixText: '€',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  key: const Key('filter-max'),
                  controller: _max,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'bis',
                    suffixText: '€',
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Kaufpreis'),
          const SizedBox(height: 6),
          _chips<bool>(
            'filter-purchase',
            const {null: 'Egal', true: 'eingetragen', false: 'fehlt noch'},
            _withPurchase,
            (value) => _withPurchase = value,
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              TextButton(
                key: const Key('filter-reset'),
                onPressed: () => Navigator.of(context).pop(widget.filter.clearExtras()),
                child: const Text('Zurücksetzen'),
              ),
              const Spacer(),
              FilledButton(
                key: const Key('filter-apply'),
                onPressed: _apply,
                child: const Text('Anwenden'),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}
