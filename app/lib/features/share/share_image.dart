// Als Bild teilen (Karte, Ordner): Vorschau zeigen, als PNG rendern, über das Teilen-Menü
// des Handys senden (WhatsApp, Instagram …) – am Rechner als Download.
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/device/device.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

const _shareSize = Size(360, 450); // 4:5 wie Instagram-Beiträge; gerendert mit 3× Pixeldichte

Future<void> showShareImage(
  BuildContext context, {
  required Widget content,
  required String filename,
  required String text,
}) => showDialog<void>(
  context: context,
  builder: (_) => _ShareDialog(content: content, filename: filename, text: text),
);

class _ShareDialog extends ConsumerStatefulWidget {
  const _ShareDialog({required this.content, required this.filename, required this.text});

  final Widget content;
  final String filename;
  final String text;

  @override
  ConsumerState<_ShareDialog> createState() => _ShareDialogState();
}

class _ShareDialogState extends ConsumerState<_ShareDialog> {
  final _boundary = GlobalKey();
  bool _busy = false;

  Future<void> _share() async {
    setState(() => _busy = true);
    final render = _boundary.currentContext?.findRenderObject() as RenderRepaintBoundary?;
    final image = await render?.toImage(pixelRatio: 3);
    final data = await image?.toByteData(format: ui.ImageByteFormat.png);
    if (!mounted) return;
    if (data == null) {
      setState(() => _busy = false);
      showMessage(context, 'Bild konnte nicht erstellt werden.');
      return;
    }
    final outcome = await ref
        .read(deviceProvider)
        .shareImage(data.buffer.asUint8List(), widget.filename, widget.text);
    if (!mounted) return;
    Navigator.of(context).pop();
    switch (outcome) {
      case ShareOutcome.downloaded:
        showMessage(context, 'Bild gespeichert (Downloads).');
      case ShareOutcome.failed:
        showMessage(context, 'Teilen ist hier nicht möglich.');
      case ShareOutcome.shared || ShareOutcome.cancelled:
        break;
    }
  }

  @override
  Widget build(BuildContext context) => Dialog(
    insetPadding: const EdgeInsets.all(16),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          FittedBox(
            child: RepaintBoundary(
              key: _boundary,
              child: SizedBox.fromSize(size: _shareSize, child: widget.content),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Abbrechen'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  key: const Key('share-confirm'),
                  onPressed: _busy ? null : _share,
                  icon: const Icon(Icons.ios_share),
                  label: const Text('Teilen'),
                ),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

/// Gemeinsamer Rahmen: Farbverlauf, Inhalt, kleine Marke unten.
class _ShareFrame extends StatelessWidget {
  const _ShareFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: const BoxDecoration(
      gradient: LinearGradient(
        colors: [Color(0xFF0B1426), Color(0xFF2A1B5E)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
    ),
    child: DefaultTextStyle(
      style: const TextStyle(color: Colors.white, fontSize: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: child),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.inventory_2, color: AppColors.accent, size: 16),
              const SizedBox(width: 6),
              Text(
                'Kartenkiste',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.8),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

/// Einzelne Karte: großes Bild, Name, Set, Preis.
class CardShareContent extends StatelessWidget {
  const CardShareContent({required this.card, this.price, this.owned = 0, super.key});

  final CardInfo card;
  final String? price;
  final int owned;

  @override
  Widget build(BuildContext context) => _ShareFrame(
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CardImage(url: card.image(high: true), width: 170),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                card.displayName,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(card.subtitle, style: TextStyle(color: Colors.white.withValues(alpha: 0.75))),
              const Spacer(),
              if (price != null) ...[
                Text(
                  'Wert (Near Mint)',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 12),
                ),
                Text(
                  money(price),
                  style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800),
                ),
              ],
              if (owned > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    '✓ $owned× in meiner Sammlung',
                    style: const TextStyle(color: Color(0xFF4ADE80), fontWeight: FontWeight.w700),
                  ),
                ),
            ],
          ),
        ),
      ],
    ),
  );
}

/// Ordner bzw. Sammlung: Gesamtwert und die wertvollsten Karten im Raster.
class CollectionShareContent extends StatelessWidget {
  const CollectionShareContent({
    required this.title,
    required this.totalValue,
    required this.items,
    required this.count,
    super.key,
  });

  final String title;
  final String totalValue;
  final List<CollectionItem> items;
  final int count;

  @override
  Widget build(BuildContext context) => _ShareFrame(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        Text(
          '${money(totalValue)} · $count ${count == 1 ? 'Karte' : 'Karten'}',
          style: TextStyle(color: Colors.white.withValues(alpha: 0.8)),
        ),
        const SizedBox(height: 12),
        Expanded(
          child: GridView.count(
            crossAxisCount: 3,
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            childAspectRatio: 63 / 88,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              for (final item in items.take(9))
                LayoutBuilder(
                  builder: (_, constraints) => CardImage(
                    url: item.image,
                    width: constraints.maxWidth,
                    contain: item.card == null,
                  ),
                ),
            ],
          ),
        ),
      ],
    ),
  );
}
