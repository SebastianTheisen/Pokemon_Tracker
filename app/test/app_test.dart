import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
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
    await tester.tap(find.byKey(const Key('scan-other')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Umbreon VMAX'));
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
}
