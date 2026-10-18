import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/app.dart';
import 'package:kartenkiste/features/cardmarket/cardmarket_import.dart';
import 'package:kartenkiste/models/models.dart';
import 'package:kartenkiste/router.dart';

import 'fakes.dart';

/// Daten so kodieren, wie es das Lesezeichen tut (Base64url ohne Auffüllzeichen).
String encodePayload(Map<String, Object?> data) =>
    base64Url.encode(utf8.encode(jsonEncode(data))).replaceAll('=', '');

const page = 'https://www.cardmarket.com/de/Pokemon/Products/Singles/X/Y?language=3';

void main() {
  test('gefilterter Cardmarket-Link nur mit Produkt-ID', () {
    const product = 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273';
    expect(
      cardmarketOffersUrl(productUrl: product, cardId: 'c1', language: 'de', condition: 'EX'),
      '$product&language=3&minCondition=3#kartenkiste=c1',
    );
    expect(
      cardmarketOffersUrl(productUrl: product, cardId: 'c1', language: 'ja'),
      '$product&language=7&minCondition=2#kartenkiste=c1',
    );
    expect(
      cardmarketOffersUrl(
        productUrl: 'https://www.cardmarket.com/de/Pokemon/Products/Search?searchString=x',
        cardId: 'c1',
        language: 'de',
      ),
      isNull,
    );
  });

  test('Lesezeichen-Daten werden gelesen, Unsinn ergibt null', () {
    final payload = BookmarkletPayload.decode(
      encodePayload({
        'c': 'c1',
        'u': page,
        'r': [
          {
            'condition': 'NM',
            'price': '180,00 €',
            'labels': ['Deutsch'],
          },
        ],
      }),
    )!;
    expect(payload.cardId, 'c1');
    expect(payload.pageUrl, page);
    expect(payload.offerRows.single.labels, ['Deutsch']);
    expect(BookmarkletPayload.decode('kein base64 !!'), isNull);
    expect(BookmarkletPayload.decode(null), isNull);
  });

  test('Lesezeichen-Code enthält die App-Adresse und ist ein javascript:-Link', () {
    final code = bookmarkletCode('https://kartenkiste.example.ts.net');
    expect(code, startsWith('javascript:(()=>{'));
    expect(code, contains('"https://kartenkiste.example.ts.net"'));
    expect(code, isNot(contains('\n')));
  });

  testWidgets('Import: Anmeldung, Vorschau, speichern → zurück zur Karte', (tester) async {
    final api = FakeApi();
    await pumpApp(tester, api);
    final container = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)));
    final data = encodePayload({
      'c': 'c1',
      'u': page,
      'r': [
        {
          'condition': 'NM',
          'price': '180,00 €',
          'labels': ['Deutsch'],
        },
      ],
    });

    container.read(routerProvider).go('/cardmarket-import?d=$data');
    await tester.pumpAndSettle();
    expect(find.text('Anmelden'), findsOneWidget); // Ziel bleibt gemerkt
    await tester.enterText(find.byKey(const Key('login-email')), 'ich@example.com');
    await tester.enterText(find.byKey(const Key('login-password')), 'richtig-gutes-passwort');
    await tester.tap(find.text('Anmelden'));
    await tester.pumpAndSettle();

    expect(find.text('Cardmarket-Angebote'), findsOneWidget);
    expect(find.text('ab 180,00 €'), findsOneWidget);
    expect(api.calls, contains('cardmarketOffers:c1:1:false'));

    await tester.tap(find.text('Preise speichern'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('cardmarketOffers:c1:1:true'));
    expect(find.text('Cardmarket-Preise gespeichert.'), findsOneWidget);
    expect(find.byKey(const Key('cardmarket-offers')), findsOneWidget); // Karten-Detail
  });

  test('Median, Spanne und Anzahl der gewählten Verkäufe', () {
    final stats = soldStats([200, 160, 180]);
    expect((stats.median, stats.low, stats.high, stats.count), (180, 160, 200, 3));
    expect(soldStats([100, 200]).median, 150);
    expect(variantLabel('graded:PSA 10'), 'PSA 10');
    expect(variantLabel('raw'), 'ungegradet');
  });

  testWidgets('eBay-Import: Vorschlag, abwählen, speichern', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final container = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)));
    final data = encodePayload({
      'c': 'c1',
      'u': 'https://www.ebay.de/sch/i.html?_nkw=x&LH_Sold=1',
      'r': [
        {'title': 'Nachtara VMAX 215/203', 'price': '180,00 €', 'sold': 'Verkauft 12. Okt 2026'},
        {'title': 'Nachtara VMAX 215/203 PSA 10', 'price': '650,00 €', 'sold': ''},
        {'title': 'Konvolut 50 Karten', 'price': '40,00 €', 'sold': ''},
      ],
    });

    container.read(routerProvider).go('/ebay-import?d=$data');
    await tester.pumpAndSettle();

    expect(find.text('eBay-Verkäufe'), findsOneWidget);
    expect(find.text('Median 180,00\u00a0€'), findsOneWidget);
    expect(find.text('Median 650,00\u00a0€'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('sale-1')));
    await tester.tap(find.byKey(const Key('sale-1'))); // PSA-Verkauf abwählen
    await tester.pumpAndSettle();
    expect(find.text('Median 650,00\u00a0€'), findsNothing);

    await tester.ensureVisible(find.text('Verkäufe speichern'));
    await tester.tap(find.text('Verkäufe speichern'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('ebaySold:c1:3:0:true'));
    expect(find.text('eBay-Verkäufe gespeichert.'), findsOneWidget);
  });
}
