// Deutsche Formatierung für Geld, Datum und Prozent.
import 'package:intl/intl.dart';

final _euro = NumberFormat.currency(locale: 'de_DE', symbol: '€');
final _usd = NumberFormat.currency(locale: 'de_DE', symbol: r'$');
final _date = DateFormat('dd.MM.yyyy', 'de_DE');
final _dateTime = DateFormat('dd.MM.yyyy, HH:mm', 'de_DE');

/// Betrag aus der API (Dezimalzahl als Text, z. B. "1805.90").
double? parseAmount(String? value) => value == null ? null : double.tryParse(value);

/// Eingabe eines Betrags in die API-Form: „1.234,50“ → "1234.50", leer → null.
///
/// Punkte ohne Komma sind Tausenderpunkte, wenn danach genau drei Ziffern folgen
/// („2.000“ → "2000", „1.234.567“ → "1234567"); sonst Dezimalpunkt („12.50“ → "12.50").
String? normalizeAmount(String input) {
  var text = input.replaceAll(RegExp(r'[\s€]'), '');
  if (text.isEmpty) return null;
  if (text.contains(',')) {
    text = text.replaceAll('.', '').replaceAll(',', '.');
  } else if (RegExp(r'^\d{1,3}(\.\d{3})+$').hasMatch(text)) {
    text = text.replaceAll('.', '');
  }
  return text;
}

String money(String? value, {String currency = 'EUR'}) {
  final amount = parseAmount(value);
  if (amount == null) return '–';
  return currency == 'USD' ? _usd.format(amount) : _euro.format(amount);
}

/// Veränderung mit Vorzeichen: „+51,00 €“.
String signedMoney(String? value) {
  final amount = parseAmount(value);
  if (amount == null) return '–';
  final formatted = _euro.format(amount.abs());
  if (amount > 0) return '+$formatted';
  if (amount < 0) return '−$formatted';
  return formatted;
}

String date(DateTime? value) => value == null ? '–' : _date.format(value.toLocal());

String dateTime(DateTime? value) => value == null ? '–' : _dateTime.format(value.toLocal());

String percent(double value) => '${(value * 100).round()} %';

/// Veränderung in Prozent mit Vorzeichen und einer Nachkommastelle: „+20,0 %“.
/// [value] als Anteil (0.2) bzw. mit [isPercent] schon in Prozent („20.0“ vom Server).
String signedPercent(double value, {bool isPercent = false}) {
  final pct = isPercent ? value : value * 100;
  final text = pct.abs().toStringAsFixed(1).replaceAll('.', ',');
  if (pct > 0) return '+$text %';
  if (pct < 0) return '−$text %';
  return '$text %';
}

const languageLabels = {
  'de': 'Deutsch',
  'en': 'Englisch',
  'ja': 'Japanisch',
  'ko': 'Koreanisch',
  'zh-tw': 'Chinesisch (trad.)',
  'zh-cn': 'Chinesisch (vereinf.)',
};

String languageTag(String language) => switch (language) {
  'zh-tw' => 'ZH-TW',
  'zh-cn' => 'ZH-CN',
  _ => language.toUpperCase(),
};

const conditions = ['MT', 'NM', 'EX', 'GD', 'LP', 'PL', 'PO'];

const conditionLabels = {
  'MT': 'Mint',
  'NM': 'Near Mint',
  'EX': 'Excellent',
  'GD': 'Good',
  'LP': 'Light Played',
  'PL': 'Played',
  'PO': 'Poor',
};
