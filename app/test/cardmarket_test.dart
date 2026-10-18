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
    final payload = CardmarketPayload.decode(
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
    expect(payload.rows.single.labels, ['Deutsch']);
    expect(CardmarketPayload.decode('kein base64 !!'), isNull);
    expect(CardmarketPayload.decode(null), isNull);
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
}
