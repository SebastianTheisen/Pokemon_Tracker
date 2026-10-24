// Versiegeltes Produkt hinzufügen – aufgebaut wie bei Collectr:
//
// * Start: die neuesten Sets mit versiegelten Produkten zum Durchblättern (kein leerer Bildschirm).
// * Suche (deutsch oder englisch, der Server übersetzt) und Filter nach Art (Display, Top-Trainer-
//   Box, Booster …); Treffer als Raster mit großen Bildern und Wert.
// * Produkt antippen → Blatt mit Bild, Preisen, Sprache, Anzahl und optional Kaufpreis/-datum
//   (für Gewinn und Verlust in der Sammlung).
//
// Der Wert kommt danach täglich aus dem offiziellen Cardmarket-Preisführer (Median aus Trend,
// Ø 7 und Ø 30 Tagen).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import 'item_sheet.dart';
import 'owned.dart';
import '../card/card_detail_screen.dart';
import '../dashboard/dashboard_screen.dart';
import 'collection_screen.dart';

const _minQueryLength = 2;

/// Arten in der Reihenfolge der Filter (häufigste zuerst).
const sealedKinds = [
  'display',
  'elite_trainer_box',
  'booster_bundle',
  'booster',
  'collection_box',
  'tin',
  'blister',
];

final sealedSetsProvider = FutureProvider.autoDispose<List<SealedSet>>(
  (ref) => ref.watch(apiProvider).sealedSets(),
);

class SealedAddScreen extends ConsumerStatefulWidget {
  const SealedAddScreen({super.key});

  @override
  ConsumerState<SealedAddScreen> createState() => _SealedAddScreenState();
}

class _SealedAddScreenState extends ConsumerState<SealedAddScreen> {
  final _search = TextEditingController();
  Timer? _debounce;
  String _query = '';
  String? _kind;
  SealedSet? _set;
  Future<List<SealedOffer>>? _results;

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  bool get _browsing => _set == null && _query.length < _minQueryLength;

  void _reload() {
    _results = _browsing
        ? null
        : ref.read(apiProvider).searchSealed(_query, kind: _kind, expansion: _set?.expansionId);
  }

  void _onChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      final query = text.trim();
      if (!mounted || query == _query) return;
      setState(() {
        _query = query;
        _reload();
      });
    });
  }

  void _chooseKind(String? kind) => setState(() {
    _kind = kind;
    _reload();
  });

  void _openSet(SealedSet? set) => setState(() {
    _set = set;
    _reload();
  });

  Future<void> _add(SealedOffer offer) async {
    final choice = await showModalBottomSheet<_AddChoice>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => _AddSheet(offer: offer),
    );
    if (choice == null || !mounted) return;
    final api = ref.read(apiProvider);
    final ok = await runAction(context, () async {
      final product = await api.productFromCardmarket(offer.cardmarketProductId, choice.language);
      await api.addItem({
        'product_id': product.id,
        'folder_id': ?effectiveFolderId(
          ref.read(folderChoiceProvider),
          ref.read(foldersProvider).value ?? const <Folder>[],
        ),
        'quantity': choice.quantity,
        'purchase_price': ?choice.purchasePrice,
        'purchase_date': ?choice.purchaseDate,
      });
    });
    if (!ok || !mounted) return;
    ref.invalidate(itemsProvider);
    invalidateCollection(ref);
    showMessage(context, 'Hinzugefügt: ${choice.quantity}× ${offer.name}');
  }

  @override
  Widget build(BuildContext context) => PopScope(
    // Zurück aus einem Set führt zur Set-Übersicht, nicht aus dem Bildschirm.
    canPop: _set == null,
    onPopInvokedWithResult: (didPop, _) {
      if (!didPop) _openSet(null);
    },
    child: Scaffold(
      appBar: AppBar(title: Text(_set?.name ?? 'Versiegeltes hinzufügen')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              key: const Key('sealed-search'),
              controller: _search,
              onChanged: _onChanged,
              decoration: InputDecoration(
                prefixIcon: const Icon(Icons.search),
                hintText: _set == null
                    ? 'z. B. Prismatische Entwicklungen Top-Trainer-Box'
                    : 'In ${_set!.name} suchen',
              ),
            ),
          ),
          _KindFilter(selected: _kind, onSelected: _chooseKind),
          Expanded(
            child: _browsing
                ? _SetGrid(onOpen: _openSet)
                : _OfferGrid(results: _results, onAdd: _add),
          ),
        ],
      ),
    ),
  );
}

class _KindFilter extends StatelessWidget {
  const _KindFilter({required this.selected, required this.onSelected});

  final String? selected;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 48,
    child: ListView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      children: [
        for (final kind in [null, ...sealedKinds])
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              key: Key('sealed-kind-${kind ?? 'all'}'),
              label: Text(kind == null ? 'Alle' : productKindLabels[kind] ?? kind),
              selected: selected == kind,
              onSelected: (_) => onSelected(kind),
            ),
          ),
      ],
    ),
  );
}

/// Start: neueste Sets mit versiegelten Produkten.
class _SetGrid extends ConsumerWidget {
  const _SetGrid({required this.onOpen});

  final ValueChanged<SealedSet> onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) => AsyncBody(
    value: ref.watch(sealedSetsProvider),
    onRetry: () => ref.invalidate(sealedSetsProvider),
    builder: (sets) => sets.isEmpty
        ? const EmptyView(
            icon: Icons.inventory_2_outlined,
            message: 'Booster, Displays, Top-Trainer-Boxen, Tins … oben suchen.',
          )
        : CustomScrollView(
            slivers: [
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: SectionTitle('Neueste Sets'),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                sliver: SliverGrid.builder(
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                    maxCrossAxisExtent: 220,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 0.95,
                  ),
                  itemCount: sets.length,
                  itemBuilder: (context, index) => _SetTile(set: sets[index], onOpen: onOpen),
                ),
              ),
            ],
          ),
  );
}

class _SetTile extends StatelessWidget {
  const _SetTile({required this.set, required this.onOpen});

  final SealedSet set;
  final ValueChanged<SealedSet> onOpen;

  @override
  Widget build(BuildContext context) => Card(
    key: Key('sealed-set-${set.expansionId}'),
    clipBehavior: Clip.antiAlias,
    margin: EdgeInsets.zero,
    child: InkWell(
      onTap: () => onOpen(set),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: _ProductImage(url: set.imageUrl ?? set.logoUrl, fallback: set.logoUrl),
            ),
            const SizedBox(height: 8),
            Text(
              set.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            Text(
              [
                '${set.products} Produkte',
                if (set.releaseDate != null) date(set.releaseDate),
              ].join(' · '),
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ],
        ),
      ),
    ),
  );
}

class _OfferGrid extends StatelessWidget {
  const _OfferGrid({required this.results, required this.onAdd});

  final Future<List<SealedOffer>>? results;
  final ValueChanged<SealedOffer> onAdd;

  @override
  Widget build(BuildContext context) => FutureBuilder<List<SealedOffer>>(
    future: results,
    builder: (context, snapshot) {
      if (snapshot.hasError) return ErrorView(message: '${snapshot.error}');
      final offers = snapshot.data;
      if (offers == null) return const Center(child: CircularProgressIndicator());
      if (offers.isEmpty) {
        return const EmptyView(
          icon: Icons.search_off,
          message: 'Nichts gefunden – weniger Wörter, andere Art oder den englischen Namen.',
        );
      }
      return GridView.builder(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
          maxCrossAxisExtent: 220,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 0.68,
        ),
        itemCount: offers.length,
        itemBuilder: (context, index) =>
            _OfferCard(offer: offers[index], onTap: () => onAdd(offers[index])),
      );
    },
  );
}

class _OfferCard extends StatelessWidget {
  const _OfferCard({required this.offer, required this.onTap});

  final SealedOffer offer;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    key: Key('sealed-${offer.cardmarketProductId}'),
    clipBehavior: Clip.antiAlias,
    margin: EdgeInsets.zero,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: _ProductImage(url: offer.imageUrl)),
            const SizedBox(height: 8),
            Text(
              offer.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
            ),
            Text(
              productKindLabels[offer.kind] ?? offer.kind,
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 4),
            Text(
              offer.value == null ? 'noch kein Preis' : money(offer.value),
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: offer.value == null ? AppColors.textMuted : AppColors.primary,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Verpackungsbild (ganz sichtbar) auf hellem Grund; ohne Bild ein Platzhalter.
class _ProductImage extends StatelessWidget {
  const _ProductImage({required this.url, this.fallback});

  final String? url;
  final String? fallback;

  @override
  Widget build(BuildContext context) {
    const placeholder = Center(
      child: Icon(Icons.inventory_2_outlined, color: AppColors.textMuted, size: 40),
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceHigh,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.all(6),
        child: url == null
            ? placeholder
            : Image.network(
                url!,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => fallback != null && fallback != url
                    ? Image.network(fallback!, fit: BoxFit.contain)
                    : placeholder,
              ),
      ),
    );
  }
}

typedef _AddChoice = ({String language, int quantity, String? purchasePrice, String? purchaseDate});

/// Produktblatt: Bild, Preise, Sprache, Anzahl, optional Kaufpreis und Kaufdatum.
class _AddSheet extends StatefulWidget {
  const _AddSheet({required this.offer});

  final SealedOffer offer;

  @override
  State<_AddSheet> createState() => _AddSheetState();
}

class _AddSheetState extends State<_AddSheet> {
  static const _mainLanguages = ['de', 'en', 'ja'];

  final _price = TextEditingController();
  String _language = 'de';
  int _quantity = 1;
  DateTime? _bought;

  @override
  void dispose() {
    _price.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _bought ?? now,
      firstDate: DateTime(1996),
      lastDate: now,
    );
    if (picked != null) setState(() => _bought = picked);
  }

  void _submit() {
    final price = normalizeAmount(_price.text);
    if (price != null && double.tryParse(price) == null) {
      showMessage(context, 'Kaufpreis bitte als Zahl eingeben, z. B. 54,90');
      return;
    }
    Navigator.of(context).pop((
      language: _language,
      quantity: _quantity,
      purchasePrice: price,
      purchaseDate: _bought?.toIso8601String().substring(0, 10),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final offer = widget.offer;
    final prices = [
      if (offer.trend != null) 'Trend ${money(offer.trend)}',
      if (offer.low != null) 'ab ${money(offer.low)}',
    ];
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          16,
          0,
          16,
          16 + MediaQuery.viewInsetsOf(context).bottom, // Tastatur
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(height: 160, child: _ProductImage(url: offer.imageUrl)),
            const SizedBox(height: 12),
            Text(
              offer.name,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
            ),
            Text(
              [productKindLabels[offer.kind] ?? offer.kind, ?offer.setName].join(' · '),
              style: const TextStyle(color: AppColors.textMuted),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        offer.value == null ? 'noch kein Preis' : money(offer.value),
                        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                      ),
                      if (prices.isNotEmpty)
                        Text(
                          prices.join(' · '),
                          style: const TextStyle(color: AppColors.textMuted),
                        ),
                    ],
                  ),
                ),
                TextButton.icon(
                  onPressed: () => openLink(context, offer.url),
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: const Text('Cardmarket'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text('Sprache'),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                for (final language in [
                  ..._mainLanguages,
                  ...languageLabels.keys.where((l) => !_mainLanguages.contains(l)),
                ])
                  ChoiceChip(
                    key: Key('sealed-language-$language'),
                    label: Text(languageTag(language)),
                    tooltip: languageLabels[language],
                    selected: _language == language,
                    onSelected: (_) => setState(() => _language = language),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                const Expanded(child: Text('Anzahl')),
                IconButton(
                  onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null,
                  icon: const Icon(Icons.remove_circle_outline),
                ),
                Text('$_quantity', style: const TextStyle(fontSize: 18)),
                IconButton(
                  key: const Key('sealed-more'),
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
                    key: const Key('sealed-price'),
                    controller: _price,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Kaufpreis je Stück (optional)',
                      suffixText: '€',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  key: const Key('sealed-date'),
                  onPressed: _pickDate,
                  icon: const Icon(Icons.event, size: 18),
                  label: Text(_bought == null ? 'Kaufdatum' : date(_bought)),
                ),
              ],
            ),
            const SizedBox(height: 16),
            const Align(alignment: Alignment.centerLeft, child: FolderPicker()),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const Key('sealed-add'),
              onPressed: _submit,
              icon: const Icon(Icons.add),
              label: const Text('Zur Sammlung hinzufügen'),
            ),
          ],
        ),
      ),
    );
  }
}
