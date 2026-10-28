// Live-Scanner (wie Collectr/TCGplayer): Kamera läuft, Karte hinhalten – die App erkennt sie
// selbst, vibriert und sammelt sie in einer Liste. Am Ende prüfen und alle auf einmal hinzufügen.
//
// Damit nicht dauernd Bilder zum Server gehen, wird nur ausgelöst, wenn das Bild ruhig ist
// UND sich seit dem letzten Foto deutlich verändert hat (also eine neue Karte daliegt).
// Der Auslöser-Knopf erkennt sofort – Rückfallweg, falls die Automatik nicht anspringt
// (z. B. unruhiges Kamerabild bei wenig Licht).
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

/// Ruhig: mittlere Grauwert-Änderung zwischen zwei Messungen (0–255) darunter. iPhone-Kameras
/// rauschen innen stärker – 6 war dort nie erreicht.
const stillThreshold = 9.0;

/// Neue Szene: Abstand zum letzten Foto darüber.
const changeThreshold = 14.0;

/// So viele ruhige Messungen hintereinander, bevor ausgelöst wird.
const stillSamples = 2;

const _tick = Duration(milliseconds: 300);

/// Nach so vielen Messungen ohne Auslösen den Auslöser-Knopf als Tipp nennen (≈ 6 s).
const hintAfterTicks = 20;

/// Höchstens so viele Erkennungen gleichzeitig im Hintergrund.
const maxPending = 3;

/// So lange bleibt die Bestätigung („✓ Karte“ mit Ausschnitt) stehen.
const confirmDuration = Duration(milliseconds: 1600);

/// Eine erkannte Karte der laufenden Sitzung.
class LiveHit {
  LiveHit({required this.scan, required this.match, this.crop}) : selected = true;

  final ScanResult scan;
  final ScanMatch match;

  /// Fotoausschnitt der Karte (Bestätigung und Tipp).
  final Uint8List? crop;
  bool selected;

  CardInfo get card => match.card;
}

enum _Phase { starting, running, denied, unsupported }

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

  /// Foto wird gerade aufgenommen (kurz); die Erkennung selbst läuft im Hintergrund weiter,
  /// währenddessen kann schon die nächste Karte hingelegt werden.
  bool _capturing = false;
  int _pending = 0;

  /// Messungen seit dem letzten Foto bzw. ohne Kamerabild.
  int _idleTicks = 0;
  int _noSignalTicks = 0;

  /// Unsicherer Treffer: bester Tipp zum Bestätigen („Ist es Glurak ex?“).
  LiveHit? _guess;

  /// Bestätigung eines Treffers: Ausschnitt + Name.
  LiveHit? _confirmed;
  bool _confirmedDuplicate = false;
  Timer? _confirmTimer;

  /// Kurze Meldung unten im Bild („Nicht erkannt …“).
  String? _flash;
  Timer? _flashTimer;

  /// Kurzes Aufblitzen beim Auslösen (wie die Kamera-App).
  bool _shutterFlash = false;

  @override
  void initState() {
    super.initState();
    unawaited(_start());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _flashTimer?.cancel();
    _confirmTimer?.cancel();
    _camera.stop();
    super.dispose();
  }

  Future<void> _start() async {
    final result = await _camera.start();
    if (!mounted) return;
    setState(
      () => _phase = switch (result) {
        CameraStart.ok => _Phase.running,
        CameraStart.denied => _Phase.denied,
        CameraStart.unsupported => _Phase.unsupported,
      },
    );
    if (result == CameraStart.ok) _timer = Timer.periodic(_tick, (_) => _check());
  }

  bool get _canCapture => !_capturing && _pending < maxPending;

  void _check() {
    if (!_canCapture || !mounted) return;
    final (:motion, :change) = _camera.measure();
    final hintBefore = _hint;
    if (motion < 0) {
      _noSignalTicks++; // Kamera liefert (noch) kein Bild
    } else {
      _noSignalTicks = 0;
      _still = motion < stillThreshold ? _still + 1 : 0;
      if (_still >= stillSamples && change > changeThreshold) {
        unawaited(_capture());
        return;
      }
    }
    _idleTicks++;
    if (_hint != hintBefore) setState(() {});
  }

  /// Hinweis in der Statuszeile, wenn die Automatik nicht anspringt.
  String? get _hint => _noSignalTicks >= stillSamples * 5
      ? 'Kamera liefert kein Bild – Auslöser antippen'
      : _idleTicks >= hintAfterTicks && _pending == 0
      ? 'Erkennt nichts? Auslöser antippen'
      : null;

  /// Foto aufnehmen und die Erkennung im Hintergrund starten.
  Future<void> _capture() async {
    if (!_canCapture) return;
    _capturing = true;
    _still = 0;
    _idleTicks = 0;
    try {
      final bytes = await _camera.frame(guide: liveGuide);
      if (!mounted) return;
      if (bytes == null) {
        _show('Kein Kamerabild – Live-Scanner neu öffnen oder mit Foto scannen');
        return;
      }
      unawaited(HapticFeedback.selectionClick());
      setState(() {
        _pending++;
        _shutterFlash = true;
      });
      Timer(const Duration(milliseconds: 120), () {
        if (mounted) setState(() => _shutterFlash = false);
      });
      unawaited(_recognize(bytes));
    } finally {
      _capturing = false;
    }
  }

  Future<void> _recognize(Uint8List bytes) async {
    try {
      final result = await ref
          .read(apiProvider)
          .scan(UploadImage(bytes: bytes, filename: 'live.jpg'));
      if (!mounted) return;
      final best = result.best;
      if (result.looksEmpty) {
        return; // keine Karte im Bild (Tisch, Boden …) – still verwerfen
      } else if (result.confident && best != null) {
        _take(LiveHit(scan: result, match: best, crop: bytes));
      } else if (best != null) {
        // Wie bei Collectr: bester Tipp zum Bestätigen statt nur „nicht sicher“.
        setState(() => _guess = LiveHit(scan: result, match: best, crop: bytes));
      } else {
        _show('Nicht erkannt – Karte ruhig und ganz in den Rahmen halten');
      }
    } on ApiException catch (error) {
      _show(error.message);
    } finally {
      if (mounted) setState(() => _pending--);
    }
  }

  /// Treffer übernehmen (doppelt hintereinander zählt nur einmal) und kurz bestätigen.
  void _take(LiveHit hit) {
    final duplicate = _hits.isNotEmpty && _hits.last.card.id == hit.card.id;
    _confirmTimer?.cancel();
    setState(() {
      if (identical(_guess, hit)) _guess = null;
      if (!duplicate) _hits.add(hit);
      _confirmed = hit;
      _confirmedDuplicate = duplicate;
      _flash = null;
    });
    if (!duplicate) unawaited(HapticFeedback.heavyImpact());
    _confirmTimer = Timer(confirmDuration, () {
      if (mounted) setState(() => _confirmed = null);
    });
  }

  void _show(String text) {
    if (!mounted) return;
    _flashTimer?.cancel();
    setState(() => _flash = text);
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

  String get _status => switch (_phase) {
    _Phase.starting => 'Kamera startet …',
    _ when _pending > 0 =>
      _pending == 1 ? 'Erkenne … nächste Karte hinlegen' : 'Erkenne $_pending Karten …',
    _ => _hint ?? 'Karte in den Rahmen legen – ruhig halten',
  };

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
          IgnorePointer(
            child: AnimatedOpacity(
              opacity: _shutterFlash ? 0.5 : 0,
              duration: const Duration(milliseconds: 100),
              child: const ColoredBox(color: Colors.white),
            ),
          ),
          Positioned(
            left: 16,
            right: 16,
            top: 16,
            child: _StatusPill(text: _status, busy: _phase == _Phase.starting || _pending > 0),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 104,
            child: Center(
              child: _Shutter(
                busy: _capturing,
                onPressed: _phase == _Phase.running && _canCapture
                    ? () => unawaited(_capture())
                    : null,
              ),
            ),
          ),
          if (_confirmed case final hit?)
            Positioned(
              left: 16,
              right: 16,
              bottom: 186,
              child: _Confirmation(key: ValueKey(hit), hit: hit, duplicate: _confirmedDuplicate),
            )
          else if (_guess case final guess?)
            Positioned(
              left: 16,
              right: 16,
              bottom: 186,
              child: _GuessCard(
                hit: guess,
                onTake: () => _take(guess),
                onDismiss: () => setState(() => _guess = null),
              ),
            )
          else if (_flash case final text?)
            Positioned(left: 16, right: 16, bottom: 194, child: _Flash(text: text)),
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

/// Bestätigung wie bei Collectr: der fotografierte Ausschnitt, Name und Häkchen – springt kurz
/// auf und verschwindet wieder; die Karte liegt dann unten in der Leiste.
class _Confirmation extends StatelessWidget {
  const _Confirmation({required this.hit, required this.duplicate, super.key});

  final LiveHit hit;
  final bool duplicate;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0.6, end: 1),
    duration: const Duration(milliseconds: 260),
    curve: Curves.easeOutBack,
    builder: (context, scale, child) => Opacity(
      opacity: scale.clamp(0, 1),
      child: Transform.scale(scale: scale, child: child),
    ),
    child: Material(
      key: const Key('live-confirm'),
      color: duplicate ? AppColors.warning : AppColors.gain,
      borderRadius: BorderRadius.circular(16),
      elevation: 6,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: SizedBox(
                width: 56,
                height: 78,
                child: hit.crop == null
                    ? CardImage(url: hit.card.image(), width: 56)
                    : Image.memory(hit.crop!, fit: BoxFit.cover, gaplessPlayback: true),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    duplicate ? 'Schon erfasst' : 'Erkannt',
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                  Text(
                    hit.card.displayName,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 16,
                    ),
                  ),
                  Text(
                    hit.card.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Icon(duplicate ? Icons.repeat : Icons.check_circle, color: Colors.white, size: 32),
          ],
        ),
      ),
    ),
  );
}

/// Kartenrahmen als Hilfe (Kartenformat 63 × 88), Rest abgedunkelt.
class _FramePainter extends CustomPainter {
  const _FramePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rect = liveGuide.rect(size);
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

/// Runder Auslöser wie in der Kamera-App: erkennt das aktuelle Bild sofort.
class _Shutter extends StatelessWidget {
  const _Shutter({required this.busy, required this.onPressed});

  final bool busy;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: 'Jetzt erkennen',
    child: GestureDetector(
      key: const Key('live-shutter'),
      onTap: onPressed,
      child: Container(
        width: 68,
        height: 68,
        padding: const EdgeInsets.all(5),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 4),
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: onPressed == null ? Colors.white38 : Colors.white,
          ),
          child: busy
              ? const Padding(
                  padding: EdgeInsets.all(14),
                  child: CircularProgressIndicator(strokeWidth: 3, color: Colors.black54),
                )
              : null,
        ),
      ),
    ),
  );
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
  const _Flash({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Center(
    child: Container(
      key: const Key('live-flash'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(color: AppColors.warning, borderRadius: BorderRadius.circular(14)),
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
          // Eigenes Foto neben dem Katalogbild – so sieht man sofort, ob es passt.
          if (hit.crop case final crop?) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.memory(crop, width: 42, height: 59, fit: BoxFit.cover),
            ),
            const SizedBox(width: 6),
          ],
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
