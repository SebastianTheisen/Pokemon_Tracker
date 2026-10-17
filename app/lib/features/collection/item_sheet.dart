// Formular zum Hinzufügen bzw. Bearbeiten einer Sammlungsposition (als Bottom-Sheet).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

final foldersProvider = FutureProvider.autoDispose<List<Folder>>(
  (ref) => ref.watch(apiProvider).folders(),
);

const gradingCompanies = ['PSA', 'BGS', 'CGC', 'OTHER'];

/// Öffnet das Formular. Gibt die gespeicherte Position zurück (oder `null`).
Future<CollectionItem?> showItemSheet(
  BuildContext context, {
  CardInfo? card,
  CollectionItem? item,
  Grading? grading,
}) => showModalBottomSheet<CollectionItem>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (_) => ItemForm(card: card, item: item, grading: grading),
);

class ItemForm extends ConsumerStatefulWidget {
  const ItemForm({this.card, this.item, this.grading, super.key})
    : assert(card != null || item != null, 'Karte oder Position nötig');

  final CardInfo? card;
  final CollectionItem? item;
  final Grading? grading;

  @override
  ConsumerState<ItemForm> createState() => _ItemFormState();
}

class _ItemFormState extends ConsumerState<ItemForm> {
  late final CollectionItem? _item = widget.item;
  late String? _folderId = _item?.folderId;
  late String _variant = _item?.variant ?? 'normal';
  late String _condition = _item?.condition ?? 'NM';
  late int _quantity = _item?.quantity ?? 1;
  late bool _graded = _item?.kind == 'graded' || widget.grading != null;
  late String _company = _item?.gradingCompany ?? widget.grading?.company ?? 'PSA';
  late final _grade = TextEditingController(text: _item?.grade ?? widget.grading?.grade ?? '');
  late final _purchase = TextEditingController(text: _item?.purchasePrice ?? '');
  late final _custom = TextEditingController(text: _item?.customPrice ?? '');
  late final _note = TextEditingController(text: _item?.note ?? '');
  bool _busy = false;

  bool get _isEdit => _item != null;
  bool get _isSealed => _item?.kind == 'sealed';

  @override
  void dispose() {
    for (final controller in [_grade, _purchase, _custom, _note]) {
      controller.dispose();
    }
    super.dispose();
  }

  /// „1.234,50“ / „12,50“ / „12.50“ → "1234.50" / "12.50"; leer → null.
  static String? _amount(TextEditingController controller) => normalizeAmount(controller.text);

  Map<String, Object?> _body() => {
    'folder_id': ?_folderId,
    if (!_isSealed) 'variant': _variant,
    if (!_isSealed && !_graded) 'condition': _condition,
    'quantity': _quantity,
    'purchase_price': _amount(_purchase),
    'custom_price': _amount(_custom),
    'note': _note.text.trim().isEmpty ? null : _note.text.trim(),
    if (_graded && !_isEdit) 'grading_company': _company,
    if (_graded) 'grade': _grade.text.trim().isEmpty ? null : _grade.text.trim(),
  };

  Future<void> _save() async {
    final amounts = [_amount(_purchase), _amount(_custom)];
    if (amounts.any((value) => value != null && double.tryParse(value) == null)) {
      showMessage(context, 'Preise bitte als Zahl eingeben, z. B. 12,50');
      return;
    }
    setState(() => _busy = true);
    final api = ref.read(apiProvider);
    CollectionItem? saved;
    final ok = await runAction(context, () async {
      saved = _isEdit
          ? await api.updateItem(_item!.id, _body())
          : await api.addItem({'card_id': widget.card!.id, ..._body()});
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.of(context).pop(saved);
  }

  @override
  Widget build(BuildContext context) {
    final folders = ref.watch(foldersProvider).value ?? const <Folder>[];
    final title = widget.card?.name ?? _item!.title;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _isEdit ? 'Position bearbeiten' : 'Zur Sammlung hinzufügen',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            Text(title, style: const TextStyle(color: AppColors.textMuted)),
            const SizedBox(height: 16),
            if (folders.length > 1)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: _folderId ?? folders.first.id,
                  decoration: const InputDecoration(labelText: 'Ordner'),
                  items: [
                    for (final folder in folders)
                      DropdownMenuItem(value: folder.id, child: Text(folder.name)),
                  ],
                  onChanged: (value) => setState(() => _folderId = value),
                ),
              ),
            if (!_isSealed) ...[
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'normal', label: Text('Normal')),
                  ButtonSegment(value: 'reverse', label: Text('Reverse Holo')),
                ],
                selected: {_variant},
                onSelectionChanged: (value) => setState(() => _variant = value.first),
              ),
              const SizedBox(height: 12),
              if (!_isEdit || _graded)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Gegradet (Slab)'),
                  value: _graded,
                  onChanged: _isEdit ? null : (value) => setState(() => _graded = value),
                ),
              if (_graded)
                Row(
                  children: [
                    Expanded(
                      child: DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _company,
                        decoration: const InputDecoration(labelText: 'Firma'),
                        items: [
                          for (final company in gradingCompanies)
                            DropdownMenuItem(
                              value: company,
                              child: Text(company == 'OTHER' ? 'Andere' : company),
                            ),
                        ],
                        onChanged: _isEdit
                            ? null
                            : (value) => setState(() => _company = value ?? 'PSA'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: _grade,
                        decoration: const InputDecoration(labelText: 'Note, z. B. 10'),
                      ),
                    ),
                  ],
                )
              else
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final condition in conditions)
                      ChoiceChip(
                        label: Text(condition),
                        tooltip: conditionLabels[condition],
                        selected: _condition == condition,
                        onSelected: (_) => setState(() => _condition = condition),
                      ),
                  ],
                ),
              const SizedBox(height: 12),
            ],
            Row(
              children: [
                const Text('Menge'),
                const Spacer(),
                IconButton(
                  onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null,
                  icon: const Icon(Icons.remove_circle_outline),
                ),
                Text('$_quantity', style: const TextStyle(fontSize: 18)),
                IconButton(
                  onPressed: () => setState(() => _quantity++),
                  icon: const Icon(Icons.add_circle_outline),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _purchase,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Kaufpreis (Stück)',
                      suffixText: '€',
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _custom,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Eigenpreis', suffixText: '€'),
                  ),
                ),
              ],
            ),
            if (_graded || _isSealed)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text(
                  'Gegradete und versiegelte Positionen haben nur mit Eigenpreis einen Wert.',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ),
            const SizedBox(height: 12),
            TextField(
              controller: _note,
              maxLength: 500,
              decoration: const InputDecoration(labelText: 'Notiz (optional)'),
            ),
            const SizedBox(height: 8),
            FilledButton(
              key: const Key('item-save'),
              onPressed: _busy ? null : _save,
              child: Text(_isEdit ? 'Speichern' : 'Hinzufügen'),
            ),
          ],
        ),
      ),
    );
  }
}
