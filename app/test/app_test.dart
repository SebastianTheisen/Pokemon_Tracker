import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/models/json.dart';

import 'fakes.dart';

void main() {
  moversTests();
  profitTests();
  variantTests();
  psaTests();

  testWidgets('ohne Sitzung: Anmeldung, falsches und richtiges Passwort', (tester) async {
    final api = FakeApi();
    await pumpApp(tester, api);

    expect(find.text('Anmelden'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('login-email')), 'ich@example.com');
    await tester.enterText(find.byKey(const Key('login-password')), 'falsch');
    await tester.tap(find.text('Anmelden'));
    await tester.pumpAndSettle();
    expect(find.text('E-Mail oder Passwort falsch.'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('login-password')), 'richtig-gutes-passwort');
    await tester.tap(find.text('Anmelden'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Hallo Sebastian'), findsOneWidget);
    expect(find.text('4.894,67\u00a0€'), findsOneWidget);
    expect(find.text('▲ +51,00\u00a0€'), findsOneWidget);
    expect(find.text('Wertvollste Karten'), findsOneWidget);
  });

  testWidgets('Registrierung prüft Eingaben', (tester) async {
    await pumpApp(tester, FakeApi());
    await tester.tap(find.text('Neu hier? Mit Einladungscode registrieren'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Konto anlegen'));
    await tester.pumpAndSettle();
    expect(find.text('Bitte ausfüllen'), findsWidgets);
    expect(find.text('Mindestens 10 Zeichen'), findsOneWidget);
  });

  testWidgets('Suche → Karten-Detail mit Schätzung, Beleg und Verlauf', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);

    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('search-field')), 'nachtara 215');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(api.calls, contains('search:nachtara 215'));

    await tester.tap(find.text('Nachtara VMAX'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('condition-value')), findsOneWidget);
    expect(find.text('1.805,90\u00a0€'), findsWidgets);
    expect(find.text('Schätzung'), findsWidgets);
    expect(find.text('Beleg ansehen'), findsOneWidget);
    final lowest = find.textContaining('Tiefster Preis: 1.790,00\u00a0€');
    final mainList = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(lowest, 300, scrollable: mainList);
    expect(lowest, findsOneWidget);
    await tester.scrollUntilVisible(find.text('EX'), -300, scrollable: mainList);

    await tester.tap(find.text('EX'));
    await tester.pumpAndSettle();
    expect(find.text('1.535,02\u00a0€'), findsWidgets);
  });

  testWidgets('ohne belegten Preis wird keine Zahl erfunden', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..pricesJson = {
        'card_id': 'c1',
        'status': 'no_data',
        'last_checked_at': null,
        'offers': <Object>[],
        'conditions': <Object>[],
      };
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first; // wertvollste Karte auf der Startseite
    await tester.ensureVisible(topCard); // liegt unterhalb des sichtbaren Bereichs
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('no-price')), findsOneWidget);
  });

  testWidgets('Scan → ein Tipp fügt hinzu (Slab mit Note), dann nächste Karte', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..scanResult = scanJson(grading: {'company': 'PSA', 'grade': '10'});
    await pumpApp(tester, api);

    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('scan:galerie.jpg'));
    expect(find.text('Erkannt'), findsOneWidget);
    // Slab ohne gespeicherte PSA-10-Verkäufe: kein Rohkarten-Preis, sondern Weg zu eBay.
    expect(find.byKey(const Key('scan-price')), findsNothing);
    expect(find.byKey(const Key('scan-graded-ebay')), findsOneWidget);
    expect(find.text('Slab: PSA 10'), findsOneWidget);
    expect(find.text('Umbreon VMAX'), findsNothing); // Alternativen erst auf Wunsch

    await tester.tap(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();
    expect(api.calls, containsAllInOrder(['confirm:scan1:c1', 'addItem']));
    expect(api.lastItemBody, {
      'card_id': 'c1',
      'quantity': 1,
      'grading_company': 'PSA',
      'grade': '10',
    });
    expect(find.text('Hinzugefügt'), findsOneWidget);

    await tester.tap(find.byKey(const Key('scan-next')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('scan-camera')), findsOneWidget);
  });

  testWidgets('unsicherer Scan: andere Karte wählen und hinzufügen', (tester) async {
    final api = FakeApi(loggedIn: true)..scanResult = scanJson(confident: false);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-camera')));
    await tester.pumpAndSettle();

    expect(find.text('Bitte prüfen'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('scan-other')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-other')));
    await tester.pumpAndSettle();
    // Die Liste baut weiter unten liegende Inhalte erst beim Scrollen.
    await tester.scrollUntilVisible(
      find.text('Umbreon VMAX'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Umbreon VMAX'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('scan-card-name')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('confirm:scan1:c2'));
    expect(api.lastItemBody?['condition'], 'NM');
  });

  testWidgets('Hinzufügen von der Karten-Seite: nur Zustand und Anzahl', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('add-to-collection')));
    await tester.pumpAndSettle();

    expect(find.text('Kaufpreis (Stück)'), findsNothing); // eingeklappt
    await tester.tap(find.text('EX').last);
    await tester.tap(find.byIcon(Icons.add).last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('item-save')));
    await tester.pumpAndSettle();
    expect(api.lastItemBody?['condition'], 'EX');
    expect(api.lastItemBody?['quantity'], 2);
  });

  testWidgets('Japanische Karte zeigt deutschen Namen und Original', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..scanResult = {
        ...scanJson(),
        'best': {
          'card': cardJson(
            id: 'jp1',
            name: 'ピカチュウex',
            number: '132',
            language: 'ja',
            translatedName: 'Pikachu ex',
          ),
          'confidence': 1.0,
          'reasons': <String>[],
          'image_inliers': null,
        },
      };
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    expect(find.text('Pikachu ex'), findsOneWidget);
    expect(find.textContaining('ピカチュウex · Drachenwandel · 132'), findsOneWidget);
  });

  testWidgets('Admin erzeugt Einladung und sieht den Code', (tester) async {
    final api = FakeApi(loggedIn: true, role: 'admin');
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Mehr')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Einladungen'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('create-invite')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'für Max');
    await tester.tap(find.text('Erzeugen'));
    await tester.pumpAndSettle();

    expect(api.calls, contains('invite:für Max'));
    expect(find.byKey(const Key('shown-code')), findsOneWidget);
    expect(find.text('ABCD-EFGH-JKLM'), findsOneWidget);
  });

  testWidgets('Nutzer ohne Admin-Rechte sehen keinen Admin-Bereich; Abmelden', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Mehr')));
    await tester.pumpAndSettle();
    expect(find.text('Einladungen'), findsNothing);

    await tester.tap(find.text('Abmelden'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('logout'));
    expect(find.text('Anmelden'), findsOneWidget);
  });

  testWidgets('Slab-Scan zeigt den Median gespeicherter PSA-10-Verkäufe', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..scanResult = scanJson(grading: {'company': 'PSA', 'grade': '10'});
    (api.pricesJson['offers']! as List<Object?>).add({
      'source': 'ebay_sold',
      'variant': 'graded:PSA 10',
      'condition': null,
      'currency': 'EUR',
      'kind': 'external',
      'updated_at': DateTime(2026, 10, 18).toIso8601String(),
      'url': 'https://www.ebay.de/sch/i.html?_nkw=x',
      'metrics': {'median': '650.00', 'low': '600.00', 'high': '700.00', 'count': '5'},
    });
    await pumpApp(tester, api);

    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    expect(find.text('650,00\u00a0€'), findsOneWidget);
    expect(find.textContaining('Median aus 5 eBay-Verkäufen'), findsOneWidget);
  });

  testWidgets('Scan einer Rohkarte: Knöpfe zum Preisholen bei Cardmarket und eBay', (tester) async {
    await pumpApp(tester, FakeApi(loggedIn: true));

    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('scan-price')), findsOneWidget);
    expect(find.text('Cardmarket DE ab NM'), findsOneWidget);
    expect(find.byKey(const Key('scan-ebay')), findsOneWidget);
  });

  testWidgets('Scan: „Ist ein Slab?“ – Firma Beckett, Note 10, Black Label', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('scan-slab')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-slab')));
    await tester.pumpAndSettle();
    expect(find.text('Slab (gegradet)'), findsOneWidget);

    await tester.tap(find.byKey(const Key('item-company')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Beckett (BGS)').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('item-black-label')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('item-save')));
    await tester.tap(find.byKey(const Key('item-save')));
    await tester.pumpAndSettle();

    expect(api.lastItemBody?['grading_company'], 'BGS');
    expect(api.lastItemBody?['grade'], '10 BL');
    expect(api.lastItemBody?.containsKey('condition'), isFalse);
    expect(api.calls, contains('confirm:scan1:c1'));
  });
}

void moversTests() {
  testWidgets('Startseite zeigt Gewinner und Verlierer der Woche', (tester) async {
    Json mover(String change, String pct) => {
      'card': cardJson(),
      'variant': 'normal',
      'quantity': 2,
      'before': '10.00',
      'now': '15.00',
      'change': change,
      'change_pct': pct,
      'since': '2026-10-14T00:00:00Z',
    };
    final api = FakeApi(loggedIn: true)
      ..moversJson = {
        'days': 7,
        'gainers': [mover('10.00', '50.0')],
        'losers': [mover('-2.00', '-10.0')],
      };
    await pumpApp(tester, api);

    final section = find.byKey(const Key('movers'));
    await tester.scrollUntilVisible(section, 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Bewegungen (7 Tage)'), findsOneWidget);
    expect(find.text('+10,00\u00a0€'), findsOneWidget);
    expect(find.text('+50,0 %'), findsOneWidget);
    expect(find.text('−2,00\u00a0€'), findsOneWidget);
    expect(find.text('-10,0 %'), findsOneWidget);
  });
}

void variantTests() {
  testWidgets('Holo-Karte ohne Reverse: Fassungen gezeigt, keine Auswahl beim Hinzufügen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)
      ..cardVariants = {'normal': false, 'reverse': false, 'holo': true, 'firstEdition': false}
      ..cardIllustrator = 'Ryota Murayama';
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('card-variants')), findsOneWidget);
    expect(find.text('Holo'), findsWidgets);
    expect(find.text('Illustration: Ryota Murayama'), findsOneWidget);

    await tester.tap(find.byKey(const Key('add-to-collection')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Weitere Angaben'));
    await tester.pumpAndSettle();
    expect(find.text('Kaufpreis (Stück)'), findsOneWidget); // aufgeklappt
    expect(find.byKey(const Key('item-variant')), findsNothing); // gibt nur Holo
    await tester.tap(find.byKey(const Key('item-save')));
    await tester.pumpAndSettle();
    expect(api.lastItemBody?['variant'], 'normal');
  });
}

void psaTests() {
  testWidgets('PSA-Slab: Bestätigung von PSA und Hinweis bei anderer Nummer', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..scanResult = scanJson(
        grading: {'company': 'PSA', 'grade': '10', 'cert': '73270136'},
        psa: {
          'cert': '73270136',
          'year': '2022',
          'brand': 'POKEMON JAPANESE SWORD & SHIELD PARADIGM TRIGGER',
          'card_number': '110',
          'subject': 'FA/LUGIA V',
          'grade_description': 'GEM MT 10',
          'grade': '10',
          'population': 1234,
          'population_higher': 0,
        },
        psaWarning: 'Laut PSA ist es Nr. 110 (FA/LUGIA V) – bitte die Karte prüfen.',
      );
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-gallery')));
    await tester.pumpAndSettle();

    expect(find.text('Slab: PSA 10'), findsOneWidget);
    expect(
      find.text('✓ Von PSA bestätigt · FA/LUGIA V #110 · Population 1234 (höher: 0)'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('scan-psa-warning')), findsOneWidget);
  });
}

void profitTests() {
  testWidgets('Startseite: investiert, Gewinn in € und %, bester und schlechtester Kauf', (
    tester,
  ) async {
    Json bought(String id, String total, String cost, String profit) {
      final json = itemJson(id: id, total: total);
      (json['value'] as Json)
        ..['cost'] = cost
        ..['profit'] = profit;
      return json..['purchase_price'] = cost;
    }

    final api = FakeApi(loggedIn: true)
      ..summaryOverride = {
        ...summaryJson(top: itemJson()),
        'invested': '275.00',
        'profit': '50.00',
        'profit_cost': '250.00',
        'profit_percent': '20.0',
        'profit_positions': 2,
        'best_profit': bought('i2', '200.00', '120.00', '80.00'),
        'worst_profit': bought('i3', '100.00', '130.00', '-30.00'),
      };
    await pumpApp(tester, api);

    expect(find.text('Investiert 275,00\u00a0€ · Gewinn +50,00\u00a0€ (+20,0 %)'), findsOneWidget);
    final section = find.byKey(const Key('profit-section'));
    await tester.scrollUntilVisible(section, 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('Seit dem Kauf'), findsOneWidget);
    expect(find.text('+80,00\u00a0€'), findsWidgets);
    expect(find.text('+66,7 %'), findsOneWidget);
    expect(find.text('−30,00\u00a0€'), findsWidgets);
    expect(find.text('−23,1 %'), findsOneWidget);
  });

  testWidgets('ohne Kaufpreise keine Gewinnzeile', (tester) async {
    await pumpApp(tester, FakeApi(loggedIn: true));
    expect(find.byKey(const Key('hero-profit')), findsNothing);
    expect(find.byKey(const Key('profit-section')), findsNothing);
  });

  testWidgets('Scan: nach dem Hinzufügen Kaufpreis eintragen → Gewinn', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-camera')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();

    final field = find.byKey(const Key('scan-purchase'));
    await tester.ensureVisible(field);
    await tester.enterText(field, '1.500,00');
    await tester.tap(find.byKey(const Key('scan-purchase-save')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('updateItem:i1'));
    expect(api.lastItemChanges, {'purchase_price': '1500.00'});
    expect(find.text('Seit dem Kauf: +305,90\u00a0€'), findsOneWidget);
  });

  testWidgets('Scan: ungültiger Kaufpreis wird nicht gespeichert', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-camera')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();

    final field = find.byKey(const Key('scan-purchase'));
    await tester.ensureVisible(field);
    await tester.enterText(field, 'viel');
    await tester.tap(find.byKey(const Key('scan-purchase-save')));
    await tester.pumpAndSettle();
    expect(api.calls.where((c) => c.startsWith('updateItem')), isEmpty);
  });
}
