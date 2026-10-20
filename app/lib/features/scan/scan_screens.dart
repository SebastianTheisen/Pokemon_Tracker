// Scanner: Einzelkarte (Kamera/Galerie), Stapel und Binderseite (Beta).
//
// Ablauf: Foto → Backend erkennt die Karte → Ergebnis mit Alternativen anzeigen →
// Nutzer bestätigt oder wählt selbst → Bestätigung ans Backend (wird sein eigenes
// Referenzbild) → optional direkt zur Sammlung oder Merkliste.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../collection/item_sheet.dart';
import '../dashboard/dashboard_screen.dart';
import '../card/card_detail_screen.dart';
import '../search/search_screen.dart';
import '../wishlist/wishlist_screen.dart';

/// Bildquelle, in Tests ersetzbar.
abstract interface class ScanImageSource {
  Future<UploadImage?> pick({required bool camera, double maxSide});
  Future<List<UploadImage>> pickMany({double maxSide});
}

class PickerImageSource implements ScanImageSource {
  final _picker = ImagePicker();

  static Future<UploadImage> _read(XFile file) async =>
      UploadImage(bytes: await file.readAsBytes(), filename: file.name);

  @override
  Future<UploadImage?> pick({required bool camera, double maxSide = 2000}) async {
    final file = await _picker.pickImage(
      source: camera ? ImageSource.camera : ImageSource.gallery,
      maxWidth: maxSide,
      maxHeight: maxSide,
      imageQuality: 88,
    );
    return file == null ? null : _read(file);
  }

  @override
  Future<List<UploadImage>> pickMany({double maxSide = 2000}) async {
    final files = await _picker.pickMultiImage(
      maxWidth: maxSide,
      maxHeight: maxSide,
      imageQuality: 88,
    );
    return [for (final file in files) await _read(file)];
  }
}

final imageSourceProvider = Provider<ScanImageSource>((ref) => PickerImageSource());

/// Bestätigt den Treffer (wird eigenes Referenzbild) und setzt die Karte auf die Merkliste.
Future<bool> addScanToWishlist(
  BuildContext context,
  WidgetRef ref,
  ScanResult result,
  CardInfo card,
) async {
  final api = ref.read(apiProvider);
  final ok = await runAction(context, () async {
    await api.confirmScan(result.scanId, card.id);
    await api.addToWishlist(cardId: card.id);
  });
  if (ok && context.mounted) {
    ref.invalidate(wishlistProvider);
    showMessage(context, '${card.displayName} steht auf der Merkliste.');
  }
  return ok;
}

/// Ergebnis eines Scans: großes Kartenbild, Preis, ein Knopf „Hinzufügen“.
/// Alternativen, Suche und Begründungen nur auf Wunsch.
class ScanResultView extends ConsumerStatefulWidget {
  const ScanResultView({required this.result, required this.onDone, super.key});

  final ScanResult result;

  /// „Nächste Karte“ – zurück zum Scannen bzw. Liste schließen.
  final VoidCallback onDone;

  @override
  ConsumerState<ScanResultView> createState() => _ScanResultViewState();
}

class _ScanResultViewState extends ConsumerState<ScanResultView> {
  late CardInfo? _selected = widget.result.best?.card;
  late bool _showAlternatives = widget.result.best == null;
  CollectionItem? _added;
  bool _busy = false;

  ScanMatch? get _match =>
      widget.result.matches.where((m) => m.card.id == _selected?.id).firstOrNull;

  bool get _isConfirmedBest =>
      widget.result.confident && _selected?.id == widget.result.best?.card.id;

  void _select(CardInfo card) => setState(() {
    _selected = card;
    _showAlternatives = false;
  });

  Future<void> _searchMyself() async {
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
    if (card != null) _select(card);
  }

  /// Ein Tipp: bestätigen + mit Standardwerten hinzufügen (NM, 1×; Slab mit Note).
  Future<void> _quickAdd() async {
    final card = _selected;
    if (card == null) return;
    final grading = widget.result.grading;
    setState(() => _busy = true);
    final api = ref.read(apiProvider);
    CollectionItem? item;
    final ok = await runAction(context, () async {
      await api.confirmScan(widget.result.scanId, card.id);
      item = await api.addItem({
        'card_id': card.id,
        'quantity': 1,
        if (grading == null) 'condition': 'NM',
        if (grading != null)
          'grading_company': gradingCompanies.contains(grading.company) ? grading.company : 'OTHER',
        if (grading?.grade != null) 'grade': grading!.grade,
      });
    });
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (ok) _added = item;
    });
    if (ok) invalidateCollection(ref);
  }

  /// Nicht als Slab erkannt, ist aber einer: Formular mit Slab-Auswahl (Firma, Note, Black
  /// Label) öffnen; beim Speichern wird der Scan wie beim schnellen Hinzufügen bestätigt.
  Future<void> _addAsSlab() async {
    final card = _selected;
    if (card == null) return;
    final saved = await showItemSheet(
      context,
      card: card,
      grading: widget.result.grading ?? const Grading(company: 'PSA', grade: '10'),
    );
    if (saved == null || !mounted) return;
    await runAction(
      context,
      () => ref.read(apiProvider).confirmScan(widget.result.scanId, card.id),
    );
    if (!mounted) return;
    setState(() => _added = saved);
    invalidateCollection(ref);
  }

  Future<void> _editAdded() async {
    final item = _added;
    if (item == null) return;
    final saved = await showItemSheet(context, item: item);
    if (saved != null && mounted) {
      setState(() => _added = saved);
      invalidateCollection(ref);
    }
  }

  Future<void> _undo() async {
    final item = _added;
    if (item == null) return;
    if (await runAction(context, () => ref.read(apiProvider).deleteItem(item.id))) {
      invalidateCollection(ref);
      if (mounted) setState(() => _added = null);
    }
  }

  void _showReasons() {
    final match = _match;
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Warum diese Karte?'),
        content: Text(
          match == null
              ? 'Selbst ausgewählt.'
              : [
                  'Sicherheit: ${percent(match.confidence)}',
                  ...match.reasons.map((reason) => '• $reason'),
                ].join('\n'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('OK')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    final added = _added;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        if (selected == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Text(
              'Keine Karte erkannt.\nWähle unten eine Möglichkeit oder suche selbst.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16),
            ),
          )
        else ...[
          Center(child: CardImage(url: selected.image(high: true), width: 190)),
          const SizedBox(height: 16),
          Center(
            child: added != null
                ? const _StatusChip(Icons.check_circle, 'Hinzugefügt', AppColors.gain)
                : _isConfirmedBest
                ? const _StatusChip(Icons.verified, 'Erkannt', AppColors.gain)
                : const _StatusChip(Icons.help_outline, 'Bitte prüfen', AppColors.warning),
          ),
          const SizedBox(height: 10),
          Text(
            selected.displayName,
            key: const Key('scan-card-name'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
          ),
          Text(
            [?selected.originalName, selected.subtitle, languageTag(selected.language)].join(' · '),
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.textMuted),
          ),
          if (widget.result.grading case final grading?)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Slab: ${grading.company} ${grading.grade ?? ''}'.trim(),
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.accent, fontWeight: FontWeight.w600),
              ),
            ),
          const SizedBox(height: 12),
          _ScanPrice(card: selected, grading: widget.result.grading),
          const SizedBox(height: 20),
          if (added == null) ...[
            FilledButton.icon(
              key: const Key('scan-add'),
              onPressed: _busy ? null : _quickAdd,
              icon: const Icon(Icons.add),
              label: Text(widget.result.grading == null ? 'Hinzufügen' : 'Als Slab hinzufügen'),
            ),
            const SizedBox(height: 4),
            Wrap(
              alignment: WrapAlignment.center,
              children: [
                TextButton(
                  key: const Key('scan-slab'),
                  onPressed: _busy ? null : _addAsSlab,
                  child: Text(widget.result.grading == null ? 'Ist ein Slab?' : 'Slab anpassen'),
                ),
                TextButton(
                  key: const Key('scan-other'),
                  onPressed: () => setState(() => _showAlternatives = !_showAlternatives),
                  child: const Text('Andere Karte?'),
                ),
                TextButton(
                  onPressed: () => addScanToWishlist(context, ref, widget.result, selected),
                  child: const Text('Merkliste'),
                ),
                TextButton(onPressed: _showReasons, child: const Text('Warum?')),
              ],
            ),
          ] else ...[
            FilledButton.icon(
              key: const Key('scan-next'),
              onPressed: widget.onDone,
              icon: const Icon(Icons.photo_camera),
              label: const Text('Nächste Karte'),
            ),
            const SizedBox(height: 4),
            Wrap(
              alignment: WrapAlignment.center,
              children: [
                TextButton(onPressed: _editAdded, child: const Text('Zustand/Preis ändern')),
                TextButton(onPressed: _undo, child: const Text('Rückgängig')),
              ],
            ),
          ],
        ],
        if (_showAlternatives && added == null) ...[
          const SizedBox(height: 12),
          const Text(
            'Andere Möglichkeiten',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final match in widget.result.matches)
                if (match.card.id != selected?.id)
                  _AlternativeThumb(match: match, onTap: () => _select(match.card)),
            ],
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            key: const Key('scan-search'),
            onPressed: _searchMyself,
            icon: const Icon(Icons.search),
            label: const Text('Selbst suchen'),
          ),
        ],
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip(this.icon, this.label, this.color);

  final IconData icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.15),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(width: 6),
        Text(
          label,
          key: const Key('scan-status'),
          style: TextStyle(color: color, fontWeight: FontWeight.w600),
        ),
      ],
    ),
  );
}

/// Preis im Scan-Ergebnis: Rohkarte → Near-Mint-Preis (belegt oder geschätzt); Slab → Median
/// gespeicherter eBay-Verkäufe gleicher Firma und Note (sonst Knopf zu diesen Verkäufen).
class _ScanPrice extends ConsumerWidget {
  const _ScanPrice({required this.card, this.grading});

  final CardInfo card;
  final Grading? grading;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prices = ref.watch(pricesProvider(card.id));
    return prices.when(
      loading: () => const Center(
        child: SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)),
      ),
      error: (_, _) => const SizedBox.shrink(),
      data: (data) => grading == null ? _raw(context, data) : _graded(context, data, grading!),
    );
  }

  Widget _raw(BuildContext context, CardPrices data) {
    final nm = data.conditions
        .where((c) => c.condition == 'NM' && c.variant == 'normal')
        .firstOrNull;
    final cardmarket = cardmarketOffersUrl(
      productUrl: data.offers.where((o) => o.source == 'cardmarket').firstOrNull?.url,
      cardId: card.id,
      language: card.language,
    );
    return Column(
      children: [
        if (nm == null)
          const Text(
            'Noch kein belegter Preis',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted),
          )
        else
          _PriceLine(
            value: money(nm.value, currency: nm.currency),
            label: nm.isEstimate ? 'Near Mint · geschätzt' : 'Near Mint · mit Beleg',
          ),
        const SizedBox(height: 6),
        _FetchPrices(
          buttons: [
            if (cardmarket != null)
              (
                key: const Key('scan-cardmarket'),
                label: 'Cardmarket ${languageTag(card.language)} ab NM',
                url: cardmarket,
              ),
            (
              key: const Key('scan-ebay'),
              label: 'eBay verkauft',
              url: ebaySoldSearch(card).toString(),
            ),
          ],
        ),
      ],
    );
  }

  Widget _graded(BuildContext context, CardPrices data, Grading grading) {
    final label = '${grading.company} ${grading.grade ?? ''}'.trim();
    final sold = data.offers
        .where(
          (o) =>
              o.source == 'ebay_sold' && o.variant == gradedVariant(grading.company, grading.grade),
        )
        .firstOrNull;
    final median = sold?.metrics['median'];
    if (sold != null && median != null) {
      final count = double.tryParse(sold.metrics['count'] ?? '')?.round();
      return Column(
        children: [
          _PriceLine(
            value: money(median, currency: sold.currency),
            label: '$label · Median aus ${count ?? '?'} eBay-Verkäufen · ${date(sold.updatedAt)}',
          ),
          const SizedBox(height: 6),
          _FetchPrices(
            buttons: [
              (
                key: const Key('scan-graded-ebay'),
                label: '$label-Verkäufe neu holen',
                url: ebaySoldSearch(card, grading: label).toString(),
              ),
            ],
          ),
        ],
      );
    }
    return Column(
      children: [
        Text(
          'Noch kein $label-Preis – der Rohkarten-Preis passt für Slabs nicht.',
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.textMuted),
        ),
        const SizedBox(height: 6),
        OutlinedButton.icon(
          key: const Key('scan-graded-ebay'),
          onPressed: () => openLink(context, ebaySoldSearch(card, grading: label).toString()),
          icon: const Icon(Icons.open_in_new, size: 18),
          label: Text('Verkaufte $label bei eBay'),
        ),
        const Text(
          'Dort das Lesezeichen „An Kartenkiste senden“ antippen – dann steht der Preis hier.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.textMuted, fontSize: 12),
        ),
      ],
    );
  }
}

/// Knöpfe „Preis holen“: öffnen die passende Seite (Sprache, Zustand bzw. Note sind schon
/// gesetzt); dort überträgt das Lesezeichen „An Kartenkiste senden“ die Preise.
class _FetchPrices extends StatelessWidget {
  const _FetchPrices({required this.buttons});

  final List<({Key key, String label, String url})> buttons;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Wrap(
        alignment: WrapAlignment.center,
        spacing: 8,
        runSpacing: 4,
        children: [
          for (final button in buttons)
            OutlinedButton.icon(
              key: button.key,
              onPressed: () => openLink(context, button.url),
              icon: const Icon(Icons.open_in_new, size: 18),
              label: Text(button.label),
            ),
        ],
      ),
      const Text(
        'Dort das Lesezeichen „An Kartenkiste senden“ antippen.',
        textAlign: TextAlign.center,
        style: TextStyle(color: AppColors.textMuted, fontSize: 12),
      ),
    ],
  );
}

class _PriceLine extends StatelessWidget {
  const _PriceLine({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Text(
        value,
        key: const Key('scan-price'),
        style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
      ),
      Text(
        label,
        textAlign: TextAlign.center,
        style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
      ),
    ],
  );
}

class _AlternativeThumb extends StatelessWidget {
  const _AlternativeThumb({required this.match, required this.onTap});

  final ScanMatch match;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(8),
    child: SizedBox(
      width: 96,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CardImage(url: match.card.image(), width: 96),
          const SizedBox(height: 4),
          Text(match.card.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
          Text(
            '${match.card.number} · ${languageTag(match.card.language)}',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 11),
          ),
        ],
      ),
    ),
  );
}

class ScanScreen extends ConsumerStatefulWidget {
  const ScanScreen({super.key});

  @override
  ConsumerState<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends ConsumerState<ScanScreen> {
  UploadImage? _image;
  ScanResult? _result;
  String? _error;
  bool _busy = false;
  String? _language;

  Future<void> _scan({required bool camera}) async {
    final image = await ref.read(imageSourceProvider).pick(camera: camera);
    if (image == null) return;
    setState(() {
      _image = image;
      _result = null;
      _error = null;
      _busy = true;
    });
    try {
      final result = await ref.read(apiProvider).scan(image, language: _language);
      if (mounted) setState(() => _result = result);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _reset() => setState(() {
    _image = null;
    _result = null;
    _error = null;
  });

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Karte scannen'),
        actions: [
          if (_image != null)
            IconButton(tooltip: 'Neuer Scan', onPressed: _reset, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _busy
          ? _Busy(image: _image)
          : result != null
          ? ScanResultView(result: result, onDone: _reset)
          : _StartView(
              error: _error,
              language: _language,
              onLanguage: (value) => setState(() => _language = value),
              onCamera: () => _scan(camera: true),
              onGallery: () => _scan(camera: false),
            ),
    );
  }
}

class _Busy extends StatelessWidget {
  const _Busy({this.image, this.label = 'Erkenne Karte …'});

  final UploadImage? image;
  final String label;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (image != null)
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Image.memory(image!.bytes, height: 260, fit: BoxFit.contain),
          ),
        const SizedBox(height: 24),
        const CircularProgressIndicator(),
        const SizedBox(height: 12),
        Text(label),
      ],
    ),
  );
}

class _StartView extends StatelessWidget {
  const _StartView({
    required this.onCamera,
    required this.onGallery,
    required this.onLanguage,
    this.language,
    this.error,
  });

  final VoidCallback onCamera;
  final VoidCallback onGallery;
  final ValueChanged<String?> onLanguage;
  final String? language;
  final String? error;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(24),
    children: [
      const SizedBox(height: 12),
      Center(
        child: Container(
          width: 200,
          height: 280,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: AppColors.primary, width: 3),
          ),
          child: const Icon(Icons.style, size: 72, color: AppColors.textMuted),
        ),
      ),
      const SizedBox(height: 20),
      const Text(
        'Karte ganz ins Bild – Name und Nummer sollten lesbar sein.',
        textAlign: TextAlign.center,
        style: TextStyle(color: AppColors.textMuted),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(
            error!,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.loss),
          ),
        ),
      const SizedBox(height: 24),
      SizedBox(
        height: 60,
        child: FilledButton.icon(
          key: const Key('scan-camera'),
          onPressed: onCamera,
          icon: const Icon(Icons.photo_camera, size: 26),
          label: const Text('Foto aufnehmen', style: TextStyle(fontSize: 17)),
        ),
      ),
      const SizedBox(height: 8),
      TextButton.icon(
        key: const Key('scan-gallery'),
        onPressed: onGallery,
        icon: const Icon(Icons.photo_library),
        label: const Text('Aus der Galerie wählen'),
      ),
      const SizedBox(height: 24),
      Wrap(
        alignment: WrapAlignment.center,
        spacing: 8,
        children: [
          ActionChip(
            avatar: const Icon(Icons.burst_mode, size: 18),
            label: const Text('Mehrere Karten'),
            onPressed: () => context.push('/scan/batch'),
          ),
          ActionChip(
            avatar: const Icon(Icons.grid_view, size: 18),
            label: const Text('Binderseite (Beta)'),
            onPressed: () => context.push('/scan/binder'),
          ),
          ActionChip(
            avatar: const Icon(Icons.translate, size: 18),
            label: Text(
              language == null ? 'Sprache: automatisch' : 'Sprache: ${languageTag(language!)}',
            ),
            onPressed: () => _pickLanguage(context),
          ),
        ],
      ),
    ],
  );

  Future<void> _pickLanguage(BuildContext context) async {
    final choice = await showModalBottomSheet<String>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              title: const Text('Automatisch erkennen'),
              onTap: () => Navigator.of(sheetContext).pop('auto'),
            ),
            for (final entry in languageLabels.entries)
              ListTile(
                title: Text(entry.value),
                onTap: () => Navigator.of(sheetContext).pop(entry.key),
              ),
          ],
        ),
      ),
    );
    if (choice != null) onLanguage(choice == 'auto' ? null : choice);
  }
}

/// Zeile einer Ergebnisliste (Stapel/Binder); Tippen öffnet das Ergebnis.
class _ResultTile extends ConsumerWidget {
  const _ResultTile({
    required this.title,
    required this.result,
    required this.done,
    required this.onDone,
    this.error,
  });

  final String title;
  final ScanResult? result;
  final String? error;
  final bool done;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final best = result?.best;
    return ListTile(
      leading: CardImage(url: best?.card.image(), width: 40),
      title: Text(best?.card.name ?? error ?? 'Nicht erkannt'),
      subtitle: Text(
        best == null ? title : '$title · ${best.card.subtitle}',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(color: AppColors.textMuted),
      ),
      trailing: done
          ? const Icon(Icons.check_circle, color: AppColors.gain)
          : result == null
          ? null
          : Tag(
              result!.confident ? 'sicher' : 'prüfen',
              color: result!.confident ? AppColors.gain : AppColors.warning,
            ),
      onTap: result == null || done
          ? null
          : () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              useSafeArea: true,
              builder: (sheetContext) => SizedBox(
                height: MediaQuery.sizeOf(sheetContext).height * 0.9,
                child: ScanResultView(
                  result: result!,
                  onDone: () {
                    Navigator.of(sheetContext).pop();
                    onDone();
                  },
                ),
              ),
            ),
    );
  }
}

class BatchScanScreen extends ConsumerStatefulWidget {
  const BatchScanScreen({super.key});

  @override
  ConsumerState<BatchScanScreen> createState() => _BatchScanScreenState();
}

class _BatchScanScreenState extends ConsumerState<BatchScanScreen> {
  List<BatchItem>? _items;
  final _done = <int>{};
  bool _busy = false;

  Future<void> _pick() async {
    final images = await ref.read(imageSourceProvider).pickMany();
    if (images.isEmpty) return;
    setState(() {
      _busy = true;
      _items = null;
      _done.clear();
    });
    try {
      final items = await ref.read(apiProvider).scanBatch(images);
      if (mounted) setState(() => _items = items);
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: const Text('Stapel-Scan')),
      body: _busy
          ? const _Busy(label: 'Erkenne Karten …')
          : items == null
          ? EmptyView(
              icon: Icons.burst_mode,
              message:
                  'Mehrere Fotos auswählen (je eine Karte, bis zu 20). '
                  'Danach jedes Ergebnis bestätigen oder korrigieren.',
              action: FilledButton.icon(
                onPressed: _pick,
                icon: const Icon(Icons.photo_library),
                label: const Text('Fotos auswählen'),
              ),
            )
          : ListView.separated(
              itemCount: items.length,
              separatorBuilder: (_, _) => const Divider(indent: 72),
              itemBuilder: (context, index) => _ResultTile(
                title: items[index].filename,
                result: items[index].result,
                error: items[index].error,
                done: _done.contains(index),
                onDone: () => setState(() => _done.add(index)),
              ),
            ),
      floatingActionButton: items == null
          ? null
          : FloatingActionButton.extended(
              onPressed: _pick,
              icon: const Icon(Icons.add_photo_alternate),
              label: const Text('Neuer Stapel'),
            ),
    );
  }
}

class BinderScanScreen extends ConsumerStatefulWidget {
  const BinderScanScreen({super.key});

  @override
  ConsumerState<BinderScanScreen> createState() => _BinderScanScreenState();
}

class _BinderScanScreenState extends ConsumerState<BinderScanScreen> {
  static const _layouts = {
    'auto': 'Automatisch',
    '3x3': '9er-Seite (3×3)',
    '4x3': '12er-Seite (4×3)',
    '2x2': '4er-Seite (2×2)',
  };

  String _layout = 'auto';
  BinderResult? _result;
  final _done = <int>{};
  bool _busy = false;

  Future<void> _scan({required bool camera}) async {
    final image = await ref.read(imageSourceProvider).pick(camera: camera, maxSide: 3000);
    if (image == null) return;
    setState(() {
      _busy = true;
      _result = null;
      _done.clear();
    });
    try {
      final result = await ref.read(apiProvider).scanBinder(image, layout: _layout);
      if (mounted) setState(() => _result = result);
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Scaffold(
      appBar: AppBar(title: const Text('Binder-Scan (Beta)')),
      body: _busy
          ? const _Busy(label: 'Erkenne Binderseite – das dauert etwas …')
          : ListView(
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text(
                        'Eine ganze Binderseite fotografieren, gerade von oben und ohne '
                        'Spiegelungen. Beta: Die Erkennung schwankt noch – bitte jede Karte prüfen.',
                        style: TextStyle(color: AppColors.textMuted),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _layout,
                        decoration: const InputDecoration(labelText: 'Seitenformat'),
                        items: [
                          for (final entry in _layouts.entries)
                            DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                        ],
                        onChanged: (value) => setState(() => _layout = value ?? 'auto'),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: () => _scan(camera: true),
                              icon: const Icon(Icons.photo_camera),
                              label: const Text('Foto'),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () => _scan(camera: false),
                              icon: const Icon(Icons.photo_library),
                              label: const Text('Galerie'),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                if (result != null) ...[
                  SectionTitle(
                    '${result.cells.length} Felder '
                    '(${result.method == 'konturen' ? 'Karten erkannt' : 'Raster ${result.method}'})',
                  ),
                  for (final (index, cell) in result.cells.indexed)
                    _ResultTile(
                      title: 'Reihe ${cell.row + 1}, Platz ${cell.column + 1}',
                      result: cell.result,
                      done: _done.contains(index),
                      onDone: () => setState(() => _done.add(index)),
                    ),
                ],
              ],
            ),
    );
  }
}
