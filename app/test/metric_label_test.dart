import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/features/card/card_detail_screen.dart';

void main() {
  test('Kennzahlen von PriceCharting sind lesbar beschriftet', () {
    expect(metricLabel('trend'), 'Trend');
    expect(metricLabel('ungraded'), 'Roh');
    expect(metricLabel('grade_9_5'), 'Note 9,5');
    expect(metricLabel('grade_7'), 'Note 7');
    expect(metricLabel('psa_10'), 'PSA 10');
    expect(metricLabel('bgs_10_black'), 'BGS 10 Black Label');
    expect(metricLabel('cgc_10_pristine'), 'CGC 10 Pristine');
    expect(metricLabel('unbekannt'), 'unbekannt');
  });
}
