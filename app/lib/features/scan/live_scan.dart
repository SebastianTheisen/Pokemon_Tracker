// Live-Scanner (wie Collectr/TCGplayer): Kamera läuft, Karte hinhalten – die App erkennt sie
// selbst, vibriert und sammelt sie in einer Liste. Am Ende prüfen und alle auf einmal hinzufügen.
//
// Damit nicht dauernd Bilder zum Server gehen, wird nur ausgelöst, wenn das Bild ruhig ist
// UND sich seit dem letzten Foto deutlich verändert hat (also eine neue Karte daliegt).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/camera/live_camera.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../collection/item_sheet.dart';
import '../collection/owned.dart';
import '../dashboard/dashboard_screen.dart';

/// Ruhig: mittlere Grauwert-Änderung zwischen zwei Messungen (0–255) darunter.
const stillThreshold = 6.0;

/// Neue Szene: Abstand zum letzten Foto darüber.
const changeThreshold = 14.0;

/// So viele ruhige Messungen hintereinander, bevor ausgelöst wird.
const stillSamples = 2;

const _tick = Duration(milliseconds: 300);

/// Eine erkannte Karte der laufenden Sitzung.
class LiveHit {
  LiveHit({required this.scan, required this.match}) : selected = true;

  final ScanResult scan;
  final ScanMatch match;
  bool selected;

  CardInfo get card => match.card;
}

enum _Phase { starting, waiting, recognizing, denied, unsupported }

class LiveScanScreen extends ConsumerStatefulWidget {
  const LiveScanScreen({super.key});

  @override
  ConsumerState<LiveScanScreen> createState() => _LiveScanScreenState();
}

class _LiveScanScreenState extends ConsumerState<LiveScanScreen> {
  late final LiveCamera _camera = ref.read(liveCameraProvider);
  final List<LiveHit> _hits = [];
  _Phase _phase = _Phase.starting;
  Timer? _timer;
  int _still = 0;
  bool _busy = false;

  /// Unsicherer Treffer: bester Tipp zum Bestätigen („Ist es Glurak ex?“).
  LiveHit? _guess;

  /// Kurze Meldung unten im Bild („✓ Glurak ex“, „Nicht sicher …“).
  String? _flash;
  bool _flashGood = true;
  Timer? _flashTimer;

  @override
  void initState() {
    super.initState();
    unawaited(_start());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _flashTimer?.cancel();
    _camera.stop();
    super.dispose();
  }

  Future<void> _start() async {
    final result = await _camera.start();
    if (!mounted) return;
    setState(
      () => _phase = switch (result) {
        CameraStart.ok => _Phase.waiting,
        CameraStart.denied => _Phase.denied,
        CameraStart.unsupported => _Phase.unsupported,
      },
    );
    if (result == CameraStart.ok) _timer = Timer.periodic(_tick, (_) => _check());
  }

  void _check() {
    if (_busy || !mounted) return;
    final (:motion, :change) = _camera.measure();
    _still = motion < stillThreshold ? _still + 1 : 0;
    if (_still >= stillSamples && change > changeThreshold) unawaited(_recognize());
  }

  Future<void> _recognize() async {
    _busy = true;
    _still = 0;
    setState(() => _phase = _Phase.recognizing);
    try {
      final bytes = await _camera.frame();
      if (bytes == null || !mounted) return;
      final result = await ref
          .read(apiProvider)
          .scan(UploadImage(bytes: bytes, filename: 'live.jpg'));
      if (!mounted) return;
      final best = result.best;
      if (result.confident && best != null) {
        _take(LiveHit(scan: result, match: best));
      } else if (best != null) {
        // Wie bei Collectr: bester Tipp zum Bestätigen statt nur „nicht sicher“.
        setState(() => _guess = LiveHit(scan: result, match: best));
      } else {
        _show('Nicht erkannt – Karte ruhig und ganz ins Bild halten', good: false);
      }
    } on ApiException catch (error) {
      _show(error.message, good: false);
    } finally {
      _busy = false;
      if (mounted) setState(() => _phase = _Phase.waiting);
    }
  }

  /// Treffer übernehmen (doppelt hintereinander zählt nur einmal).
  void _take(LiveHit hit) {
    final duplicate = _hits.isNotEmpty && _hits.last.card.id == hit.card.id;
    setState(() {
      _guess = null;
      if (!duplicate) _hits.add(hit);
    });
    if (!duplicate) unawaited(HapticFeedback.heavyImpact());
    _show('✓ ${hit.card.displayName}${duplicate ? ' (schon erfasst)' : ''}', good: true);
  }

  void _show(String text, {required bool good}) {
    if (!mounted) return;
    _flashTimer?.cancel();
    setState(() {
      _flash = text;
      _flashGood = good;
    });
    _flashTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) setState(() => _flash = null);
    });
  }

  Future<void> _finish() async {
    _timer?.cancel();
    final added = await showModalBottomSheet<int>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _ReviewSheet(hits: _hits),
    );
    if (!mounted) return;
    if (added != null && added > 0) {
      invalidateCollection(ref);
      showMessage(context, '$added ${added == 1 ? 'Karte' : 'Karten'} hinzugefügt');
      context.pop();
      return;
    }
    setState(() {}); // Auswahl kann sich geändert haben
    _timer = Timer.periodic(_tick, (_) => _check());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.black,
    appBar: AppBar(
      backgroundColor: Colors.black,
      foregroundColor: Colors.white,
      title: const Text('Live-Scanner'),
    ),
    body: switch (_phase) {
      _Phase.denied || _Phase.unsupported => _Unavailable(denied: _phase == _Phase.denied),
      _ => Stack(
        fit: StackFit.expand,
        children: [
          _camera.preview(),
          const IgnorePointer(child: CustomPaint(painter: _FramePainter())),
          Positioned(
            left: 16,
            right: 16,
            top: 16,
            child: _StatusPill(
              text: switch (_phase) {
                _Phase.starting => 'Kamera startet …',
                _Phase.recognizing => 'Erkenne …',
                _ => 'Karte in den Rahmen legen – ruhig halten',
              },
              busy: _phase != _Phase.waiting,
            ),
          ),
          if (_guess case final guess?)
            Positioned(
              left: 16,
              right: 16,
              bottom: 112,
              child: _GuessCard(
                hit: guess,
                onTake: () => _take(guess),
                onDismiss: () => setState(() => _guess = null),
              ),
            )
          else if (_flash case final text?)
            Positioned(
              left: 16,
              right: 16,
              bottom: 120,
              child: _Flash(text: text, good: _flashGood),
            ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _Tray(hits: _hits, onDone: _finish),
          ),
        ],
      ),
    },
  );
}

/// Kartenrahmen als Hilfe (Kartenformat 63 × 88), Rest abgedunkelt.
class _FramePainter extends CustomPainter {
  const _FramePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final width = size.width * 0.72;
    final height = width * 88 / 63;
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height * 0.45),
      width: width,
      height: height,
    );
    final card = RRect.fromRectAndRadius(rect, const Radius.circular(16));
    canvas
      ..drawPath(
        Path.combine(
          PathOperation.difference,
          Path()..addRect(Offset.zero & size),
          Path()..addRRect(card),
        ),
        Paint()..color = Colors.black.withValues(alpha: 0.45),
      )
      ..drawRRect(
        card,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3,
      );
  }

  @override
  bool shouldRepaint(_FramePainter oldDelegate) => false;
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.text, required this.busy});

  final String text;
  final bool busy;

  @override
  Widget build(BuildContext context) => Center(
    child: Container(
      key: const Key('live-status'),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (busy) ...[
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Text(text, style: const TextStyle(color: Colors.white)),
          ),
        ],
      ),
    ),
  );
}

class _Flash extends StatelessWidget {
  const _Flash({required this.text, required this.good});

  final String text;
  final bool good;

  @override
  Widget build(BuildContext context) => Center(
    child: Container(
      key: const Key('live-flash'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: good ? AppColors.gain : AppColors.warning,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
      ),
    ),
  );
}

/// Unsicherer Treffer: Bild, Name und „Übernehmen“ – oder weg damit.
class _GuessCard extends StatelessWidget {
  const _GuessCard({required this.hit, required this.onTake, required this.onDismiss});

  final LiveHit hit;
  final VoidCallback onTake;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) => Material(
    key: const Key('live-guess'),
    color: Theme.of(context).colorScheme.surface,
    borderRadius: BorderRadius.circular(16),
    child: Padding(
      padding: const EdgeInsets.all(10),
      child: Row(
        children: [
          CardImage(url: hit.card.image(), width: 42),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Ist es ${hit.card.displayName}?',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                Text(
                  '${hit.card.subtitle} · nicht ganz sicher',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ],
            ),
          ),
          IconButton(
            key: const Key('live-guess-no'),
            tooltip: 'Nein',
            onPressed: onDismiss,
            icon: const Icon(Icons.close),
          ),
          FilledButton(
            key: const Key('live-guess-yes'),
            onPressed: onTake,
            child: const Text('Ja'),
          ),
        ],
      ),
    ),
  );
}

/// Unten: erfasste Karten als kleine Bilder und „Fertig“.
class _Tray extends StatelessWidget {
  const _Tray({required this.hits, required this.onDone});

  final List<LiveHit> hits;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(12, 10, 12, 16),
    color: Colors.black.withValues(alpha: 0.75),
    child: SafeArea(
      top: false,
      child: Row(
        children: [
          Expanded(
            child: hits.isEmpty
                ? const Text(
                    'Erkannte Karten erscheinen hier.',
                    style: TextStyle(color: Colors.white70),
                  )
                : SizedBox(
                    height: 64,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      reverse: true, // neueste vorn
                      itemCount: hits.length,
                      separatorBuilder: (_, _) => const SizedBox(width: 6),
                      itemBuilder: (_, index) =>
                          CardImage(url: hits[hits.length - 1 - index].card.image(), width: 46),
                    ),
                  ),
          ),
          const SizedBox(width: 12),
          FilledButton(
            key: const Key('live-done'),
            onPressed: hits.isEmpty ? null : onDone,
            child: Text('Fertig (${hits.length})'),
          ),
        ],
      ),
    ),
  );
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({required this.denied});

  final bool denied;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        key: const Key('live-unavailable'),
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.videocam_off, color: Colors.white70, size: 48),
          const SizedBox(height: 12),
          Text(
            denied
                ? 'Kein Kamerazugriff. Erlaube die Kamera für die Kartenkiste in den '
                      'Browser- bzw. Handy-Einstellungen und öffne den Live-Scanner erneut.'
                : 'Live-Kamera wird hier nicht unterstützt. Der normale Scanner mit Foto '
                      'funktioniert trotzdem.',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => context.pushReplacement('/scan'),
            icon: const Icon(Icons.photo_camera),
            label: const Text('Mit Foto scannen'),
          ),
        ],
      ),
    ),
  );
}

/// Prüfen und hinzufügen: falsche abwählen, Rest landet im gewählten Ordner (1× NM bzw. Slab).
class _ReviewSheet extends ConsumerStatefulWidget {
  const _ReviewSheet({required this.hits});

  final List<LiveHit> hits;

  @override
  ConsumerState<_ReviewSheet> createState() => _ReviewSheetState();
}

class _ReviewSheetState extends ConsumerState<_ReviewSheet> {
  bool _busy = false;

  Future<void> _addAll() async {
    final chosen = widget.hits.where((hit) => hit.selected).toList();
    if (chosen.isEmpty) return;
    setState(() => _busy = true);
    final api = ref.read(apiProvider);
    final folderId = effectiveFolderId(
      ref.read(folderChoiceProvider),
      ref.read(foldersProvider).value ?? const <Folder>[],
    );
    var added = 0;
    final ok = await runAction(context, () async {
      for (final hit in chosen) {
        await api.confirmScan(hit.scan.scanId, hit.card.id);
        final grading = hit.scan.grading;
        await api.addItem({
          'card_id': hit.card.id,
          'folder_id': ?folderId,
          'quantity': 1,
          if (grading == null) 'condition': 'NM',
          if (grading != null)
            'grading_company': gradingCompanies.contains(grading.company)
                ? grading.company
                : 'OTHER',
          if (grading?.grade != null) 'grade': grading!.grade,
        });
        added++;
      }
    });
    if (!mounted) return;
    setState(() => _busy = false);
    unawaited(HapticFeedback.mediumImpact());
    if (ok || added > 0) Navigator.of(context).pop(added);
  }

  @override
  Widget build(BuildContext context) {
    final chosen = widget.hits.where((hit) => hit.selected).length;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.8),
        child: Column(
          key: const Key('live-review'),
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${widget.hits.length} erkannt – falsche abwählen',
                      style: Theme.of(context).textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  const FolderPicker(),
                ],
              ),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final (index, hit) in widget.hits.indexed)
                    CheckboxListTile(
                      key: Key('live-hit-$index'),
                      value: hit.selected,
                      onChanged: (value) => setState(() => hit.selected = value ?? false),
                      secondary: CardImage(url: hit.card.image(), width: 36),
                      title: Text(hit.card.displayName),
                      subtitle: Text(
                        [
                          hit.card.subtitle,
                          if (hit.scan.grading case final grading?)
                            '${grading.company} ${grading.grade ?? ''}'.trim(),
                          '${(hit.match.confidence * 100).round()} % sicher',
                        ].join(' · '),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  key: const Key('live-add-all'),
                  onPressed: _busy || chosen == 0 ? null : _addAll,
                  icon: const Icon(Icons.add),
                  label: Text('$chosen ${chosen == 1 ? 'Karte' : 'Karten'} hinzufügen'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
