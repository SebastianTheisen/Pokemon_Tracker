import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/app.dart';
import 'package:kartenkiste/core/api.dart';
import 'package:kartenkiste/features/cardmarket/cardmarket_import.dart';
import 'package:kartenkiste/models/models.dart';
import 'package:kartenkiste/router.dart';

import 'fakes.dart';

/// Daten so kodieren, wie es das Lesezeichen tut (Base64url ohne Auffüllzeichen).
String encodePayload(Map<String, Object?> data) =>
    base64Url.encode(utf8.encode(jsonEncode(data))).replaceAll('=', '');

const page = 'https://www.cardmarket.com/de/Pokemon/Products/Singles/X/Y?language=3';

void main() {
  cardmarketEditionTests();
  ebayFetchTests();
  sealedTests();
  usMarketTests();

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

  testWidgets('Weitergeklickt (ohne Sprungmarke): gemerkte Karte, Seite merken vorgeschlagen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)..rememberedCard = 'c1';
    await pumpApp(tester, api);
    final container = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)));
    final data = encodePayload({
      'c': null,
      'u': 'https://www.cardmarket.com/de/Pokemon/Products/Singles/30th-Celebration/Charizard',
      'r': [
        {
          'condition': 'NM',
          'price': '120,00 €',
          'labels': ['Japanisch'],
        },
      ],
    });

    container.read(routerProvider).go('/cardmarket-import?d=$data');
    await tester.pumpAndSettle();

    expect(find.text('Nachtara VMAX'), findsOneWidget); // gemerkte Karte c1
    final remember = tester.widget<CheckboxListTile>(find.byKey(const Key('import-remember-page')));
    expect(remember.value, isTrue);
    await tester.ensureVisible(find.text('Preise speichern'));
    await tester.tap(find.text('Preise speichern'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('cardmarketOffers:c1:1:true:remember'));
  });
}

void cardmarketEditionTests() {
  testWidgets('Scan: unsichere Sprachfassung prüfen und für das Set übernehmen', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..cardmarketJson = cardmarketChoiceJson(selected: 908315, twins: true, uncertain: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    final tile = find.byKey(const Key('cardmarket-edition'));
    await tester.ensureVisible(tile);
    expect(find.text('Cardmarket-Sprachfassung prüfen'), findsOneWidget);
    expect(find.text('Ausgabe 6603 · laut TCGdex'), findsOneWidget);
    await tester.tap(tile);
    await tester.pumpAndSettle();

    expect(find.text('Japanisch'), findsOneWidget);
    expect(find.textContaining('Trend 158,67 €'), findsOneWidget);
    await tester.tap(find.byKey(const Key('cardmarket-option-907902')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('cardmarket-edition-save')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('chooseCardmarket:c1:907902'));
    expect(find.textContaining('Für das ganze Set übernommen (176 Karten)'), findsOneWidget);
    // Danach eindeutig gewählt: kein Hinweis mehr, aber weiterhin änderbar.
    expect(find.text('Cardmarket-Sprachfassung prüfen'), findsNothing);
    expect(find.text('Japanisch · von euch gewählt'), findsOneWidget);
  });

  testWidgets('Ausgabe benennen; ohne Sprachfassungen keine Auswahl', (tester) async {
    final api = FakeApi(loggedIn: true)..cardmarketJson = cardmarketChoiceJson(twins: true);
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('cardmarket-edition')));
    await tester.pumpAndSettle();
    // Bestätigen nur nötig, solange die Zuordnung unsicher ist.
    final save = tester.widget<FilledButton>(find.byKey(const Key('cardmarket-edition-save')));
    expect(save.onPressed, isNull);
    await tester.tap(find.byKey(const Key('cardmarket-label-6603')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'S-Chinesisch');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('labelExpansion:6603:S-Chinesisch'));
  });

  testWidgets('eindeutige Ausgabe: keine Zeile', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('cardmarket-edition')), findsNothing);
  });
}

void ebayFetchTests() {
  testWidgets('eBay direkt von ebay.de: holen, gemerkt, neu abrufen, speichern, zurück', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)..apifyStatusJson = {'configured': true};
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    final button = find.byKey(const Key('card-ebay'));
    await tester.scrollUntilVisible(button, 300, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.calls, contains('ebayFetch:c1:raw:false'));
    expect(api.calls.where((c) => c.startsWith('priceTarget')), isEmpty); // kein Browser
    expect(find.textContaining('Suche: Nachtara VMAX 215/203 -PSA -BGS'), findsOneWidget);
    expect(find.textContaining('ohne Kosten'), findsOneWidget);
    expect(find.textContaining('0.57 \$ von 7.00 \$'), findsOneWidget);

    await tester.tap(find.byKey(const Key('ebay-fetch-refresh')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('ebayFetch:c1:raw:true'));
    expect(find.textContaining('ca. 0.07 \$'), findsOneWidget);

    await tester.tap(find.text('Verkäufe speichern'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('ebaySold:c1:2:0:true')); // Konvolut nicht gewählt
    expect(find.byKey(const Key('card-ebay')), findsOneWidget); // zurück auf der Karte
  });

  testWidgets('Budget erreicht: Hinweis statt Verkäufe', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..apifyStatusJson = {'configured': true}
      ..ebayFetchError = const ApiException(
        'Monatsbudget für eBay-Abrufe erreicht (6.90 \$ von 7.00 \$)',
        statusCode: 409,
      );
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    final button = find.byKey(const Key('card-ebay'));
    await tester.scrollUntilVisible(button, 300, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(find.textContaining('Monatsbudget für eBay-Abrufe erreicht'), findsOneWidget);
    expect(find.text('Erneut versuchen'), findsOneWidget);
  });
}

void sealedTests() {
  testWidgets('Versiegeltes: Sets durchblättern, nach Art filtern, mit Kaufpreis hinzufügen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('collection-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('add-sealed')));
    await tester.pumpAndSettle();

    // Start: neueste Sets statt leerem Bildschirm
    expect(api.calls, contains('sealedSets'));
    expect(find.text('Neueste Sets'), findsOneWidget);
    await tester.tap(find.byKey(const Key('sealed-set-6100')));
    await tester.pumpAndSettle();
    expect(
      api.calls,
      contains(
        'searchSealed::'
        ':6100',
      ),
    );
    expect(find.text('Prismatische Entwicklungen'), findsWidgets); // Titel

    await tester.ensureVisible(find.byKey(const Key('sealed-kind-elite_trainer_box')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sealed-kind-elite_trainer_box')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('searchSealed::elite_trainer_box:6100'));
    expect(find.textContaining('99,00'), findsOneWidget);

    await tester.tap(find.byKey(const Key('sealed-700001')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sealed-more')));
    await tester.enterText(find.byKey(const Key('sealed-price')), '54,90');
    await tester.ensureVisible(find.byKey(const Key('sealed-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('sealed-add')));
    await tester.pumpAndSettle();

    expect(api.calls, containsAllInOrder(['productFromCardmarket:700001:de', 'addItem']));
    expect(api.lastItemBody, {
      'product_id': 'p1',
      'folder_id': 'f1',
      'quantity': 2,
      'purchase_price': '54.90',
    });
    expect(find.textContaining('Hinzugefügt: 2× Prismatic'), findsOneWidget);
  });

  testWidgets('Versiegeltes: Suche (deutsch) zeigt Treffer als Raster', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('collection-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('add-sealed')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('sealed-search')), 'prismatische ttb');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(api.calls, contains('searchSealed:prismatische ttb::'));
    expect(find.byKey(const Key('sealed-700001')), findsOneWidget);
    expect(find.text('Top-Trainer-Box'), findsWidgets);
  });
}

void usMarketTests() {
  testWidgets('US-Markt: Verkäufe je Note, POP und letzte Verkäufe auf der Karte', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..pricechartingJson = {
        'available': true,
        'fetched_at': '2026-10-21T22:00:00Z',
        'product_url': 'https://www.pricecharting.com/game/x/y',
        'population': {
          'PSA': {'9': 47519, '10': 27631},
        },
        'sales_volume': {'PSA 10': 30, 'Ungraded': 60},
        'recent_sales': [
          {
            'grade': 'PSA 10',
            'date': '2026-10-20',
            'title': 'Nachtara VMAX PSA 10',
            'price_usd': 1040.0,
            'source': 'ebay',
            'url': 'https://www.ebay.com/itm/1',
          },
        ],
        'images': <String>[],
      };
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    final section = find.byKey(const Key('us-market'));
    await tester.scrollUntilVisible(section, 300, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('fold-us-market')));
    await tester.pumpAndSettle();
    expect(find.text('US-Markt (PriceCharting)'), findsOneWidget);
    expect(find.text('Ungraded: 60×'), findsOneWidget);
    expect(find.textContaining('PSA-Population: 10: 27.631 · 9: 47.519'), findsOneWidget);
    expect(find.textContaining('PSA 10 ·'), findsOneWidget);
  });
}
