// Linienchart für Wertverlauf (Sammlung) und Preisverlauf (Karte).
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';

class ChartPoint {
  const ChartPoint(this.date, this.value, {this.highlighted = false});

  final DateTime date;
  final double value;
  final bool highlighted; // z. B. Live-Wert oder Bestandsänderung
}

class ValueChart extends StatelessWidget {
  const ValueChart({required this.points, this.height = 160, this.currency = 'EUR', super.key});

  final List<ChartPoint> points;
  final double height;
  final String currency;

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) {
      return SizedBox(
        height: height,
        child: const Center(
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
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => AppColors.surfaceHigh,
              getTooltipItems: (spots) => [
                for (final spot in spots)
                  LineTooltipItem(
                    '${date(start.add(Duration(hours: (spot.x * 24).round())))}\n'
                    '${money(spot.y.toStringAsFixed(2), currency: currency)}',
                    const TextStyle(color: Colors.white, fontSize: 12),
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
              gradient: AppColors.scanGradient,
              dotData: FlDotData(
                checkToShowDot: (spot, _) => points[spots.indexOf(spot)].highlighted,
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  colors: [
                    AppColors.primary.withValues(alpha: 0.25),
                    AppColors.primary.withValues(alpha: 0),
                  ],
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
