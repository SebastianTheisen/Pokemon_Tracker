// Lade-Platzhalter mit wanderndem Glanz statt Drehkreis – die Seite „steht“ sofort (wie bei
// Instagram/YouTube) und wirkt dadurch schneller.
import 'package:flutter/material.dart';

import '../core/theme.dart';

/// Lässt alle [SkeletonBox]-Flächen darunter gemeinsam schimmern.
class Shimmer extends StatefulWidget {
  const Shimmer({required this.child, super.key});

  final Widget child;

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1300),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _controller,
    child: widget.child,
    builder: (context, child) => ShaderMask(
      blendMode: BlendMode.srcATop,
      shaderCallback: (bounds) {
        final shift = _controller.value * 3 - 1; // −1 … 2: Glanz läuft einmal durch
        return LinearGradient(
          begin: Alignment(shift - 1, -0.3),
          end: Alignment(shift, 0.3),
          colors: [
            AppColors.surfaceHigh,
            AppColors.outline.withValues(alpha: 0.9),
            AppColors.surfaceHigh,
          ],
        ).createShader(bounds);
      },
      child: child,
    ),
  );
}

class SkeletonBox extends StatelessWidget {
  const SkeletonBox({this.width, this.height = 14, this.radius = 6, super.key});

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
    width: width,
    height: height,
    decoration: BoxDecoration(
      color: AppColors.surfaceHigh,
      borderRadius: BorderRadius.circular(radius),
    ),
  );
}

/// Platzhalter für Listen (Bild links, zwei Textzeilen, Wert rechts).
class SkeletonList extends StatelessWidget {
  const SkeletonList({this.rows = 6, super.key});

  final int rows;

  @override
  Widget build(BuildContext context) => Shimmer(
    key: const Key('skeleton'),
    // Column statt ListView: funktioniert auch innerhalb scrollender Seiten.
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox(height: 8),
        for (var row = 0; row < rows; row++)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(
              children: [
                SkeletonBox(width: 40, height: 56),
                SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SkeletonBox(width: 160),
                      SizedBox(height: 8),
                      SkeletonBox(width: 100, height: 10),
                    ],
                  ),
                ),
                SkeletonBox(width: 56),
              ],
            ),
          ),
      ],
    ),
  );
}

/// Platzhalter für das Kartenraster der Sammlung.
class SkeletonGrid extends StatelessWidget {
  const SkeletonGrid({this.count = 9, super.key});

  final int count;

  @override
  Widget build(BuildContext context) => Shimmer(
    key: const Key('skeleton'),
    child: GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 130,
        mainAxisSpacing: 16,
        crossAxisSpacing: 12,
        childAspectRatio: 0.5,
      ),
      itemCount: count,
      itemBuilder: (_, _) => const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(aspectRatio: 63 / 88, child: SkeletonBox(radius: 8)),
          SizedBox(height: 8),
          SkeletonBox(width: 60),
          SizedBox(height: 6),
          SkeletonBox(width: 80, height: 10),
        ],
      ),
    ),
  );
}
