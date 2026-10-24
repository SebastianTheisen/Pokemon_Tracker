// Karte im Vollbild: zoomen (zwei Finger / Doppeltipp) und Holo-Effekt beim Neigen des Handys –
// ohne Sensor (Desktop, abgelehnt) folgt der Glanz dem Finger.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

Future<void> openCardViewer(BuildContext context, CardInfo card) => Navigator.of(context).push(
  PageRouteBuilder<void>(
    opaque: false,
    barrierColor: Colors.black,
    pageBuilder: (_, _, _) => CardViewer(card: card),
    transitionsBuilder: (_, animation, _, child) =>
        FadeTransition(opacity: animation, child: child),
  ),
);

class CardViewer extends ConsumerStatefulWidget {
  const CardViewer({required this.card, super.key});

  final CardInfo card;

  @override
  ConsumerState<CardViewer> createState() => _CardViewerState();
}

class _CardViewerState extends ConsumerState<CardViewer> {
  /// Neigung bzw. Fingerposition, je Achse −1 … 1.
  Offset _tilt = Offset.zero;
  bool _sensor = false;
  StreamSubscription<({double beta, double gamma})>? _subscription;
  final _zoom = TransformationController();

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    _zoom.dispose();
    super.dispose();
  }

  Future<void> _enableSensor() async {
    final device = ref.read(deviceProvider);
    if (!await device.requestTilt()) {
      if (mounted) showMessage(context, 'Neigungssensor nicht verfügbar – zieh mit dem Finger.');
      return;
    }
    _subscription = device.tilt().listen((value) {
      if (!mounted) return;
      // Handy normal gehalten: vor/zurück um ~45°, links/rechts um 0°.
      setState(
        () => _tilt = Offset(
          (value.gamma / 30).clamp(-1.0, 1.0),
          ((value.beta - 45) / 30).clamp(-1.0, 1.0),
        ),
      );
    });
    setState(() => _sensor = true);
  }

  void _drag(DragUpdateDetails details, Size size) {
    if (_sensor) return;
    setState(
      () => _tilt = Offset(
        (_tilt.dx + details.delta.dx / size.width * 2).clamp(-1.0, 1.0),
        (_tilt.dy + details.delta.dy / size.height * 2).clamp(-1.0, 1.0),
      ),
    );
  }

  void _toggleZoom() {
    final zoomed = _zoom.value.getMaxScaleOnAxis() > 1.01;
    _zoom.value = zoomed ? Matrix4.identity() : (Matrix4.identity()..scaleByDouble(2.2, 2.2, 1, 1));
  }

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(card.displayName),
        actions: [
          if (!_sensor)
            TextButton.icon(
              key: const Key('viewer-tilt'),
              onPressed: _enableSensor,
              icon: const Icon(Icons.screen_rotation_alt, color: Colors.white),
              label: const Text('Holo', style: TextStyle(color: Colors.white)),
            ),
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final width = math.min(constraints.maxWidth - 48, (constraints.maxHeight - 96) * 63 / 88);
          return GestureDetector(
            onPanUpdate: (details) => _drag(details, constraints.biggest),
            onDoubleTap: _toggleZoom,
            child: Center(
              child: InteractiveViewer(
                key: const Key('viewer-zoom'),
                transformationController: _zoom,
                maxScale: 5,
                child: Hero(
                  tag: 'card-image-${card.id}',
                  child: _HoloCard(card: card, width: width, tilt: _tilt),
                ),
              ),
            ),
          );
        },
      ),
      bottomNavigationBar: const SafeArea(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'Zwei Finger oder Doppeltipp: zoomen · Ziehen bzw. „Holo“: Glanz',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white70, fontSize: 12),
          ),
        ),
      ),
    );
  }
}

/// Karte leicht gekippt (3D) mit wanderndem Regenbogen-Glanz – wie echte Holo-Karten im Licht.
class _HoloCard extends StatelessWidget {
  const _HoloCard({required this.card, required this.width, required this.tilt});

  final CardInfo card;
  final double width;
  final Offset tilt;

  @override
  Widget build(BuildContext context) {
    final height = width * 88 / 63;
    final shine = Alignment(tilt.dx * 1.5, tilt.dy * 1.5);
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.identity()
        ..setEntry(3, 2, 0.0012)
        ..rotateX(-tilt.dy * 0.18)
        ..rotateY(tilt.dx * 0.18),
      child: Container(
        key: const Key('viewer-card'),
        width: width,
        height: height,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(width / 22),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.6),
              blurRadius: 30,
              offset: Offset(-tilt.dx * 18, 20 - tilt.dy * 10),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(width / 22),
          child: Stack(
            fit: StackFit.expand,
            children: [
              CardImage(url: card.image(high: true), width: width),
              IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    backgroundBlendMode: BlendMode.overlay,
                    gradient: LinearGradient(
                      begin: Alignment(-1 + shine.x, -1 + shine.y),
                      end: Alignment(1 + shine.x, 1 + shine.y),
                      colors: const [
                        Color(0x00FFFFFF),
                        Color(0x55FF6EC7),
                        Color(0x6670E1FF),
                        Color(0x66FFF27A),
                        Color(0x557CFFB2),
                        Color(0x00FFFFFF),
                      ],
                      stops: const [0.25, 0.38, 0.47, 0.55, 0.63, 0.75],
                    ),
                  ),
                ),
              ),
              IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      center: shine,
                      radius: 0.9,
                      colors: [
                        Colors.white.withValues(alpha: 0.28),
                        Colors.white.withValues(alpha: 0),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
