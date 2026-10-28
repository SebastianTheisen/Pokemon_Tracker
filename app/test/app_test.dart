import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/app.dart';
import 'package:kartenkiste/core/camera/live_camera.dart';
import 'package:kartenkiste/core/device/device.dart';
import 'package:kartenkiste/core/prefs.dart';
import 'package:kartenkiste/core/push/push_bridge.dart';
import 'package:kartenkiste/core/theme.dart';
import 'package:kartenkiste/features/scan/scan_screens.dart' show binderPollInterval;
import 'package:kartenkiste/router.dart';
import 'package:kartenkiste/widgets/slab_frame.dart';
import 'package:kartenkiste/widgets/value_chart.dart';
import 'package:kartenkiste/models/json.dart';

import 'fakes.dart';

void main() {
  moversTests();
  profitTests();
  selectionTests();
  filterTests();
  alertTests();
  setTests();
  friendTests();
  ownedTests();
  cardPageTests();
  reportTests();
  usabilityTests();
  variantTests();
  psaTests();
  gameTests();
  slabTests();

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
    // Kartenseite aufgeräumt: Quellen und andere Zustände sind aufklappbar.
    final mainList = find.byType(Scrollable).first;
    final lowest = find.textContaining('Tiefster Preis: 1.790,00\u00a0€'); // Verlauf ist offen
    await tester.scrollUntilVisible(lowest, 300, scrollable: mainList);
    expect(lowest, findsOneWidget);

    final conditionsFold = find.byKey(const Key('fold-conditions'));
    await tester.scrollUntilVisible(conditionsFold, -300, scrollable: mainList);
    await tester.tap(conditionsFold);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('condition-EX')));
    await tester.tap(find.byKey(const Key('condition-EX')));
    await tester.pumpAndSettle();
    expect(find.text('1.535,02\u00a0€'), findsWidgets);
    expect(find.textContaining('ab EX'), findsOneWidget); // Cardmarket-Link folgt dem Zustand
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
      'folder_id': 'f1', // einziger Ordner
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
    // Liste ist länger als der Bildschirm: bis über die untere Leiste scrollen.
    await tester.scrollUntilVisible(find.text('Abmelden'), 200);
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

    await tester.scrollUntilVisible(find.text('Abmelden'), 200);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
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
    expect(find.text('Bester und schlechtester Kauf'), findsOneWidget);
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

void selectionTests() {
  Future<void> openCollection(WidgetTester tester, FakeApi api) async {
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
  }

  testWidgets('Mehrfachauswahl: langer Druck, alle auswählen, verschieben', (tester) async {
    final api = FakeApi(loggedIn: true);
    await openCollection(tester, api);

    await tester.longPress(find.text('Nachtara VMAX').first);
    await tester.pumpAndSettle();
    expect(find.text('1 ausgewählt'), findsOneWidget);
    expect(find.byKey(const Key('add-sealed')), findsNothing);

    await tester.tap(find.byKey(const Key('select-all')));
    await tester.pumpAndSettle();
    expect(find.text('2 ausgewählt'), findsOneWidget);

    await tester.tap(find.byKey(const Key('bulk-move')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('pick-folder-f1')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('bulk:move:i1,i2:f1'));
    expect(find.text('2 Positionen verschoben'), findsOneWidget);
    expect(find.byKey(const Key('selection-count')), findsNothing);
  });

  testWidgets('Mehrfachauswahl: abwählen und entfernen mit Rückfrage', (tester) async {
    final api = FakeApi(loggedIn: true);
    await openCollection(tester, api);

    await tester.longPress(find.text('Nachtara VMAX').first); // erste Position (i1)
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('select-i2')));
    await tester.pumpAndSettle();
    expect(find.text('2 ausgewählt'), findsOneWidget);
    await tester.tap(find.byKey(const Key('select-i2')));
    await tester.pumpAndSettle();
    expect(find.text('1 ausgewählt'), findsOneWidget);

    await tester.tap(find.byKey(const Key('bulk-delete')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('bulk-delete-confirm')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('bulk:delete:i1:null'));
  });
}

void filterTests() {
  testWidgets('Filter: Sprache, Zustand, Wertspanne, Kaufpreis – Abzeichen und Zurücksetzen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('collection-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('filter-language-ja')));
    await tester.tap(find.byKey(const Key('filter-condition-NM')));
    await tester.enterText(find.byKey(const Key('filter-min')), '10');
    await tester.enterText(find.byKey(const Key('filter-max')), '1.000,50');
    await tester.ensureVisible(find.byKey(const Key('filter-purchase-true')));
    await tester.tap(find.byKey(const Key('filter-purchase-true')));
    await tester.ensureVisible(find.byKey(const Key('filter-apply')));
    await tester.tap(find.byKey(const Key('filter-apply')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('items:ja|NM|10|1000.50|true'));
    expect(find.text('5'), findsOneWidget); // Abzeichen: 5 aktive Filter

    final before = api.calls.where((c) => c == 'items:-|-|-|-|-').length;
    await tester.tap(find.byKey(const Key('collection-filter')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('filter-reset')));
    await tester.tap(find.byKey(const Key('filter-reset')));
    await tester.pumpAndSettle();
    // Die ungefilterte Liste kommt aus dem Zwischenspeicher – kein zweiter Abruf nötig.
    expect(find.text('5'), findsNothing);
    expect(api.calls.where((c) => c == 'items:-|-|-|-|-').length, before);
  });

  testWidgets('Filter: „von“ größer als „bis“ wird abgelehnt', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('collection-filter')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('filter-min')), '100');
    await tester.enterText(find.byKey(const Key('filter-max')), '5');
    await tester.ensureVisible(find.byKey(const Key('filter-apply')));
    await tester.tap(find.byKey(const Key('filter-apply')));
    await tester.pumpAndSettle();
    expect(find.text('„von“ ist größer als „bis“.'), findsOneWidget);
    expect(api.calls.where((c) => c.startsWith('items:') && c.contains('100')), isEmpty);
  });

  Future<void> searchNachtara(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('search-field')), 'nachtara');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
  }

  testWidgets('Suche: „+“ fügt 1× NM hinzu, Rückgängig entfernt wieder', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await searchNachtara(tester);

    await tester.tap(find.byKey(const Key('quick-add-c1')));
    await tester.pumpAndSettle();
    expect(api.lastItemBody, {'card_id': 'c1', 'quantity': 1, 'condition': 'NM'});
    expect(find.text('Nachtara VMAX hinzugefügt'), findsOneWidget);

    await tester.tap(find.text('Rückgängig'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('deleteItem:i1'));
  });

  testWidgets('Hinweis mit „Rückgängig“ verschwindet von selbst', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await searchNachtara(tester);

    await tester.tap(find.byKey(const Key('quick-add-c1')));
    await tester.pumpAndSettle();
    expect(find.text('Nachtara VMAX hinzugefügt'), findsOneWidget);
    await tester.pump(const Duration(seconds: 7));
    await tester.pumpAndSettle();
    expect(find.text('Nachtara VMAX hinzugefügt'), findsNothing);
    expect(api.calls, isNot(contains('deleteItem:i1')));
  });

  testWidgets('Suche: langer Druck auf „+“ → Schnellmenü (Merkliste)', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await searchNachtara(tester);

    await tester.longPress(find.byKey(const Key('quick-add-c1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('quick-details')), findsOneWidget);
    await tester.tap(find.byKey(const Key('quick-wishlist')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('wishlist:c1'));
    expect(find.text('Auf der Merkliste'), findsOneWidget);
  });
}

void alertTests() {
  Future<void> openCard(WidgetTester tester) async {
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
  }

  testWidgets('Preisalarm auf der Kartenseite: Vorschlag −10 %, steigt auf, Zustand', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await openCard(tester);

    await tester.tap(find.byKey(const Key('card-alert')));
    await tester.pumpAndSettle();
    expect(find.text('Aktuell: 1.805,90\u00a0€'), findsOneWidget);
    expect(find.widgetWithText(TextField, '1625,31'), findsOneWidget); // 90 % als Vorschlag

    await tester.tap(find.text('Steigt auf'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, '1986,49'), findsOneWidget); // 110 %
    await tester.enterText(find.byKey(const Key('alert-target')), '2.000');
    await tester.tap(find.byKey(const Key('alert-save')));
    await tester.pumpAndSettle();

    expect(api.lastAlertBody, {
      'card_id': 'c1',
      'product_id': null,
      'direction': 'above',
      'target': '2000', // „2.000“ = zweitausend
      'variant': 'normal',
      'condition': 'NM',
    });
    expect(find.text('Preisalarm angelegt. Mitteilungen sind noch aus.'), findsOneWidget);
    expect(find.text('Einschalten'), findsOneWidget); // noch kein Gerät angemeldet
  });

  testWidgets('Preisalarme: Mitteilungen einschalten, Probe, Liste', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..alertsJson = [
        alertJson(),
        alertJson(id: 'a2', active: false, triggeredAt: '2026-10-24T12:30:00Z'),
      ];
    final push = FakePushBridge();
    await pumpApp(tester, api, push: push);
    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-alerts')));
    await tester.pumpAndSettle();

    expect(find.textContaining('Aus. Einschalten'), findsOneWidget);
    await tester.tap(find.byKey(const Key('push-enable')));
    await tester.pumpAndSettle();
    expect(push.calls, ['subscribe:BKey']);
    expect(api.calls, contains('pushSubscribe:https://web.push.apple.com/abc'));
    expect(find.textContaining('An – Preisalarme'), findsOneWidget);

    await tester.tap(find.byKey(const Key('push-test')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('pushTest'));
    expect(find.text('Probe gesendet – kommt gleich an.'), findsOneWidget);

    expect(find.textContaining('▼ bis 1.500,00\u00a0€'), findsNWidgets(2));
    expect(find.textContaining('Ausgelöst 24.10.2026'), findsOneWidget);

    await tester.tap(find.byKey(const Key('alert-menu-a2')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Wieder scharf'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('updateAlert:a2:null:null:true'));
  });

  testWidgets('iPhone im Browser: Hinweis „Zum Home-Bildschirm“ statt Einschalten', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api, push: FakePushBridge(state: PushStatus.install));
    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-alerts')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Zum Home-Bildschirm'), findsOneWidget);
    expect(find.byKey(const Key('push-enable')), findsNothing);
  });

  testWidgets('ohne Server-Schlüssel: Hinweis, kein Einschalten', (tester) async {
    final api = FakeApi(loggedIn: true)..pushPublicKey = null;
    await pumpApp(tester, api);
    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-alerts')));
    await tester.pumpAndSettle();
    expect(find.textContaining('noch nicht eingerichtet'), findsOneWidget);
    expect(find.byKey(const Key('push-enable')), findsNothing);
  });
}

void setTests() {
  Future<void> openSet(WidgetTester tester) async {
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Sets'));
    await tester.pumpAndSettle();
    expect(find.textContaining('2 / 4 Karten · 50 % · Master 3 / 7'), findsOneWidget);
    await tester.tap(find.byKey(const Key('set-s1')));
    await tester.pumpAndSettle();
  }

  testWidgets('Set-Seite: Set und Master, Fehlt-Filter, Master zählt Reverse', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await openSet(tester);

    expect(api.calls, contains('setProgress:s1'));
    expect(find.text('2 / 4 · 50 %'), findsOneWidget);
    expect(find.text('3 / 7 · 43 %'), findsOneWidget);
    expect(find.textContaining('Fehlende Karten ≈ 5,00'), findsOneWidget);

    await tester.tap(find.byKey(const Key('show-missing')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('set-card-k3')), findsOneWidget);
    expect(find.byKey(const Key('set-card-k4')), findsOneWidget);
    expect(find.byKey(const Key('set-card-k2')), findsNothing); // Set: Karte 2 vorhanden

    await tester.tap(find.byKey(const Key('master-toggle')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('set-card-k2')), findsOneWidget); // Reverse fehlt
    expect(find.byKey(const Key('set-card-k1')), findsNothing); // beides vorhanden
    expect(find.textContaining('Fehlende Karten ≈ 7,50'), findsOneWidget);
  });

  testWidgets('Set-Analyse: Setwert, Veränderung, Stabilität, Gewinner und Verlierer', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await openSet(tester);
    await tester.tap(find.byKey(const Key('set-analytics')));
    await tester.pumpAndSettle();
    expect(find.text('165,50\u00a0€'), findsOneWidget);
    expect(find.text('+3,3 % gegenüber Ø 30 Tage'), findsOneWidget);
    expect(find.text('Master-Set inkl. Reverse Holo: 185,50\u00a0€'), findsOneWidget);
    expect(find.text('Preise normal (± 8 %)'), findsOneWidget);
    expect(find.text('Größte Gewinner (≈ 30 Tage)'), findsOneWidget);
    expect(find.text('+10,0 %'), findsWidgets);
    expect(find.text('−10,0 %'), findsOneWidget);
  });

  testWidgets('Set-Seite: fehlende (noch nicht gemerkte) auf die Merkliste', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await openSet(tester);

    await tester.tap(find.byKey(const Key('wish-missing')));
    await tester.pumpAndSettle();
    expect(find.text('1 Karte auf die Merkliste?'), findsOneWidget); // k3 ist schon gemerkt
    await tester.tap(find.byKey(const Key('wish-missing-confirm')));
    await tester.pumpAndSettle();
    expect(api.lastWishedIds, ['k4']);
    expect(find.text('1 Karte auf die Merkliste gesetzt.'), findsOneWidget);
  });
}

void friendTests() {
  testWidgets('Ordner für Freunde freigeben', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('collection-more')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ordner verwalten'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('share-f1')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('share:f1:true'));
    expect(find.textContaining('ist für Freunde sichtbar'), findsOneWidget);
  });

  testWidgets('Showcase eines Freundes → Karte zum Tausch → eigene Karte geben → speichern', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.text('Mehr').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-friends')));
    await tester.pumpAndSettle();
    expect(find.textContaining('2 Stück · 1 Ordner · 1.855,90'), findsOneWidget);

    await tester.tap(find.byKey(const Key('friend-u2')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('showcase:u2'));
    await tester.tap(find.byKey(const Key('showcase-item-m1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('showcase-trade')));
    await tester.pumpAndSettle();
    expect(find.text('Tausch (1)'), findsOneWidget);

    await tester.tap(find.byKey(const Key('showcase-open-trade')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('evaluate:get:m1:1'));
    expect(find.text('+50,00\u00a0€ für dich · du bekommst mehr'), findsOneWidget);

    await tester.tap(find.byKey(const Key('trade-add-mine')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('trade-pick-i2')));
    await tester.pumpAndSettle();
    expect(find.text('+20,00\u00a0€ für dich · du bekommst mehr'), findsOneWidget); // 50 − 30

    await tester.tap(find.byKey(const Key('trade-save')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('trade-partner')), 'Max');
    await tester.tap(find.byKey(const Key('trade-save-confirm')));
    await tester.pumpAndSettle();
    expect(api.lastTradePartner, 'Max');
    expect(api.lastTradeLines!.map((l) => '${l.side}:${l.itemId}').toList(), ['get:m1', 'give:i2']);
    expect(find.byKey(const Key('trade-summary')), findsNothing); // Entwurf geleert
  });

  testWidgets('Sammlung → Kartenseite → eigene Zeile → „Zum Tausch geben“', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..ownedJson = [
        {
          'card_id': 'c1',
          'folder_id': 'f1',
          'folder_name': 'Sammlung',
          'variant': 'normal',
          'grading_company': null,
          'grade': null,
          'quantity': 1,
          'item_ids': ['i1'],
        },
      ];
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
    // Antippen öffnet die Kartenseite (wie Collectr), nicht mehr ein Menü.
    await tester.tap(find.text('Nachtara VMAX').first);
    await tester.pumpAndSettle();
    expect(find.text('✓ In deiner Sammlung: 1×'), findsOneWidget);
    await tester.tap(find.byKey(const Key('owned-edit-f1-null')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('item:i1'));
    expect(find.text('Nachtara VMAX ansehen'), findsNothing); // wir sind schon auf der Karte
    await tester.tap(find.byKey(const Key('item-trade')));
    await tester.pumpAndSettle();
    expect(find.textContaining('→ „Ich gebe“'), findsOneWidget);
    await tester.tap(find.text('Zum Tausch'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('evaluate:give:i1:1'));
    expect(find.text('−30,00\u00a0€ für dich · du gibst mehr'), findsOneWidget);
  });
}

void ownedTests() {
  Json owned(String folderId, String folderName, int quantity, {String variant = 'normal'}) => {
    'card_id': 'c1',
    'folder_id': folderId,
    'folder_name': folderName,
    'variant': variant,
    'grading_company': null,
    'grade': null,
    'quantity': quantity,
  };

  testWidgets('Suche und Kartenseite zeigen „schon in deiner Sammlung“ mit Ordnern', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)
      ..ownedJson = [owned('f1', 'Sammlung', 2), owned('f2', 'Binder', 1, variant: 'reverse')];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('search-field')), 'nachtara');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('✓ In deiner Sammlung: 3× · Sammlung, Binder'), findsOneWidget);

    await tester.tap(find.text('Nachtara VMAX').first);
    await tester.pumpAndSettle();
    expect(find.text('✓ In deiner Sammlung: 3×'), findsOneWidget);
    expect(find.text('Binder · Reverse Holo'), findsOneWidget);
  });

  testWidgets('Kartenseite: Slab zählt mit Notenpreis; ohne Preis klarer Hinweis + eBay', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)
      ..ownedJson = [
        {
          ...owned('f1', 'Sammlung', 1),
          'grading_company': 'PSA',
          'grade': '10',
          'unit_value': null,
          'value_kind': 'none',
        },
        {
          ...owned('f2', 'Binder', 1),
          'grading_company': 'PSA',
          'grade': '9',
          'unit_value': '1200.00',
          'value_kind': 'external',
          'value_source': 'pricecharting',
          'value_basis': 'PriceCharting Note 9 (US-Preis umgerechnet)',
        },
      ];
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();

    expect(find.text('Noch kein Preis für PSA 10 – wird gesucht'), findsOneWidget);
    expect(find.text('1.200,00\u00a0€'), findsOneWidget);
    expect(
      find.text('Wert in der Sammlung · PriceCharting Note 9 (US-Preis umgerechnet)'),
      findsOneWidget,
    );
    expect(find.text('Preis für PSA 10 aus eBay-Verkäufen holen'), findsOneWidget);
    expect(find.text('Preis ungegradet (Rohkarte)'), findsOneWidget);
  });

  testWidgets('Scan: Ordner wählen, Wahl gilt auch für das nächste Hinzufügen', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..foldersJson = [
        {'id': 'f1', 'name': 'Sammlung', 'sort_order': 0, 'created_at': '2026-10-17T00:00:00Z'},
        {'id': 'f2', 'name': 'Binder', 'sort_order': 1, 'created_at': '2026-10-17T00:00:00Z'},
      ];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-camera')));
    await tester.pumpAndSettle();

    expect(find.text('Ordner: Sammlung ▾'), findsOneWidget);
    await tester.tap(find.byKey(const Key('folder-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('folder-option-f2')).last);
    await tester.pumpAndSettle();
    expect(find.text('Ordner: Binder ▾'), findsOneWidget);

    await tester.tap(find.byKey(const Key('scan-add')));
    await tester.pumpAndSettle();
    expect(api.lastItemBody?['folder_id'], 'f2');

    await tester.tap(find.byKey(const Key('scan-next')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scan-camera')));
    await tester.pumpAndSettle();
    expect(find.text('Ordner: Binder ▾'), findsOneWidget); // gemerkt
  });
}

void cardPageTests() {
  Future<void> openCard(WidgetTester tester) async {
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
  }

  Json offer(String source, String variant, Map<String, String> metrics) => {
    'source': source,
    'variant': variant,
    'condition': null,
    'currency': 'EUR',
    'kind': 'verified',
    'updated_at': '2026-10-24T10:00:00Z',
    'url': null,
    'metrics': metrics,
  };

  testWidgets('Noten vergleichen: Roh, PriceCharting-Noten, eBay-Median, Faktor; als Slab', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    api.pricesJson['offers'] = [
      ...api.pricesJson['offers'] as List,
      offer('pricecharting', 'graded', {'grade_9': '3611.80', 'psa_10': '9029.50'}),
      offer('ebay_sold', 'graded:PSA 10', {'median': '8500.00', 'count': '4'}),
    ];
    await pumpApp(tester, api);
    await openCard(tester);

    final section = find.byKey(const Key('grade-comparison'));
    await tester.scrollUntilVisible(section, 300, scrollable: find.byType(Scrollable).first);
    expect(find.text('Noten vergleichen'), findsOneWidget);
    expect(find.text('bis 8.500,00\u00a0€'), findsOneWidget); // Zusammenfassung, zugeklappt
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('fold-grades')));
    await tester.pumpAndSettle();
    expect(find.text('Roh (Near Mint)'), findsOneWidget);
    expect(find.text('PSA 9'), findsOneWidget);
    expect(find.text('×2,0'), findsOneWidget); // 3611,80 / 1805,90
    expect(find.text('8.500,00\u00a0€'), findsOneWidget); // eBay schlägt PriceCharting
    expect(find.text('eBay (4 Verkäufe)'), findsOneWidget);

    await tester.ensureVisible(find.byKey(const Key('grade-PSA 10')));
    // aus dem Bereich der unteren Knopfleiste (Merkliste/Sammlung) heraus scrollen
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -250));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('grade-PSA 10')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('item-save')), findsOneWidget); // Formular mit Slab offen
  });

  testWidgets('Preisverlauf: Zeitraum wählen, Veränderung im Zeitraum', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await openCard(tester);
    final chips = find.byKey(const Key('range-1J'));
    await tester.scrollUntilVisible(chips, 300, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(api.calls, contains('history:90'));
    expect(find.textContaining('+15,90\u00a0€ (+0,9 %) in 3 Monaten'), findsOneWidget);
    await tester.tap(chips);
    await tester.pumpAndSettle();
    expect(api.calls, contains('history:365'));
    expect(find.textContaining('im letzten Jahr'), findsOneWidget);
  });
}

void reportTests() {
  testWidgets('Suche ohne Treffer: dem Admin melden (Suchbegriff vorbelegt)', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('search-field')), 'Mega Lucario');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('search-report')));
    await tester.pumpAndSettle();
    expect(
      tester.widget<TextField>(find.byKey(const Key('report-text'))).controller!.text,
      'Mega Lucario',
    );
    await tester.tap(find.byKey(const Key('report-send')));
    await tester.pumpAndSettle();
    expect(api.lastReport, {
      'kind': 'card',
      'text': 'Mega Lucario',
      'context': 'Suche: Mega Lucario',
    });
    expect(find.text('Danke! Die Meldung ist beim Admin angekommen.'), findsOneWidget);
  });

  testWidgets('Admin: Meldungen ansehen und abhaken', (tester) async {
    final api = FakeApi(loggedIn: true, role: 'admin');
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Mehr')));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Abmelden'), 200);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-admin-reports')));
    await tester.pumpAndSettle();
    expect(find.text('ETB fehlt'), findsOneWidget);
    expect(find.textContaining('Produkt fehlt · Max'), findsOneWidget);
    await tester.tap(find.byKey(const Key('report-r1')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('reportDone:r1:true'));
  });
}

void usabilityTests() {
  Json point(String day, String value, {bool live = false}) => {
    'date': day,
    'total_value': value,
    'estimated_value': '0.00',
    'is_live': live,
  };

  testWidgets('Startseite „Heute“: seit gestern und frisch ausgelöster Preisalarm', (tester) async {
    final today = DateTime.now().toIso8601String();
    final api = FakeApi(loggedIn: true)
      ..historyPoints = [point('2026-10-23', '4850.00'), point('2026-10-24', '4894.67', live: true)]
      ..alertsJson = [alertJson(active: false, triggeredAt: today)];
    await pumpApp(tester, api);
    expect(find.text('Heute'), findsOneWidget);
    expect(find.textContaining('+44,67'), findsOneWidget);
    expect(find.textContaining('Preisalarm: 1.490,00'), findsOneWidget);
    await tester.tap(find.byKey(const Key('today-alert-a1')));
    await tester.pumpAndSettle();
    expect(find.text('Preisalarme'), findsWidgets);
  });

  testWidgets('Startseite ohne Neuigkeiten: keine „Heute“-Kachel; Schnellzugriff Sets', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    expect(find.byKey(const Key('today-card')), findsNothing);
    await tester.tap(find.byKey(const Key('quick-sets')));
    await tester.pumpAndSettle();
    expect(find.text('Sets'), findsWidgets);
    expect(find.textContaining('2 / 4 Karten'), findsOneWidget);
  });

  testWidgets('Mehr: Gruppen, Zähler ausgelöster Alarme, Hilfe, Export', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..alertsJson = [
        alertJson(),
        alertJson(id: 'a2', active: false, triggeredAt: '2026-10-24T12:30:00Z'),
      ];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Mehr')));
    await tester.pumpAndSettle();
    for (final group in ['SAMMLUNG', 'FREUNDE']) {
      expect(find.text(group), findsOneWidget);
    }
    expect(find.text('1 aktiv · 1 ausgelöst'), findsOneWidget);

    await tester.tap(find.byKey(const Key('more-export')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('export'));
    expect(find.text('Export ist nur in der Web-App möglich.'), findsOneWidget); // Testumgebung

    await tester.scrollUntilVisible(find.text('KONTO'), 100);
    await tester.ensureVisible(find.byKey(const Key('more-help')));
    await tester.pumpAndSettle();
    expect(find.text('HILFE'), findsOneWidget);
    await tester.tap(find.byKey(const Key('more-help')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Preisalarme'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Glocke'), findsOneWidget);
  });

  testWidgets('Preisalarme: Wochenrückblick abschalten', (tester) async {
    final api = FakeApi(loggedIn: true);
    final push = FakePushBridge(state: PushStatus.granted)
      ..subscribedEndpoint = 'https://web.push.apple.com/abc';
    await pumpApp(tester, api, push: push);
    await tester.tap(find.byKey(const Key('tab-Mehr')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('more-alerts')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('push-weekly')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('weekly:false'));
  });

  testWidgets('Unbekannte Adresse: freundliche Seite mit Weg zurück zur Übersicht', (tester) async {
    await pumpApp(tester, FakeApi(loggedIn: true));
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);

    router.go('/gibt-es-nicht');
    await tester.pumpAndSettle();
    expect(find.text('Seite nicht gefunden'), findsOneWidget);

    await tester.tap(find.byKey(const Key('error-home')));
    await tester.pumpAndSettle();
    expect(find.text('Seite nicht gefunden'), findsNothing);

    router.go('/');
    await tester.pumpAndSettle();
    expect(router.state.matchedLocation, '/home');
  });

  testWidgets('Merkliste: Bild, Preis, Veränderung in 7 Tagen und Summe', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..wishlistJson = [
        {
          'id': 'w1',
          'created_at': '2026-10-20T10:00:00Z',
          'card': cardJson(),
          'product': null,
          'nm_value': '125.00',
          'nm_value_kind': 'external',
          'change': '25.00',
          'change_pct': '25.0',
          'change_days': 7,
        },
        {
          'id': 'w2',
          'created_at': '2026-10-21T10:00:00Z',
          'card': null,
          'product': {'id': 'p1', 'kind': 'booster', 'language': 'de', 'name': 'Booster 151'},
          'nm_value': null,
          'nm_value_kind': null,
        },
      ];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Merkliste')));
    await tester.pumpAndSettle();

    expect(find.text('2 Einträge · zusammen 125,00\u00a0€'), findsOneWidget);
    expect(find.text('+25,0 % in 7 Tagen'), findsOneWidget);
    expect(find.text('noch kein Preis'), findsOneWidget);
    expect(find.text('Booster 151'), findsOneWidget);
  });

  testWidgets('Sammlung: Kurve erst auf Tipp, Auswahl über das Menü', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    expect(find.text('Verlauf'), findsOneWidget);
    await tester.tap(find.byKey(const Key('toggle-curve')));
    await tester.pumpAndSettle();
    expect(find.text('Zuklappen'), findsOneWidget);

    await tester.tap(find.byKey(const Key('collection-more')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('collection-select')));
    await tester.pumpAndSettle();
    expect(find.text('0 ausgewählt'), findsOneWidget);
    await tester.tap(find.text('Nachtara VMAX').first);
    await tester.pumpAndSettle();
    expect(find.text('1 ausgewählt'), findsOneWidget); // im Auswahlmodus kein Seitenwechsel
    await tester.tap(find.byTooltip('Auswahl beenden'));
    await tester.pumpAndSettle();
    expect(find.text('Sammlung'), findsWidgets);
    expect(find.byKey(const Key('selection-count')), findsNothing);
  });

  testWidgets('Erster Start: Anleitung mit drei Seiten, danach nie wieder', (tester) async {
    final prefs = MemoryPrefsStore();
    await pumpApp(tester, FakeApi(loggedIn: true), prefs: prefs);
    expect(find.text('Karte scannen'), findsWidgets);
    await tester.tap(find.byKey(const Key('onboarding-next')));
    await tester.pumpAndSettle();
    expect(find.text('Deine Sammlung'), findsOneWidget);
    await tester.tap(find.byKey(const Key('onboarding-next')));
    await tester.pumpAndSettle();
    expect(find.text('Los geht’s'), findsOneWidget);
    await tester.tap(find.byKey(const Key('onboarding-next')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('onboarding-next')), findsNothing);
    expect(prefs.values['onboarded'], 'true');
  });

  testWidgets('Sammlung als Liste: Umschalter merkt sich die Wahl', (tester) async {
    final prefs = MemoryPrefsStore({'onboarded': 'true'});
    await pumpApp(tester, FakeApi(loggedIn: true), prefs: prefs);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('item-row-i1')), findsNothing);
    await tester.tap(find.byKey(const Key('collection-view')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('item-row-i1')), findsOneWidget);
    expect(prefs.values['list_view'], 'true');
    await tester.tap(find.byKey(const Key('item-row-i1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('condition-value')), findsOneWidget); // Kartenseite
  });

  testWidgets('Design: folgt dem Handy, fest dunkel oder hell wählbar und gespeichert', (
    tester,
  ) async {
    final prefs = MemoryPrefsStore({'onboarded': 'true'});
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    await pumpApp(tester, FakeApi(loggedIn: true), prefs: prefs);
    expect(AppColors.brightness, Brightness.light); // „Wie Handy“
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/settings'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Dunkel'));
    await tester.pumpAndSettle();
    expect(prefs.values['theme'], 'dark');
    expect(AppColors.brightness, Brightness.dark);
    expect(Theme.of(tester.element(find.text('Dunkel'))).brightness, Brightness.dark);

    await tester.tap(find.text('Hell'));
    await tester.pumpAndSettle();
    expect(prefs.values['theme'], 'light');
    expect(AppColors.brightness, Brightness.light);
  });

  testWidgets('Neuling: Willkommen, Erste Schritte, leere Sammlung mit klaren Knöpfen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)
      ..summaryOverride = {
        ...summaryJson(total: '0.00'),
        'items': 0,
        'positions': 0,
        'top_item': null,
      }
      ..itemsOverride = [];
    final prefs = MemoryPrefsStore({'onboarded': 'true'});
    await pumpApp(tester, api, prefs: prefs);

    expect(find.byKey(const Key('welcome-hero')), findsOneWidget);
    expect(find.byKey(const Key('total-value')), findsNothing); // kein „0,00 €“
    expect(find.byKey(const Key('first-steps')), findsOneWidget);
    expect(find.text('0 von 4'), findsOneWidget);
    expect(
      find.byKey(const Key('first-scan')),
      findsOneWidget,
    ); // nur der nächste Schritt hat Knöpfe
    expect(find.text('Zur Sammlung'), findsNothing);

    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('collection-filter')), findsNothing); // keine Leiste für nichts
    expect(find.byKey(const Key('empty-scan')), findsOneWidget);
    expect(find.byKey(const Key('empty-search')), findsOneWidget);

    await tester.tap(find.byKey(const Key('tab-Übersicht')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('first-steps-hide')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('first-steps')), findsNothing);
    expect(prefs.values['first_steps_hidden'], 'true');
  });

  testWidgets('Suche: Beispiele antippen, Preis direkt am Treffer', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('search-scan')), findsOneWidget);
    await tester.tap(find.byKey(const Key('search-example-Nachtara 215')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('search:Nachtara 215'));
    expect(find.text('≈ 1.805,90\u00a0€'), findsOneWidget);
  });

  testWidgets('Erste Schritte: Kaufpreis mit einem Tipp – öffnet die neueste Karte', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api, prefs: MemoryPrefsStore({'onboarded': 'true'}));
    expect(find.byKey(const Key('first-card-done')), findsOneWidget);
    await tester.tap(find.byKey(const Key('first-price-edit')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('item-save')), findsOneWidget); // Bearbeiten-Formular offen
  });

  testWidgets('Kartenseite: Vollbild mit Zoom/Holo, Blättern im Set per Pfeil und Wischen', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true)
      ..setCardsOverride = [
        FakeApi.progressCard('k1', '1'),
        FakeApi.progressCard('c1', '215'),
        FakeApi.progressCard('k3', '216'),
      ];
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    expect(find.text('2/3'), findsOneWidget);

    await tester.tap(find.byKey(const Key('card-image')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('viewer-card')), findsOneWidget);
    expect(find.byKey(const Key('viewer-tilt')), findsOneWidget);
    await tester.drag(find.byKey(const Key('viewer-card')), const Offset(80, 0)); // Glanz folgt
    await tester.pumpAndSettle();
    await tester.tap(find.byType(BackButton).last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('card-next')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('card:k3'));

    await tester.fling(find.byKey(const Key('card-header')), const Offset(400, 0), 1500); // zurück
    await tester.pumpAndSettle();
    expect(api.calls.where((c) => c == 'card:c1').length, greaterThanOrEqualTo(1));
  });

  testWidgets('Kurve zum Anfassen: Finger zeigt Tageswert, Loslassen zeigt wieder den Zeitraum', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    final chart = find.byType(ValueChart).first;
    await tester.scrollUntilVisible(chart, 300, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -150));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('range-change')), findsOneWidget);

    final gesture = await tester.startGesture(tester.getCenter(chart));
    await tester.pump();
    await gesture.moveBy(const Offset(40, 0));
    await tester.pump();
    expect(find.byKey(const Key('scrub-line')), findsOneWidget);
    expect(find.byKey(const Key('range-change')), findsNothing);
    await gesture.up();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('range-change')), findsOneWidget);
  });

  testWidgets('Sammlung: 7-Tage-Abzeichen am Bild, unter 1 % keins', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..itemsOverride = [
        {...itemJson(), 'trend_7d_pct': '4.2'},
        {...itemJson(id: 'i2', total: '50.00'), 'trend_7d_pct': '-0.4'},
      ];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    expect(find.text('▲ 4,2 %'), findsOneWidget);
    expect(find.textContaining('0,4 %'), findsNothing);
  });

  testWidgets('Entfernen ohne Nachfrage, „Rückgängig“ legt die Position wieder an', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..ownedJson = [
        {
          'card_id': 'c1',
          'folder_id': 'f1',
          'folder_name': 'Sammlung',
          'variant': 'normal',
          'grading_company': null,
          'grade': null,
          'quantity': 1,
          'item_ids': ['i1'],
        },
      ];
    await pumpApp(tester, api);
    await tester.tap(find.text('Sammlung').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nachtara VMAX').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('owned-edit-f1-null')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Entfernen'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('deleteItem:i1'));
    expect(find.text('„Nachtara VMAX“ entfernt'), findsOneWidget);

    await tester.tap(find.byKey(const Key('undo-delete')));
    await tester.pumpAndSettle();
    expect(api.lastItemBody?['card_id'], 'c1');
    expect(api.lastItemBody?['folder_id'], 'f1');
    expect(api.lastItemBody?['condition'], 'NM');
  });

  testWidgets('Set komplett: Glückwunsch und Konfetti (verschwindet von selbst)', (tester) async {
    final api = FakeApi(loggedIn: true)..setProgressExtra = {'cards_owned': 4};
    await pumpApp(tester, api);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/sets/s1'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Set komplett! 🎉'), findsOneWidget);
    expect(find.byKey(const Key('confetti')), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('confetti')), findsNothing);
  });

  testWidgets('Karte als Bild teilen: Vorschau, PNG geht ans Teilen-Menü', (tester) async {
    final device = FakeDevice();
    await pumpApp(tester, FakeApi(loggedIn: true), device: device);
    final topCard = find.text('Nachtara VMAX').first;
    await tester.ensureVisible(topCard);
    await tester.pumpAndSettle();
    await tester.tap(topCard);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('card-share')));
    await tester.pumpAndSettle();
    expect(find.text('Wert (Near Mint)'), findsOneWidget);
    await tester.runAsync(() async {
      await tester.tap(find.byKey(const Key('share-confirm')));
      for (var i = 0; i < 20 && device.shared.isEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        await tester.pump();
      }
    });
    await tester.pumpAndSettle();
    expect(device.shared.single.filename, 'kartenkiste-215.png');
    expect(device.shared.single.bytes, greaterThan(1000)); // echtes PNG
  });

  testWidgets('Installieren: Android-Knopf bzw. iPhone-Anleitung, ausblendbar', (tester) async {
    final android = FakeDevice(state: InstallState.prompt);
    await pumpApp(tester, FakeApi(loggedIn: true), device: android);
    expect(find.byKey(const Key('install-hint')), findsOneWidget);
    await tester.tap(find.byKey(const Key('install-action')));
    await tester.pumpAndSettle();
    expect(android.installs, 1);
    expect(find.byKey(const Key('install-hint')), findsNothing); // jetzt installiert
  });

  testWidgets('Installieren am iPhone: Anleitung in drei Schritten, Ausblenden bleibt', (
    tester,
  ) async {
    final prefs = MemoryPrefsStore({'onboarded': 'true', 'first_steps_hidden': 'true'});
    await pumpApp(
      tester,
      FakeApi(loggedIn: true),
      device: FakeDevice(state: InstallState.ios),
      prefs: prefs,
    );
    await tester.tap(find.byKey(const Key('install-action')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ios-install-guide')), findsOneWidget);
    Navigator.of(tester.element(find.byKey(const Key('ios-install-guide')))).pop();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('install-hide')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('install-hint')), findsNothing);
    expect(prefs.values['install_hint_hidden'], 'true');
  });

  testWidgets('Suche merkt sich Begriffe; Sets durchblättern nach Serie mit Filter', (
    tester,
  ) async {
    final prefs = MemoryPrefsStore({'onboarded': 'true', 'first_steps_hidden': 'true'});
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api, prefs: prefs);
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('search-field')), 'nachtara');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(prefs.values['recent_searches'], '["nachtara"]');

    await tester.enterText(find.byKey(const Key('search-field')), '');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('recent-nachtara')), findsOneWidget);

    await tester.tap(find.byKey(const Key('search-browse-sets')));
    await tester.pumpAndSettle();
    expect(api.calls, contains('catalogSets:de'));
    expect(find.text('Schwert & Schild'), findsOneWidget); // Serie als Überschrift
    await tester.enterText(find.byKey(const Key('set-filter')), '151');
    await tester.pumpAndSettle();
    expect(find.text('Drachenwandel'), findsNothing);
    await tester.tap(find.text('Karmesin & Purpur 151'));
    await tester.pumpAndSettle();
    expect(api.calls, contains('setProgress:sv3pt5'));
  });

  testWidgets('Live-Scanner: löst nur bei ruhigem, neuem Bild aus; Fertig fügt alle hinzu', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 30, change: 40, card: true), // Hand bewegt sich
        (motion: 2, change: 40, card: true), // ruhig (1)
        (motion: 2, change: 40, card: true), // ruhig (2) und neu → Foto
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(camera.frames, 1); // genau ein Foto, nicht bei jeder Messung
    expect(api.calls.where((c) => c.startsWith('scan:')).length, 1);
    expect(find.text('Fertig (1)'), findsOneWidget);

    await tester.tap(find.byKey(const Key('live-done')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500)); // Blatt ist hochgefahren
    expect(find.byKey(const Key('live-review')), findsOneWidget);
    await tester.tap(find.byKey(const Key('live-add-all')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    expect(api.calls, contains('confirm:scan1:c1'));
    expect(api.lastItemBody?['card_id'], 'c1');
    await tester.pump(const Duration(seconds: 3));
    expect(camera.stopped, isTrue); // Kamera aus nach dem Schließen
  });

  testWidgets('Live-Scanner ohne Kamerazugriff: Erklärung und Weg zum Foto-Scan', (tester) async {
    await pumpApp(
      tester,
      FakeApi(loggedIn: true),
      camera: FakeLiveCamera(result: CameraStart.denied),
    );
    await tester.tap(find.byKey(const Key('scan-button')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('scan-live')));
    await tester.tap(find.byKey(const Key('scan-live')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('live-unavailable')), findsOneWidget);
    expect(find.textContaining('Kein Kamerazugriff'), findsOneWidget);
  });

  testWidgets('Live-Scanner: Auslöser erkennt sofort; ohne Kamerabild ein Hinweis', (tester) async {
    final api = FakeApi(loggedIn: true);
    // iPhone-Fall: Die Automatik springt nie an (kein Bild bzw. unruhig).
    final camera = FakeLiveCamera()
      ..measurements.addAll(List.filled(12, (motion: -1.0, change: -1.0, card: false)));
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 11; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(camera.frames, 0);
    expect(find.text('Kamera liefert kein Bild – Auslöser antippen'), findsOneWidget);

    await tester.tap(find.byKey(const Key('live-shutter')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(camera.frames, 1);
    expect(api.calls.where((c) => c.startsWith('scan:')).length, 1);
    expect(find.text('Fertig (1)'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('Einstellungen: Sammlung zurücksetzen nur mit „LÖSCHEN“', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/settings'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('reset-collection')), 300);
    await tester.tap(find.byKey(const Key('reset-collection')));
    await tester.pumpAndSettle();

    FilledButton go() => tester.widget<FilledButton>(find.byKey(const Key('reset-go')));
    expect(go().onPressed, isNull); // gesperrt
    await tester.enterText(find.byKey(const Key('reset-confirm')), 'löschen');
    await tester.pump();
    expect(go().onPressed, isNull); // genau „LÖSCHEN“
    await tester.enterText(find.byKey(const Key('reset-confirm')), 'LÖSCHEN');
    await tester.ensureVisible(find.byKey(const Key('reset-wishlist')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reset-wishlist')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('reset-go')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('reset:true'));
    expect(
      find.text(
        'Sammlung zurückgesetzt: 12 Positionen und 3 Ordner gelöscht, 4 Merklisten-Einträge.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('Collectr-Import: Vorschau, prüfen, Slabs auf PSA 10, übernehmen', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final payload = base64Url.encode(
      utf8.encode(
        jsonEncode({
          'p': 'Main Ordner',
          'u': 'https://app.getcollectr.com/showcase/profile/x',
          'r': [
            for (var i = 0; i < 4; i++) ['Karte $i', 'Eevee Heroes', 'Secret Rare • 08$i/069'],
          ],
        }),
      ),
    );
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/collectr-import?d=$payload'));
    await tester.pumpAndSettle();

    expect(api.calls, contains('collectrPreview:4:Main Ordner'));
    expect(find.text('Main Ordner'), findsOneWidget); // Ordnername aus Collectr
    expect(find.text('2 zugeordnet · 1 bitte prüfen · 1 nicht gefunden'), findsOneWidget);
    expect(find.text('1 Karten übernehmen'), findsOneWidget); // Slab ohne Note fehlt noch

    await tester.tap(find.byKey(const Key('collectr-grade-all')));
    await tester.pump();
    expect(find.text('2 Karten übernehmen'), findsOneWidget);

    await tester.tap(find.byKey(const Key('collectr-row-1'))); // „bitte prüfen“ → wählen
    await tester.pumpAndSettle();
    await tester.tap(find.text('Espeon V'));
    await tester.pumpAndSettle();
    expect(find.text('3 Karten übernehmen'), findsOneWidget);

    await tester.tap(find.byKey(const Key('collectr-commit')));
    await tester.pumpAndSettle();
    final commit = api.lastCollectrCommit!;
    expect(commit['folder_name'], 'Main Ordner');
    final items = commit['items']! as List<Json>;
    expect(items.map((i) => i['card_id']), ['c1', 'c3', 'c1']);
    expect(items[0]['quantity'], 2);
    expect(items[2]['grading_company'], 'PSA');
    expect(items[2]['grade'], '10');
    expect(items[2].containsKey('condition'), isFalse);
    expect(find.textContaining('3 Karten in „Main Ordner“ übernommen.'), findsOneWidget);
  });

  testWidgets('Binder-Scan: Karten erscheinen nach und nach mit Fortschritt', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(tester, api);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/binder'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Foto'));
    await tester.pump();
    await tester.pump();
    expect(api.calls, contains('binderJob:kamera.jpg:auto'));
    expect(find.text('0 von 2 erkannt …'), findsOneWidget);
    expect(find.byKey(const Key('binder-pending')), findsNWidgets(2));

    await tester.pump(binderPollInterval);
    await tester.pump();
    expect(find.text('1 von 2 erkannt …'), findsOneWidget);
    expect(find.byKey(const Key('binder-pending')), findsOneWidget);
    expect(find.text('Nachtara VMAX'), findsOneWidget);

    await tester.pump(binderPollInterval);
    await tester.pump();
    expect(find.byKey(const Key('binder-progress')), findsNothing);
    expect(find.byKey(const Key('binder-pending')), findsNothing);
    expect(find.text('Nachtara VMAX'), findsNWidgets(2));

    await tester.pump(binderPollInterval * 3);
    expect(api.binderPolls, 2); // fertig → keine weiteren Abfragen

    // Am Ende: alle sicheren auf einmal übernehmen, die unsichere bleibt zum Prüfen.
    expect(find.text('Alle sicheren übernehmen (1)'), findsOneWidget);
    expect(find.text('1 Karte bitte einzeln prüfen (antippen).'), findsOneWidget);
    await tester.tap(find.byKey(const Key('scan-add-all')));
    await tester.pump();
    await tester.pump();
    expect(api.calls.where((c) => c == 'addItem').length, 1);
    expect(api.calls.where((c) => c.startsWith('confirm:')).length, 1);
    expect(find.text('1 Karte übernommen'), findsOneWidget);
    expect(find.byKey(const Key('scan-add-all')), findsNothing);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    await tester.pump(const Duration(seconds: 1)); // Hinweis fährt ein
    await tester.tap(find.text('Rückgängig'));
    await tester.pump();
    expect(api.calls.where((c) => c.startsWith('deleteItem:')).length, 1);
  });

  testWidgets('Live-Scanner: Erkennung im Hintergrund, Bestätigung mit Ausschnitt', (tester) async {
    final gate = Completer<void>();
    final api = FakeApi(loggedIn: true)..scanGate = gate;
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 2, change: 40, card: true),
        (motion: 2, change: 40, card: true), // Karte 1 → Foto, Erkennung läuft
        (motion: 30, change: 40, card: true), // nächste Karte wird hingelegt
        (motion: 2, change: 40, card: true),
        (motion: 2, change: 40, card: true), // Karte 2 → Foto, obwohl Karte 1 noch erkannt wird
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(camera.frames, 2);
    expect(camera.lastGuide, liveGuide); // nur der Rahmen geht zum Server
    expect(find.text('Erkenne 2 Karten …'), findsOneWidget);

    gate.complete();
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('live-confirm')), findsOneWidget);
    expect(find.text('Nachtara VMAX'), findsWidgets);
    await tester.pump(const Duration(seconds: 2));
    expect(find.byKey(const Key('live-confirm')), findsNothing);
    expect(find.text('Fertig (1)'), findsOneWidget); // gleiche Karte zweimal → einmal
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('Live-Scanner: löst nur mit Karte im Rahmen aus; Rahmen wird grün', (tester) async {
    final api = FakeApi(loggedIn: true);
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 2, change: 40, card: false), // ruhig und neu, aber leer (Boden, Stoff)
        (motion: 2, change: 40, card: false),
        (motion: 2, change: 40, card: false),
        (motion: 2, change: 40, card: true), // Karte hingelegt → grün
        (motion: 2, change: 40, card: true), // zweimal hintereinander → Foto
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(camera.frames, 0); // leerer Rahmen löst nie aus
    expect(find.byKey(const Key('live-frame-empty')), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('live-frame-card')), findsOneWidget);
    expect(camera.frames, 0);
    await tester.pump(const Duration(milliseconds: 300));
    expect(camera.frames, 1);
    expect(camera.lastGuide, liveGuide);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('Live-Scanner: sehr unsicherer Treffer ist kein Tipp', (tester) async {
    final json = scanJson(confident: false);
    (json['best'] as Map<String, Object?>)['confidence'] = 0.3;
    final api = FakeApi(loggedIn: true)..scanResult = json;
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 2, change: 40, card: true),
        (motion: 2, change: 40, card: true),
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.byKey(const Key('live-guess')), findsNothing);
    expect(find.textContaining('Nicht sicher erkannt'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('Live-Scanner: Bild ohne Karte wird still verworfen', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..scanResult = {
        ...scanJson(confident: false),
        'detected': {'card_found': false, 'numbers': <Object>[], 'names': <Object>[]},
      };
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 2, change: 40, card: true),
        (motion: 2, change: 40, card: true),
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(api.calls.where((c) => c.startsWith('scan:')).length, 1);
    expect(find.byKey(const Key('live-guess')), findsNothing);
    expect(find.byKey(const Key('live-flash')), findsNothing);
    expect(find.text('Fertig (0)'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('Live-Scanner: unsicherer Treffer als Tipp – „Ja“ übernimmt ihn', (tester) async {
    final api = FakeApi(loggedIn: true)..scanResult = scanJson(confident: false);
    final camera = FakeLiveCamera()
      ..measurements.addAll([
        (motion: 2, change: 40, card: true),
        (motion: 2, change: 40, card: true),
      ]);
    await pumpApp(tester, api, camera: camera);
    final router = ProviderScope.containerOf(tester.element(find.byType(KartenkisteApp)))
        .read(routerProvider);
    unawaited(router.push('/scan/live'));
    await tester.pump();
    await tester.pump();
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.text('Ist es Nachtara VMAX?'), findsOneWidget);
    await tester.tap(find.byKey(const Key('live-guess-yes')));
    await tester.pump();
    expect(find.text('Fertig (1)'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });
}

void gameTests() {
  testWidgets('Spiel-Umschalter: wirkt auf Übersicht und Sammlung und wird gemerkt', (
    tester,
  ) async {
    final api = FakeApi(loggedIn: true);
    final prefs = MemoryPrefsStore({'onboarded': 'true', 'first_steps_hidden': 'true'});
    await pumpApp(tester, api, prefs: prefs);
    expect(api.gameCalls, contains('dashboard:null'));

    await tester.tap(find.byKey(const Key('game-onepiece')));
    await tester.pumpAndSettle();

    expect(prefs.values['game'], 'onepiece');
    expect(api.gameCalls, containsAll(['dashboard:onepiece', 'movers:onepiece']));

    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();
    expect(api.gameCalls, contains('items:onepiece'));

    // Zurück auf „Alle“ – auch das wird gemerkt.
    await tester.tap(find.byKey(const Key('game-all')).first);
    await tester.pumpAndSettle();
    expect(prefs.values['game'], '');
    expect(api.gameCalls.last, isNot(contains('onepiece')));
  });

  testWidgets('Spiel ohne Karten: Hinweis statt Willkommens-Bildschirm', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..summaryOverride = {...summaryJson(total: '0.00'), 'items': 0, 'positions': 0};
    await pumpApp(
      tester,
      api,
      prefs: MemoryPrefsStore({
        'onboarded': 'true',
        'first_steps_hidden': 'true',
        'game': 'onepiece',
      }),
    );

    expect(find.byKey(const Key('empty-game')), findsOneWidget);
    expect(find.text('Noch keine One Piece-Karten'), findsOneWidget);
    expect(find.byKey(const Key('game-switcher')), findsOneWidget);
  });

  testWidgets('Gesamtwert zeigt die Aufteilung je Spiel', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..summaryOverride = {
        ...summaryJson(),
        'by_game': {'pokemon': '4800.00', 'onepiece': '94.67'},
      };
    await pumpApp(tester, api);

    expect(find.byKey(const Key('game-split')), findsOneWidget);
    expect(find.textContaining('One Piece 94,67'), findsOneWidget);
  });

  testWidgets('Sets durchblättern: One Piece nur auf Englisch und Japanisch', (tester) async {
    final api = FakeApi(loggedIn: true);
    await pumpApp(
      tester,
      api,
      prefs: MemoryPrefsStore({
        'onboarded': 'true',
        'first_steps_hidden': 'true',
        'game': 'onepiece',
      }),
    );
    await tester.tap(find.byKey(const Key('tab-Suche')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('search-browse-sets')));
    await tester.tap(find.byKey(const Key('search-browse-sets')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('set-language-en')), findsOneWidget);
    expect(find.byKey(const Key('set-language-ja')), findsOneWidget);
    expect(find.byKey(const Key('set-language-de')), findsNothing);
    expect(api.calls, contains('catalogSets:en'));
    expect(api.gameCalls, contains('catalogSets:onepiece'));
  });
}

void slabTests() {
  test('Slab-Etikett: Einstufung und Farben je Firma', () {
    expect(gradeDescriptor('PSA', '10'), 'GEM MT');
    expect(gradeDescriptor('PSA', '8'), 'NM-MT');
    expect(gradeDescriptor('BGS', '9.5'), 'GEM MINT');
    expect(gradeDescriptor('BGS', '10 BL'), 'BLACK LABEL');
    expect(gradeDescriptor('CGC', '10'), 'PRISTINE');
    expect(slabStyle('PSA', '10').label, 'PSA');
    expect(slabStyle('BGS', '10 BL').background, const Color(0xFF111111));
    expect(slabStyle('OTHER', '9').label, 'GRADED');
  });

  testWidgets('Gegradete Karten erscheinen im Raster als Slab mit Etikett', (tester) async {
    final api = FakeApi(loggedIn: true)
      ..itemsOverride = [
        {...itemJson(id: 's1'), 'kind': 'graded', 'grading_company': 'PSA', 'grade': '10'},
        {...itemJson(id: 's2'), 'kind': 'graded', 'grading_company': 'BGS', 'grade': '9.5'},
        itemJson(id: 'r1', total: '12.00'),
      ];
    await pumpApp(tester, api);
    await tester.tap(find.byKey(const Key('tab-Sammlung')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('slab-PSA')), findsOneWidget);
    expect(find.byKey(const Key('slab-BGS')), findsOneWidget);
    expect(find.text('GEM MT'), findsOneWidget);
    expect(find.text('BECKETT'), findsOneWidget);
    expect(find.text('9.5'), findsOneWidget);
    expect(tester.takeException(), isNull); // kein Überlauf im Etikett
  });
}
