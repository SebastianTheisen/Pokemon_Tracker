// eBay-Verkäufe übernehmen: Vorschau der vom Lesezeichen ausgelesenen verkauften Angebote.
//
// Der Server schlägt die sicher passenden Verkäufe vor (Nummer im Titel, kein Konvolut,
// Euro, nicht zu alt); hier kann man ab- und zuwählen. Gruppiert wird nach ungegradet bzw.
// Grading-Firma und Note – gegradete Sammlungspositionen bekommen daraus ihren Wert.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../card/card_detail_screen.dart';
import 'cardmarket_import.dart';

class EbayImportScreen extends ConsumerStatefulWidget {
  const EbayImportScreen({required this.data, super.key});

  final String? data;

  @override
  ConsumerState<EbayImportScreen> createState() => _EbayImportScreenState();
}

class _EbayImportScreenState extends ConsumerState<EbayImportScreen> {
  late final BookmarkletPayload? _payload = BookmarkletPayload.decode(widget.data);
  String? _cardId;
  Future<EbaySoldResult>? _preview;
  Set<int>? _selected;
  bool _saving = false;
  bool _lookingUp = false;

  @override
  void initState() {
    super.initState();
    _cardId = _payload?.cardId;
    if (_payload != null && _cardId == null) {
      _lookingUp = true;
      _useRememberedCard();
    }
    _loadPreview();
  }

  /// Ohne Sprungmarke: die Karte nehmen, für die zuletzt „Preis holen“ geöffnet wurde.
  Future<void> _useRememberedCard() async {
    String? cardId;
    try {
      cardId = await ref.read(apiProvider).priceTarget();
    } on ApiException {
      cardId = null;
    }
    if (!mounted) return;
    setState(() {
      _lookingUp = false;
      _cardId = cardId;
      _loadPreview();
    });
  }

  void _loadPreview() {
    final payload = _payload;
    final cardId = _cardId;
    if (payload == null || cardId == null) return;
    _preview = ref
        .read(apiProvider)
        .ebaySold(cardId, pageUrl: payload.pageUrl, rows: payload.rows)
        .then((result) {
          _selected ??= {
            for (final sale in result.sales)
              if (sale.suggested) sale.index,
          };
          return result;
        });
  }

  Future<void> _save() async {
    final payload = _payload!;
    setState(() => _saving = true);
    final ok = await runAction(context, () async {
      await ref
          .read(apiProvider)
          .ebaySold(
            _cardId!,
            pageUrl: payload.pageUrl,
            rows: payload.rows,
            selected: _selected!.toList()..sort(),
            save: true,
          );
    });
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      ref.invalidate(pricesProvider(_cardId!));
      showMessage(context, 'eBay-Verkäufe gespeichert.');
      context.go('/card/$_cardId');
    }
  }

  @override
  Widget build(BuildContext context) {
    final payload = _payload;
    return Scaffold(
      appBar: AppBar(title: const Text('eBay-Verkäufe')),
      body: payload == null
          ? const EmptyView(
              icon: Icons.link_off,
              message: 'Keine gültigen Daten vom Lesezeichen erhalten.',
            )
          : _lookingUp
          ? const Center(child: CircularProgressIndicator())
          : _cardId == null
          ? CardPicker(
              onPicked: (id) => setState(() {
                _cardId = id;
                _loadPreview();
              }),
            )
          : FutureBuilder<EbaySoldResult>(
              future: _preview,
              builder: (context, snapshot) {
                if (snapshot.hasError) return ErrorView(message: '${snapshot.error}');
                final result = snapshot.data;
                if (result == null) return const Center(child: CircularProgressIndicator());
                return _buildPreview(result);
              },
            ),
    );
  }

  Widget _buildPreview(EbaySoldResult result) {
    final selected = _selected ?? {};
    final card = ref.watch(cardProvider(_cardId!)).value;
    final groups = <String, List<double>>{};
    for (final sale in result.sales) {
      final price = double.tryParse(sale.price ?? '');
      if (price != null && selected.contains(sale.index)) {
        groups.putIfAbsent(sale.group, () => []).add(price);
      }
    }
    final groupNames = groups.keys.toList()
      ..sort((a, b) => a == 'raw' ? -1 : (b == 'raw' ? 1 : a.compareTo(b)));
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        if (card != null) CardTile(card: card),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton(
            onPressed: () => setState(() {
              _cardId = null;
              _selected = null;
            }),
            child: const Text('Andere Karte wählen'),
          ),
        ),
        for (final warning in result.warnings)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
            child: Text(warning, style: const TextStyle(color: AppColors.warning)),
          ),
        const SectionTitle('Ergebnis'),
        if (groupNames.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text('Keine Verkäufe gewählt.', style: TextStyle(color: AppColors.textMuted)),
          ),
        for (final group in groupNames)
          Builder(
            builder: (context) {
              final stats = soldStats(groups[group]!);
              return ListTile(
                dense: true,
                title: Text(variantLabel(group)),
                subtitle: Text(
                  '${stats.count} Verkäufe · ${money(stats.low.toStringAsFixed(2))} – '
                  '${money(stats.high.toStringAsFixed(2))}',
                ),
                trailing: Text(
                  'Median ${money(stats.median.toStringAsFixed(2))}',
                  style: const TextStyle(fontSize: 16),
                ),
              );
            },
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: FilledButton.icon(
            onPressed: _saving || groupNames.isEmpty ? null : _save,
            icon: const Icon(Icons.save),
            label: const Text('Verkäufe speichern'),
          ),
        ),
        const SectionTitle('Verkäufe (passende sind vorausgewählt)'),
        for (final sale in result.sales)
          CheckboxListTile(
            key: Key('sale-${sale.index}'),
            dense: true,
            value: selected.contains(sale.index),
            onChanged: sale.price == null
                ? null
                : (value) => setState(
                    () => value == true ? selected.add(sale.index) : selected.remove(sale.index),
                  ),
            title: Text(sale.title, maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: Text(
              [
                if (sale.price != null) money(sale.price) else 'kein Euro-Preis',
                if (sale.soldOn != null) date(sale.soldOn),
                if (sale.group != 'raw') sale.group,
                ...sale.issues,
              ].join(' · '),
              style: TextStyle(
                color: sale.issues.isEmpty ? AppColors.textMuted : AppColors.warning,
              ),
            ),
          ),
      ],
    );
  }
}
