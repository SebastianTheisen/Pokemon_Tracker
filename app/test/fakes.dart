// Testattrappen: API ohne Netzwerk, Bildquelle ohne Kamera.
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:kartenkiste/app.dart';
import 'package:kartenkiste/core/api.dart';
import 'package:kartenkiste/core/providers.dart';
import 'package:kartenkiste/core/token_store.dart';
import 'package:kartenkiste/features/scan/scan_screens.dart';
import 'package:kartenkiste/models/models.dart';

final now = DateTime.utc(2026, 10, 17, 12);

Json userJson({String role = 'user', String name = 'Sebastian'}) => {
  'id': 'u1',
  'email': 'ich@example.com',
  'display_name': name,
  'role': role,
  'is_active': true,
  'created_at': now.toIso8601String(),
  'last_login_at': null,
};

Json cardJson({
  String id = 'c1',
  String name = 'Nachtara VMAX',
  String number = '215',
  String language = 'de',
  String? translatedName,
  Map<String, bool>? variants,
  String? illustrator,
}) => {
  'id': id,
  'variants': variants,
  'illustrator': illustrator,
  'translated_name': translatedName,
  'external_id': 'swsh7-$number',
  'language': language,
  'name': name,
  'number': number,
  'image_url': 'https://assets.tcgdex.net/de/swsh/swsh7/$number',
  'rarity': null,
  'source': 'tcgdex',
  'card_set': {'id': 's1', 'external_id': 'swsh7', 'language': language, 'name': 'Drachenwandel'},
};

Json valueJson(String? total, {String kind = 'estimated'}) => {
  'kind': kind,
  'unit_value': total,
  'total_value': total,
  'source': 'cardmarket',
  'basis': null,
  'change': '0.00',
};

Json itemJson({String id = 'i1', String total = '1805.90'}) => {
  'id': id,
  'folder_id': 'f1',
  'kind': 'raw',
  'card': cardJson(),
  'product': null,
  'variant': 'normal',
  'condition': 'NM',
  'quantity': 1,
  'purchase_price': null,
  'purchase_date': null,
  'custom_price': null,
  'note': null,
  'grading_company': null,
  'grade': null,
  'value_at_add': total,
  'value': valueJson(total),
  'created_at': now.toIso8601String(),
  'updated_at': now.toIso8601String(),
};

Json summaryJson({String total = '4894.67', Json? top}) {
  Json kind(String value) => {'value': value, 'positions': 1, 'items': 1};
  return {
    'total_value': total,
    'estimated_value': '255.00',
    'change_since_added': '51.00',
    'positions': 4,
    'items': 5,
    'cards': 4,
    'sets': 3,
    'unvalued_positions': 0,
    'raw': kind('3844.67'),
    'graded': kind('900.00'),
    'sealed': kind('150.00'),
    'top_item': top,
    'biggest_gain': null,
    'biggest_loss': null,
  };
}

Json scanJson({bool confident = true, Json? grading}) => {
  'scan_id': 'scan1',
  'confident': confident,
  'hint': confident ? 'Erkannt als Nachtara VMAX' : 'Falsche Karte? Selbst suchen',
  'best': {
    'card': cardJson(),
    'confidence': 1.0,
    'reasons': ['Nummer 215/203 passt (Set mit 203 Karten)'],
    'image_inliers': 210,
  },
  'alternatives': [
    {
      'card': cardJson(id: 'c2', name: 'Umbreon VMAX', language: 'en'),
      'confidence': 0.95,
      'reasons': <String>[],
      'image_inliers': 120,
    },
  ],
  'grading': grading,
  'detected': <String, Object?>{},
  'duration_ms': 1234,
  'can_save_reference': true,
};

/// Cardmarket-Auswahl wie vom Server; mit [twins] zusätzlich die chinesische Ausgabe.
Json cardmarketChoiceJson({
  int selected = 907902,
  bool twins = false,
  bool uncertain = false,
  String setSource = 'tcgdex',
}) {
  Json option(int product, int expansion, String? label, String trend) => {
    'product_id': product,
    'expansion_id': expansion,
    'expansion_label': label,
    'expansion_size': 176,
    'name': 'Charizard [Energy Burn | Fire Spin]',
    'trend': trend,
    'low': null,
    'url': 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=$product',
    'selected': product == selected,
    'from_tcgdex': product == 908315,
  };
  return {
    'card_id': 'c1',
    'product_id': selected,
    'expansion_id': selected == 907902 ? 6602 : 6603,
    'reason': 'tcgdex',
    'set_source': setSource,
    'uncertain': uncertain,
    'catalog_ready': true,
    'url': 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=$selected',
    'options': [
      option(907902, 6602, 'Japanisch', '158.67'),
      if (twins) option(908315, 6603, null, '66.34'),
    ],
  };
}

/// API-Attrappe: zeichnet Aufrufe auf und liefert feste Antworten.
class FakeApi extends Api {
  FakeApi({this.loggedIn = false, this.role = 'user'})
    : super(baseUrl: 'http://test', tokens: MemoryTokenStore());

  bool loggedIn;
  String role;
  final calls = <String>[];
  Map<String, Object?>? lastItemBody;
  Json pricesJson = {
    'card_id': 'c1',
    'status': 'ok',
    'last_checked_at': now.toIso8601String(),
    'offers': [
      {
        'source': 'cardmarket',
        'variant': 'normal',
        'condition': null,
        'currency': 'EUR',
        'kind': 'verified',
        'updated_at': now.toIso8601String(),
        'url': 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273',
        'metrics': {'trend': '1805.90', 'avg7': '1790.00'},
      },
    ],
    'conditions': [
      for (final (condition, value) in [('NM', '1805.90'), ('EX', '1535.02')])
        {
          'variant': 'normal',
          'condition': condition,
          'value': value,
          'currency': 'EUR',
          'kind': 'estimated',
          'source': 'cardmarket',
          'updated_at': now.toIso8601String(),
          'url': 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=574273',
          'basis_metric': 'nm_median',
          'basis_value': '1805.90',
          'factor': condition == 'NM' ? '1.00' : '0.85',
        },
    ],
  };
  Json scanResult = scanJson();

  @override
  Future<User?> restoreSession() async => loggedIn ? User.fromJson(userJson(role: role)) : null;

  @override
  Future<User> login(String email, String password) async {
    calls.add('login:$email');
    if (password != 'richtig-gutes-passwort') {
      throw const ApiException('E-Mail oder Passwort falsch.', statusCode: 401);
    }
    loggedIn = true;
    return User.fromJson(userJson(role: role));
  }

  @override
  Future<void> logout() async {
    calls.add('logout');
    loggedIn = false;
  }

  @override
  Future<CollectionSummary> dashboard() async =>
      CollectionSummary.fromJson(summaryJson(top: itemJson()));

  Json moversJson = {'days': 7, 'gainers': <Json>[], 'losers': <Json>[]};

  @override
  Future<Movers> movers({int days = 7}) async => Movers.fromJson(moversJson);

  @override
  Future<CollectionHistory> collectionHistory({int days = 90}) async =>
      CollectionHistory.fromJson({'points': <Json>[], 'markers': <Json>[]});

  @override
  Future<List<SearchHit>> search(String query, {String? language, int limit = 30}) async {
    calls.add('search:$query');
    return query.contains('nachtara')
        ? [
            SearchHit.fromJson({'score': 1.0, 'card': cardJson()}),
          ]
        : [];
  }

  @override
  /// Kartendetails für [card] (Varianten, Illustrator) – Standard unbekannt.
  Map<String, bool>? cardVariants;
  String? cardIllustrator;

  @override
  Future<CardInfo> card(String id) async =>
      CardInfo.fromJson(cardJson(id: id, variants: cardVariants, illustrator: cardIllustrator));

  @override
  Future<CardPrices> prices(String cardId) async => CardPrices.fromJson(pricesJson);

  /// Cardmarket-Ausgabe: Standard eindeutig (keine Auswahl sichtbar).
  Json cardmarketJson = cardmarketChoiceJson();

  @override
  Future<CardmarketChoice> cardmarketChoice(String cardId) async =>
      CardmarketChoice.fromJson(cardmarketJson);

  @override
  Future<CardmarketChoice> chooseCardmarket(String cardId, int productId) async {
    calls.add('chooseCardmarket:$cardId:$productId');
    cardmarketJson = cardmarketChoiceJson(selected: productId, twins: true, setSource: 'user');
    return CardmarketChoice.fromJson({
      ...cardmarketJson,
      'set_changed': true,
      'cards_affected': 176,
    });
  }

  @override
  Future<void> labelCardmarketExpansion(int expansionId, String label) async {
    calls.add('labelExpansion:$expansionId:$label');
  }

  String? rememberedCard;

  @override
  Future<void> setPriceTarget(String cardId) async {
    calls.add('priceTarget:$cardId');
    rememberedCard = cardId;
  }

  @override
  Future<String?> priceTarget() async => rememberedCard;

  @override
  Future<EbaySoldResult> ebaySold(
    String cardId, {
    required String pageUrl,
    required List<Json> rows,
    List<int>? selected,
    bool save = false,
  }) async {
    calls.add('ebaySold:$cardId:${rows.length}:${selected?.join(',')}:$save');
    return EbaySoldResult.fromJson({
      'sales': [
        for (final (index, row) in rows.indexed)
          {
            'index': index,
            'title': row['title'],
            'price': (row['title'] as String).contains('PSA') ? '650.00' : '180.00',
            'sold_on': '2026-10-12',
            'group': (row['title'] as String).contains('PSA') ? 'PSA 10' : 'raw',
            'url': '',
            'issues': (row['title'] as String).contains('Konvolut') ? ['Konvolut'] : <String>[],
            'suggested': !(row['title'] as String).contains('Konvolut'),
          },
      ],
      'warnings': <String>[],
      'saved': save ? 4 : 0,
    });
  }

  /// Apify: Standard nicht eingerichtet (Lesezeichen-Weg wie bisher).
  Json apifyStatusJson = {'configured': false};

  /// Fehler beim eBay-Abruf (z. B. Budget erreicht) – sonst feste Verkäufe.
  ApiException? ebayFetchError;

  @override
  Future<ApifyStatus> apifyStatus() async => ApifyStatus.fromJson(apifyStatusJson);

  @override
  Future<EbayFetch> ebayFetch(String cardId, {String? grading, bool force = false}) async {
    calls.add('ebayFetch:$cardId:${grading ?? 'raw'}:$force');
    if (ebayFetchError case final error?) throw error;
    return EbayFetch.fromJson({
      'card_id': cardId,
      'query': 'Nachtara VMAX 215/203 ${grading ?? '-PSA -BGS'}',
      'page_url': 'https://www.ebay.de/sch/i.html?_nkw=Nachtara',
      'rows': [
        {'title': 'Nachtara VMAX 215/203 ${grading ?? 'Deutsch'}', 'price': '180,00 €'},
        {'title': 'Pokemon Konvolut 50 Karten', 'price': '20,00 €'},
      ],
      'fetched_at': now.toIso8601String(),
      'cached': !force,
      'cost_usd': force ? '0.07005' : null,
      'used_usd': 0.57,
      'budget_usd': 7.0,
    });
  }

  @override
  Future<CardmarketOffersResult> cardmarketOffers(
    String cardId, {
    required String pageUrl,
    required List<CardmarketOfferRow> rows,
    bool save = false,
    bool rememberPage = false,
  }) async {
    calls.add('cardmarketOffers:$cardId:${rows.length}:$save${rememberPage ? ':remember' : ''}');
    return CardmarketOffersResult.fromJson({
      'accepted': rows.length,
      'skipped': 0,
      'prices': [
        {'variant': 'normal', 'condition': 'NM', 'low': '180.00', 'low3': '188.33', 'offers': 3},
      ],
      'warnings': <String>[],
      'saved': save ? 2 : 0,
    });
  }

  @override
  Future<PriceHistory> priceHistory(
    String cardId, {
    String source = 'cardmarket',
    String variant = 'normal',
    String metric = 'trend',
    int days = 365,
  }) async => PriceHistory.fromJson({
    'source': source,
    'variant': variant,
    'metric': metric,
    'currency': 'EUR',
    'points': [
      {'date': '2026-10-16', 'value': '1790.00'},
      {'date': '2026-10-17', 'value': '1805.90'},
    ],
    'lowest': '1790.00',
    'highest': '1805.90',
    'observed_since': now.toIso8601String(),
  });

  @override
  Future<List<Folder>> folders() async => [
    Folder.fromJson({
      'id': 'f1',
      'name': 'Sammlung',
      'sort_order': 0,
      'created_at': '2026-10-17T00:00:00Z',
    }),
  ];

  @override
  Future<ItemPage> items({
    String? folderId,
    String? kind,
    String? query,
    String sort = 'value_desc',
    int limit = 500,
    int offset = 0,
  }) async => ItemPage.fromJson({
    'items': [itemJson()],
    'total': 1,
  });

  @override
  Future<List<SealedOffer>> searchSealed(String query) async {
    calls.add('searchSealed:$query');
    return [
      SealedOffer.fromJson({
        'cardmarket_product_id': 700001,
        'name': 'Prismatic Evolutions Elite Trainer Box',
        'category': 'Pokémon Elite Trainer Box',
        'kind': 'elite_trainer_box',
        'trend': '95.00',
        'low': '89.00',
        'value': '99.00',
        'url': 'https://www.cardmarket.com/de/Pokemon/Products?idProduct=700001',
      }),
    ];
  }

  @override
  Future<Product> productFromCardmarket(int cardmarketProductId, String language) async {
    calls.add('productFromCardmarket:$cardmarketProductId:$language');
    return Product.fromJson({
      'id': 'p1',
      'kind': 'elite_trainer_box',
      'language': language,
      'name': 'Prismatic Evolutions Elite Trainer Box',
      'cardmarket_product_id': cardmarketProductId,
    });
  }

  @override
  Future<CollectionItem> addItem(Map<String, Object?> body) async {
    calls.add('addItem');
    lastItemBody = body;
    return CollectionItem.fromJson(itemJson());
  }

  @override
  Future<List<WishlistEntry>> wishlist() async => [];

  @override
  Future<ScanResult> scan(UploadImage image, {String? language}) async {
    calls.add('scan:${image.filename}');
    return ScanResult.fromJson(scanResult);
  }

  @override
  Future<ConfirmResult> confirmScan(
    String scanId,
    String cardId, {
    bool saveReference = true,
  }) async {
    calls.add('confirm:$scanId:$cardId');
    return const ConfirmResult(referenceSaved: true);
  }

  @override
  Future<List<Invite>> invites() async => [];

  @override
  Future<Invite> createInvite({String? note, int? days}) async {
    calls.add('invite:$note');
    return Invite.fromJson({
      'id': 'inv1',
      'note': note,
      'created_at': now.toIso8601String(),
      'expires_at': now.add(const Duration(days: 14)).toIso8601String(),
      'used_at': null,
      'used_by_id': null,
      'revoked_at': null,
      'status': 'open',
      'code': 'ABCD-EFGH-JKLM',
    });
  }
}

class FakeImageSource implements ScanImageSource {
  int picks = 0;

  @override
  Future<UploadImage?> pick({required bool camera, double maxSide = 2000}) async {
    picks++;
    return UploadImage(
      bytes: Uint8List.fromList([1, 2, 3]),
      filename: camera ? 'kamera.jpg' : 'galerie.jpg',
    );
  }

  @override
  Future<List<UploadImage>> pickMany({double maxSide = 2000}) async => [
    UploadImage(bytes: Uint8List.fromList([1]), filename: 'a.jpg'),
  ];
}

/// Startet die ganze App mit Attrappen auf einem Handy-großen Bildschirm.
Future<void> pumpApp(WidgetTester tester, FakeApi api, {FakeImageSource? images}) async {
  await initializeDateFormatting('de_DE');
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      retry: (_, _) => null,
      overrides: [
        apiProvider.overrideWithValue(api),
        imageSourceProvider.overrideWithValue(images ?? FakeImageSource()),
      ],
      child: const KartenkisteApp(),
    ),
  );
  await tester.pumpAndSettle();
}
