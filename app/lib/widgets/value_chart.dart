// Linienchart für Wertverlauf (Sammlung) und Preisverlauf (Karte).
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/format.dart';
import '../core/theme.dart';

class ChartPoint {
  const ChartPoint(this.date, this.value, {this.highlighted = false});

  final DateTime date;
  final double value;
  final bool highlighted; // z. B. Live-Wert oder Bestandsänderung
}

class ValueChart extends StatelessWidget {
  const ValueChart({
    required this.points,
    this.height = 160,
    this.currency = 'EUR',
    this.onDark = false,
    this.emptyHint = true,
    this.onScrub,
    super.key,
  });

  /// Finger auf der Kurve (wie bei Trading-Apps): Punkt unter dem Finger, `null` beim Loslassen.
  /// Ohne Rückruf zeigt die Kurve wie bisher eine Sprechblase.
  final ValueChanged<ChartPoint?>? onScrub;

  final List<ChartPoint> points;
  final double height;
  final String currency;

  /// Weiße Linie auf farbigem Hintergrund (Wert-Karte der Startseite).
  final bool onDark;

  /// Ohne Daten einen Hinweis zeigen (sonst nur Platz freihalten).
  final bool emptyHint;

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) {
      if (!emptyHint) return SizedBox(height: height);
      return SizedBox(
        height: height,
        child: Center(
          child: Text(
            'Die Kurve entsteht ab jetzt mit jedem Tag.\nVergangene Tage werden nicht nachgetragen.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted),
          ),
        ),
      );
    }
    final start = points.first.date;
    double x(DateTime date) => date.difference(start).inHours / 24;
    final spots = [for (final p in points) FlSpot(x(p.date), p.value)];
    final values = points.map((p) => p.value);
    final low = values.reduce((a, b) => a < b ? a : b);
    final high = values.reduce((a, b) => a > b ? a : b);
    final padding = (high - low).abs() < 0.01 ? (high.abs() * 0.1 + 1) : (high - low) * 0.15;
    // Farbe nach Richtung im gezeigten Zeitraum: grün aufwärts, rot abwärts.
    final rising = points.last.value >= points.first.value;
    final lineColor = onDark ? Colors.white : (rising ? AppColors.gain : AppColors.loss);
    final scrub = onScrub;

    return SizedBox(
      height: height,
      child: LineChart(
        LineChartData(
          minY: low - padding,
          maxY: high + padding,
          gridData: const FlGridData(show: false),
          borderData: FlBorderData(show: false),
          titlesData: const FlTitlesData(show: false),
          lineTouchData: LineTouchData(
            // Immer den nächstgelegenen Tag nehmen – auch zwischen weit auseinanderliegenden Punkten.
            touchSpotThreshold: 10000,
            touchCallback: scrub == null
                ? null
                : (event, response) {
                    final spot = response?.lineBarSpots?.firstOrNull;
                    final ended =
                        event is FlPanEndEvent ||
                        event is FlPanCancelEvent ||
                        event is FlTapUpEvent ||
                        event is FlTapCancelEvent ||
                        event is FlLongPressEnd ||
                        event is FlPointerExitEvent;
                    if (ended || spot == null) {
                      scrub(null);
                      return;
                    }
                    final point = points[spot.spotIndex];
                    scrub(point);
                    HapticFeedback.selectionClick();
                  },
            getTouchedSpotIndicator: (bar, indexes) => [
              for (final _ in indexes)
                TouchedSpotIndicatorData(
                  FlLine(
                    color: lineColor.withValues(alpha: 0.6),
                    strokeWidth: 1.5,
                    dashArray: [4, 4],
                  ),
                  FlDotData(
                    getDotPainter: (_, _, _, _) => FlDotCirclePainter(
                      radius: 5,
                      color: lineColor,
                      strokeWidth: 2,
                      strokeColor: Colors.white,
                    ),
                  ),
                ),
            ],
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => AppColors.surfaceHigh,
              // Mit Mitzieh-Anzeige steht der Wert oben – keine zusätzliche Sprechblase.
              getTooltipItems: (spots) => [
                for (final spot in spots)
                  if (scrub != null)
                    null
                  else
                    LineTooltipItem(
                      '${date(start.add(Duration(hours: (spot.x * 24).round())))}\n'
                      '${money(spot.y.toStringAsFixed(2), currency: currency)}',
                      TextStyle(color: Theme.of(context).colorScheme.onSurface, fontSize: 12),
                    ),
              ],
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              preventCurveOverShooting: true,
              barWidth: 2.5,
              color: lineColor,
              dotData: FlDotData(
                checkToShowDot: (spot, _) => points[spots.indexOf(spot)].highlighted,
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  colors: [lineColor.withValues(alpha: 0.25), lineColor.withValues(alpha: 0)],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Zeile über der Kurve, solange der Finger darauf liegt: „Mo., 12.10.2026 · 3.456,00 €  +5,2 %“
/// (Veränderung gegenüber dem Anfang des Zeitraums).
class ScrubLine extends StatelessWidget {
  const ScrubLine({required this.point, required this.first, this.currency = 'EUR', super.key});

  final ChartPoint point;
  final ChartPoint first;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final diff = point.value - first.value;
    final color = diff > 0 ? AppColors.gain : (diff < 0 ? AppColors.loss : AppColors.textMuted);
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: '${date(point.date)} · '),
          TextSpan(
            text: money(point.value.toStringAsFixed(2), currency: currency),
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          if (first.value != 0)
            TextSpan(
              text: '  ${signedPercent(diff / first.value)}',
              style: TextStyle(color: color, fontWeight: FontWeight.w600),
            ),
        ],
      ),
      key: const Key('scrub-line'),
    );
  }
}
