// Konfetti für besondere Momente (Set komplett) – einmalig, blockiert keine Eingaben.
import 'dart:math' as math;

import 'package:flutter/material.dart';

class ConfettiBurst extends StatefulWidget {
  const ConfettiBurst({this.pieces = 90, super.key});

  final int pieces;

  @override
  State<ConfettiBurst> createState() => _ConfettiBurstState();
}

class _Piece {
  _Piece(math.Random random)
    : x = random.nextDouble(),
      speed = 0.6 + random.nextDouble() * 0.8,
      drift = (random.nextDouble() - 0.5) * 0.4,
      spin = (random.nextDouble() - 0.5) * 12,
      size = 5 + random.nextDouble() * 6,
      delay = random.nextDouble() * 0.25,
      color = _colors[random.nextInt(_colors.length)];

  static const _colors = [
    Color(0xFF4C7DFF),
    Color(0xFF8B5CF6),
    Color(0xFF22C55E),
    Color(0xFFF59E0B),
    Color(0xFFEF4444),
    Color(0xFFFFFFFF),
  ];

  final double x;
  final double speed;
  final double drift;
  final double spin;
  final double size;
  final double delay;
  final Color color;
}

class _ConfettiBurstState extends State<ConfettiBurst> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2600),
  )..forward();
  late final List<_Piece> _pieces = List.generate(widget.pieces, (_) => _Piece(_random));
  final _random = math.Random();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: AnimatedBuilder(
      animation: _controller,
      builder: (_, _) => _controller.isCompleted
          ? const SizedBox.shrink()
          : CustomPaint(
              key: const Key('confetti'),
              size: Size.infinite,
              painter: _ConfettiPainter(_pieces, _controller.value),
            ),
    ),
  );
}

class _ConfettiPainter extends CustomPainter {
  _ConfettiPainter(this.pieces, this.progress);

  final List<_Piece> pieces;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    for (final piece in pieces) {
      final t = ((progress - piece.delay) / (1 - piece.delay)).clamp(0.0, 1.0);
      if (t == 0) continue;
      final y = -20 + t * piece.speed * size.height * 1.1;
      final x = (piece.x + piece.drift * t) * size.width + math.sin(t * 10 + piece.x * 6) * 12;
      final paint = Paint()..color = piece.color.withValues(alpha: 1 - t * t);
      canvas
        ..save()
        ..translate(x, y)
        ..rotate(piece.spin * t)
        ..drawRect(
          Rect.fromCenter(center: Offset.zero, width: piece.size, height: piece.size * 0.5),
          paint,
        )
        ..restore();
    }
  }

  @override
  bool shouldRepaint(_ConfettiPainter oldDelegate) => oldDelegate.progress != progress;
}
