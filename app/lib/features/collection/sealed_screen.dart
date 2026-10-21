// Versiegeltes Produkt hinzufügen: im Cardmarket-Katalog suchen (englische Namen wie bei
// Cardmarket), Sprache und Anzahl wählen. Der Wert kommt danach täglich aus dem offiziellen
// Cardmarket-Preisführer (Median aus Trend, Ø 7 und Ø 30 Tagen).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../card/card_detail_screen.dart';
import '../dashboard/dashboard_screen.dart';
import 'collection_screen.dart';

const _minQueryLength = 2;

class SealedAddScreen extends ConsumerStatefulWidget {
  const SealedAddScreen({super.key});

  @override
  ConsumerState<SealedAddScreen> createState() => _SealedAddScreenState();
}

class _SealedAddScreenState extends ConsumerState<SealedAddScreen> {
  Timer? _debounce;
  String _query = '';
  Future<List<SealedOffer>>? _results;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _onChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      final query = text.trim();
      if (!mounted || query == _query) return;
      setState(() {
        _query = query;
        _results = query.length < _minQueryLength
            ? null
            : ref.read(apiProvider).searchSealed(query);
      });
    });
  }

  Future<void> _add(SealedOffer offer) async {
    final choice = await showModalBottomSheet<({String language, int quantity})>(
      context: context,
      showDragHandle: true,
      builder: (_) => _AddSheet(offer: offer),
    );
    if (choice == null || !mounted) return;
    final api = ref.read(apiProvider);
    final ok = await runAction(context, () async {
      final product = await api.productFromCardmarket(offer.cardmarketProductId, choice.language);
      await api.addItem({'product_id': product.id, 'quantity': choice.quantity});
    });
    if (!ok || !mounted) return;
    ref
      ..invalidate(itemsProvider)
      ..invalidate(dashboardProvider);
    showMessage(context, 'Hinzugefügt: ${choice.quantity}× ${offer.name}');
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Versiegeltes hinzufügen')),
    body: Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: TextField(
            key: const Key('sealed-search'),
            autofocus: true,
            onChanged: _onChanged,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'z. B. Prismatic Evolutions Elite Trainer Box',
              helperText:
                  'Namen wie bei Cardmarket (englisch). Preise aus dem Cardmarket-Preisführer.',
            ),
          ),
        ),
        Expanded(
          child: _results == null
              ? const EmptyView(
                  icon: Icons.inventory_2_outlined,
                  message: 'Booster, Displays, Elite Trainer Boxen, Tins … suchen.',
                )
              : FutureBuilder<List<SealedOffer>>(
                  future: _results,
                  builder: (context, snapshot) {
                    if (snapshot.hasError) return ErrorView(message: '${snapshot.error}');
                    final offers = snapshot.data;
                    if (offers == null) return const Center(child: CircularProgressIndicator());
                    if (offers.isEmpty) {
                      return const EmptyView(
                        icon: Icons.search_off,
                        message: 'Nichts gefunden – englischen Namen wie bei Cardmarket probieren.',
                      );
                    }
                    return ListView.builder(
                      itemCount: offers.length,
                      itemBuilder: (context, index) =>
                          _OfferTile(offer: offers[index], onAdd: () => _add(offers[index])),
                    );
                  },
                ),
        ),
      ],
    ),
  );
}

class _OfferTile extends StatelessWidget {
  const _OfferTile({required this.offer, required this.onAdd});

  final SealedOffer offer;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final prices = [
      if (offer.value != null) 'Wert ${money(offer.value)}',
      if (offer.trend != null) 'Trend ${money(offer.trend)}',
      if (offer.low != null) 'ab ${money(offer.low)}',
    ];
    return ListTile(
      key: Key('sealed-${offer.cardmarketProductId}'),
      leading: const Icon(Icons.inventory_2_outlined),
      title: Text(offer.name),
      subtitle: Text(
        [
          productKindLabels[offer.kind] ?? offer.kind,
          if (prices.isEmpty) 'noch kein Preis' else prices.join(' · '),
        ].join(' · '),
      ),
      onTap: onAdd,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: 'Auf Cardmarket ansehen',
            icon: const Icon(Icons.open_in_new),
            onPressed: () => openLink(context, offer.url),
          ),
          IconButton(
            tooltip: 'Hinzufügen',
            icon: const Icon(Icons.add_circle_outline, color: AppColors.primary),
            onPressed: onAdd,
          ),
        ],
      ),
    );
  }
}

/// Sprache und Anzahl wählen.
class _AddSheet extends StatefulWidget {
  const _AddSheet({required this.offer});

  final SealedOffer offer;

  @override
  State<_AddSheet> createState() => _AddSheetState();
}

class _AddSheetState extends State<_AddSheet> {
  String _language = 'de';
  int _quantity = 1;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            widget.offer.name,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            key: const Key('sealed-language'),
            initialValue: _language,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Sprache'),
            items: [
              for (final entry in languageLabels.entries)
                DropdownMenuItem(value: entry.key, child: Text(entry.value)),
            ],
            onChanged: (value) => setState(() => _language = value ?? _language),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Expanded(child: Text('Anzahl')),
              IconButton(
                onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null,
                icon: const Icon(Icons.remove),
              ),
              Text('$_quantity', style: const TextStyle(fontSize: 18)),
              IconButton(
                key: const Key('sealed-more'),
                onPressed: () => setState(() => _quantity++),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            key: const Key('sealed-add'),
            onPressed: () => Navigator.of(context).pop((language: _language, quantity: _quantity)),
            icon: const Icon(Icons.add),
            label: const Text('Zur Sammlung hinzufügen'),
          ),
        ],
      ),
    ),
  );
}
