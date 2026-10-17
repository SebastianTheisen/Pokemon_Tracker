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

/// Bestätigt einen Treffer und bietet „Zur Sammlung“ an. Gibt `true` zurück, wenn gespeichert.
Future<bool> acceptCard(
  BuildContext context,
  WidgetRef ref,
  ScanResult result,
  CardInfo card, {
  required bool toCollection,
}) async {
  final api = ref.read(apiProvider);
  final confirmed = await runAction(context, () => api.confirmScan(result.scanId, card.id));
  if (!confirmed || !context.mounted) return false;
  if (!toCollection) {
    final ok = await runAction(context, () => api.addToWishlist(cardId: card.id));
    if (ok && context.mounted) {
      ref.invalidate(wishlistProvider);
      showMessage(context, '${card.name} steht auf der Merkliste.');
    }
    return ok;
  }
  final saved = await showItemSheet(context, card: card, grading: result.grading);
  if (saved == null || !context.mounted) return false;
  invalidateCollection(ref);
  showMessage(context, '${card.name} ist in der Sammlung.');
  return true;
}

/// Ergebnis eines Scans: Hinweis, gewählter Treffer, Alternativen, „Selbst suchen“.
class ScanResultView extends ConsumerStatefulWidget {
  const ScanResultView({required this.result, required this.onDone, super.key});

  final ScanResult result;
  final VoidCallback onDone;

  @override
  ConsumerState<ScanResultView> createState() => _ScanResultViewState();
}

class _ScanResultViewState extends ConsumerState<ScanResultView> {
  late CardInfo? _selected = widget.result.best?.card;
  ScanMatch? get _match =>
      widget.result.matches.where((m) => m.card.id == _selected?.id).firstOrNull;

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
    if (card != null) setState(() => _selected = card);
  }

  Future<void> _accept({required bool toCollection}) async {
    final card = _selected;
    if (card == null) return;
    if (await acceptCard(context, ref, widget.result, card, toCollection: toCollection)) {
      widget.onDone();
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    final selected = _selected;
    final match = _match;
    final banner = result.confident && selected?.id == result.best?.card.id
        ? (color: AppColors.gain, icon: Icons.check_circle, text: result.hint)
        : (
            color: AppColors.warning,
            icon: Icons.help_outline,
            text: selected == null ? result.hint : 'Bitte prüfen – stimmt die Karte?',
          );
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        Container(
          margin: const EdgeInsets.all(16),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: banner.color.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              Icon(banner.icon, color: banner.color),
              const SizedBox(width: 8),
              Expanded(child: Text(banner.text, key: const Key('scan-hint'))),
            ],
          ),
        ),
        if (result.grading case final grading?)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Row(
              children: [
                const Icon(Icons.verified, color: AppColors.accent),
                const SizedBox(width: 8),
                Text('Slab erkannt: ${grading.company} ${grading.grade ?? ''}'.trim()),
              ],
            ),
          ),
        if (selected != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CardImage(url: selected.image(high: true), width: 110),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            selected.name,
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(fontWeight: FontWeight.bold),
                          ),
                          Text(
                            selected.subtitle,
                            style: const TextStyle(color: AppColors.textMuted),
                          ),
                          const SizedBox(height: 4),
                          Tag(languageLabels[selected.language] ?? selected.language),
                          if (match != null) ...[
                            const SizedBox(height: 8),
                            Text(
                              'Sicherheit: ${percent(match.confidence)}',
                              style: const TextStyle(fontSize: 12),
                            ),
                            for (final reason in match.reasons)
                              Text(
                                '• $reason',
                                style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                              ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        const SizedBox(height: 12),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              FilledButton.icon(
                key: const Key('scan-add'),
                onPressed: selected == null ? null : () => _accept(toCollection: true),
                icon: const Icon(Icons.add),
                label: const Text('Zur Sammlung hinzufügen'),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: selected == null ? null : () => _accept(toCollection: false),
                      icon: const Icon(Icons.favorite_border),
                      label: const Text('Merkliste'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      key: const Key('scan-search'),
                      onPressed: _searchMyself,
                      icon: const Icon(Icons.search),
                      label: const Text('Selbst suchen'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        if (result.matches.length > 1) ...[
          const SectionTitle('Andere Möglichkeiten'),
          for (final other in result.matches)
            if (other.card.id != selected?.id)
              CardTile(
                card: other.card,
                trailing: Text(percent(other.confidence)),
                onTap: () => setState(() => _selected = other.card),
              ),
        ],
      ],
    );
  }
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
    padding: const EdgeInsets.all(16),
    children: [
      Container(
        height: 260,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.primary, width: 2),
          color: AppColors.surface,
        ),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.style, size: 64, color: AppColors.textMuted),
            SizedBox(height: 12),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                'Karte formatfüllend fotografieren – Name und Nummer sollten lesbar sein. '
                'Slabs, Toploader und Sleeves funktionieren auch.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textMuted),
              ),
            ),
          ],
        ),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(error!, style: const TextStyle(color: AppColors.loss)),
        ),
      const SizedBox(height: 16),
      FilledButton.icon(
        key: const Key('scan-camera'),
        onPressed: onCamera,
        icon: const Icon(Icons.photo_camera),
        label: const Text('Foto aufnehmen'),
      ),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        key: const Key('scan-gallery'),
        onPressed: onGallery,
        icon: const Icon(Icons.photo_library),
        label: const Text('Aus der Galerie'),
      ),
      const SizedBox(height: 16),
      DropdownButtonFormField<String?>(
        isExpanded: true,
        initialValue: language,
        decoration: const InputDecoration(labelText: 'Sprache der Karte'),
        items: [
          const DropdownMenuItem(child: Text('Automatisch erkennen')),
          for (final entry in languageLabels.entries)
            DropdownMenuItem(value: entry.key, child: Text(entry.value)),
        ],
        onChanged: onLanguage,
      ),
      const SizedBox(height: 24),
      Row(
        children: [
          Expanded(
            child: TextButton.icon(
              onPressed: () => context.push('/scan/batch'),
              icon: const Icon(Icons.burst_mode),
              label: const Text('Stapel-Scan'),
            ),
          ),
          Expanded(
            child: TextButton.icon(
              onPressed: () => context.push('/scan/binder'),
              icon: const Icon(Icons.grid_view),
              label: const Text('Binder (Beta)'),
            ),
          ),
        ],
      ),
      TextButton.icon(
        onPressed: () => context.go('/search'),
        icon: const Icon(Icons.edit_note),
        label: const Text('Manuell hinzufügen (Suche)'),
      ),
    ],
  );
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
