// Zeitraum für Kurven (1M · 3M · 6M · 1J · Alle) und die Veränderung im Zeitraum.
import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';
import 'value_chart.dart';

enum ChartRange {
  month(30, '1M', 'im letzten Monat'),
  quarter(90, '3M', 'in 3 Monaten'),
  half(180, '6M', 'in 6 Monaten'),
  year(365, '1J', 'im letzten Jahr'),
  all(3650, 'Alle', 'seit Beginn');

  const ChartRange(this.days, this.label, this.phrase);

  final int days;
  final String label;

  /// Für „+12,30 € (+8,1 %) in 3 Monaten“.
  final String phrase;
}

class RangeChips extends StatelessWidget {
  const RangeChips({required this.value, required this.onChanged, super.key});

  final ChartRange value;
  final ValueChanged<ChartRange> onChanged;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 6,
    children: [
      for (final range in ChartRange.values)
        ChoiceChip(
          key: Key('range-${range.label}'),
          label: Text(range.label),
          visualDensity: VisualDensity.compact,
          selected: value == range,
          onSelected: (_) => onChanged(range),
        ),
    ],
  );
}

/// „▲ +12,30 € (+8,1 %) in 3 Monaten“ – erster gegen letzten Punkt; leer ohne zwei Punkte.
class RangeChange extends StatelessWidget {
  const RangeChange({required this.points, required this.range, this.currency = 'EUR', super.key});

  final List<ChartPoint> points;
  final ChartRange range;
  final String currency;

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) return const SizedBox.shrink();
    final first = points.first.value;
    final last = points.last.value;
    final diff = last - first;
    final color = diff > 0 ? AppColors.gain : (diff < 0 ? AppColors.loss : AppColors.textMuted);
    final amount = currency == 'EUR'
        ? signedMoney(diff.toStringAsFixed(2))
        : '${diff >= 0 ? '+' : '−'}${money(diff.abs().toStringAsFixed(2), currency: currency)}';
    final pct = first == 0 ? '' : ' (${signedPercent(diff / first)})';
    return Text(
      '${diff > 0 ? '▲' : (diff < 0 ? '▼' : '■')} $amount$pct ${range.phrase}',
      key: const Key('range-change'),
      style: TextStyle(color: color, fontWeight: FontWeight.w600),
    );
  }
}
