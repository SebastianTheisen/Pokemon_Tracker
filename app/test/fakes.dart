// Testattrappen: API ohne Netzwerk, Bildquelle ohne Kamera.
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:kartenkiste/app.dart';
import 'package:kartenkiste/core/api.dart';
import 'package:kartenkiste/core/providers.dart';
import 'package:kartenkiste/core/push/push_bridge.dart';
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

Json scanJson({bool confident = true, Json? grading, Json? psa, String? psaWarning}) => {
  'scan_id': 'scan1',
  'psa': psa,
  'psa_warning': psaWarning,
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

  Json? summaryOverride;

  @override
  Future<CollectionSummary> dashboard({String? folderId}) async {
    calls.add('dashboard:$folderId');
    return CollectionSummary.fromJson(summaryOverride ?? summaryJson(top: itemJson()));
  }

  @override
  Future<List<FolderSummary>> folderSummaries() async => [
    FolderSummary.fromJson({
      'folder': {
        'id': 'f1',
        'name': 'Sammlung',
        'sort_order': 0,
        'created_at': '2026-10-17T00:00:00Z',
      },
      'total_value': '4894.67',
      'positions': 4,
      'items': 5,
      'invested': '200.00',
      'profit': '55.00',
      'profit_cost': '200.00',
      'profit_percent': '27.5',
      'profit_positions': 1,
    }),
  ];

  Json moversJson = {'days': 7, 'gainers': <Json>[], 'losers': <Json>[]};

  @override
  Future<Movers> movers({int days = 7}) async => Movers.fromJson(moversJson);

  @override
  Future<CollectionHistory> collectionHistory({int days = 90, String? folderId}) async =>
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

  /// Kartendetails für [card] (Varianten, Illustrator) – Standard unbekannt.
  Map<String, bool>? cardVariants;
  String? cardIllustrator;

  @override
  Future<CardInfo> card(String id) async =>
      CardInfo.fromJson(cardJson(id: id, variants: cardVariants, illustrator: cardIllustrator));

  @override
  Future<CardPrices> prices(String cardId) async => CardPrices.fromJson(pricesJson);

  /// US-Markt (PriceCharting): Standard „nicht vorhanden“ (Abschnitt unsichtbar).
  Json pricechartingJson = {'available': false};

  @override
  Future<PriceChartingDetails> pricecharting(String cardId) async =>
      PriceChartingDetails.fromJson(pricechartingJson);

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

  List<Json> foldersJson = [
    {'id': 'f1', 'name': 'Sammlung', 'sort_order': 0, 'created_at': '2026-10-17T00:00:00Z'},
  ];

  @override
  Future<List<Folder>> folders() async => foldersJson.map(Folder.fromJson).toList();

  List<Json> ownedJson = [];

  @override
  Future<List<OwnedEntry>> owned(List<String> cardIds) async => [
    for (final json in ownedJson)
      if (cardIds.contains(json['card_id'])) OwnedEntry.fromJson(json),
  ];

  @override
  Future<ItemPage> items({
    String? folderId,
    String? kind,
    String? query,
    String sort = 'value_desc',
    String? language,
    String? condition,
    String? minValue,
    String? maxValue,
    bool? withPurchase,
    int limit = 500,
    int offset = 0,
  }) async {
    calls.add(
      'items:${[language, condition, minValue, maxValue, withPurchase].map((v) => v ?? '-').join('|')}',
    );
    return ItemPage.fromJson({
      'items': [itemJson(), itemJson(id: 'i2', total: '50.00')],
      'total': 2,
    });
  }

  @override
  Future<List<SealedSet>> sealedSets() async {
    calls.add('sealedSets');
    return [
      SealedSet.fromJson({
        'expansion_id': 6100,
        'name': 'Prismatische Entwicklungen',
        'products': 12,
        'release_date': '2025-01-17',
        'logo_url': null,
        'image_url': null,
      }),
    ];
  }

  @override
  Future<List<SealedOffer>> searchSealed(String query, {String? kind, int? expansion}) async {
    calls.add('searchSealed:$query:${kind ?? ''}:${expansion ?? ''}');
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
        'expansion_id': 6100,
        'set_name': 'Prismatische Entwicklungen',
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

  Map<String, Object?>? lastItemChanges;

  // ------------------------------------------------------------------ Sets

  static Json setJson() => {
    'id': 's1',
    'external_id': 'swsh7',
    'language': 'de',
    'name': 'Drachenwandel',
    'series_name': 'Schwert & Schild',
    'release_date': '2021-08-27',
    'card_count_official': 203,
    'card_count_total': 237,
    'logo_url': null,
    'symbol_url': null,
  };

  static Json progressCard(
    String id,
    String number, {
    int normal = 0,
    int reverse = 0,
    bool hasReverse = true,
    bool wished = false,
  }) => {
    'card': cardJson(id: id, number: number, name: 'Karte $number'),
    'owned_normal': normal,
    'owned_reverse': reverse,
    'reverse': hasReverse,
    'on_wishlist': wished,
    'nm_value': '2.50',
    'reverse_value': null,
  };

  List<String>? lastWishedIds;

  // ------------------------------------------------------- Freunde, Tausch

  List<TradeDraftLine>? lastTradeLines;
  String? lastTradePartner;

  @override
  Future<Folder> shareFolder(String id, {required bool shared}) async {
    calls.add('share:$id:$shared');
    return Folder(id: id, name: 'Sammlung', sortOrder: 0, shared: shared);
  }

  @override
  Future<List<Friend>> friends() async => [
    Friend.fromJson({
      'user_id': 'u2',
      'display_name': 'Max',
      'folders': 1,
      'items': 2,
      'total_value': '1855.90',
    }),
  ];

  @override
  Future<Showcase> showcase(String userId, {String? folderId}) async {
    calls.add('showcase:$userId');
    return Showcase.fromJson({
      'user_id': userId,
      'display_name': 'Max',
      'folders': [
        {
          'id': 'f9',
          'name': 'Tausch',
          'sort_order': 0,
          'shared': true,
          'created_at': '2026-10-24T00:00:00Z',
        },
      ],
      'items': [itemJson(id: 'm1', total: '50.00')],
      'total_value': '50.00',
    });
  }

  static Json tradeLineJson(String side, String label, String unit, int quantity) => {
    'side': side,
    'card_id': 'c1',
    'product_id': null,
    'label': label,
    'image_url': null,
    'variant': 'normal',
    'condition': 'NM',
    'grading_company': null,
    'grade': null,
    'quantity': quantity,
    'unit_value': unit,
    'total': (double.parse(unit) * quantity).toStringAsFixed(2),
  };

  Json _tradeValue(List<TradeDraftLine> lines) {
    final json = [
      for (final line in lines)
        tradeLineJson(
          line.side,
          line.side == 'give' ? 'Meine Karte' : 'Karte von Max',
          line.side == 'give' ? '30.00' : '50.00',
          line.quantity,
        ),
    ];
    double sum(String side) => json
        .where((l) => l['side'] == side)
        .fold(0, (total, l) => total + double.parse(l['total']! as String));
    return {
      'lines': json,
      'give_value': sum('give').toStringAsFixed(2),
      'get_value': sum('get').toStringAsFixed(2),
      'difference': (sum('get') - sum('give')).toStringAsFixed(2),
      'unvalued': 0,
    };
  }

  @override
  Future<TradeValue> evaluateTrade(List<TradeDraftLine> lines) async {
    calls.add(
      'evaluate:${lines.map((l) => '${l.side}:${l.itemId ?? l.cardId}:${l.quantity}').join(',')}',
    );
    return TradeValue.fromJson(_tradeValue(lines));
  }

  @override
  Future<SavedTrade> saveTrade(List<TradeDraftLine> lines, {String? partner, String? note}) async {
    lastTradeLines = lines;
    lastTradePartner = partner;
    final value = _tradeValue(lines);
    return SavedTrade.fromJson({
      'id': 't1',
      'partner': partner,
      'note': note,
      'created_at': '2026-10-24T15:00:00Z',
      'give_value': value['give_value'],
      'get_value': value['get_value'],
      'now': value,
    });
  }

  @override
  Future<List<SavedTrade>> trades() async => [];

  @override
  Future<List<SetOverview>> collectionSets() async => [
    SetOverview.fromJson({
      'card_set': setJson(),
      'positions': 3,
      'value': '1810.90',
      'owned_cards': 2,
      'cards_total': 4,
      'master_total': 7,
      'master_owned': 3,
    }),
  ];

  @override
  Future<SetProgress> setProgress(String setId) async {
    calls.add('setProgress:$setId');
    return SetProgress.fromJson({
      'card_set': setJson(),
      'cards_total': 4,
      'cards_owned': 2,
      'master_total': 7,
      'master_owned': 3,
      'missing_set_value': '5.00',
      'missing_value': '7.50',
      'cards': [
        progressCard('k1', '1', normal: 1, reverse: 1),
        progressCard('k2', '2', normal: 2),
        progressCard('k3', '3', wished: true),
        progressCard('k4', '4', hasReverse: false),
      ],
    });
  }

  @override
  Future<int> addManyToWishlist(List<String> cardIds) async {
    lastWishedIds = cardIds;
    return cardIds.length;
  }

  // ---------------------------------------------------------- Preisalarme

  List<Json> alertsJson = [];
  String? pushPublicKey = 'BKey';
  int pushDevices = 0;
  Map<String, Object?>? lastAlertBody;

  @override
  Future<List<PriceAlert>> alerts() async => alertsJson.map(PriceAlert.fromJson).toList();

  @override
  Future<PriceAlert> createAlert({
    String? cardId,
    String? productId,
    required String direction,
    required String target,
    String variant = 'normal',
    String condition = 'NM',
  }) async {
    lastAlertBody = {
      'card_id': cardId,
      'product_id': productId,
      'direction': direction,
      'target': target,
      'variant': variant,
      'condition': condition,
    };
    final json = alertJson(direction: direction, target: target);
    alertsJson = [...alertsJson, json];
    return PriceAlert.fromJson(json);
  }

  @override
  Future<PriceAlert> updateAlert(
    String id, {
    String? target,
    String? direction,
    bool? active,
  }) async {
    calls.add('updateAlert:$id:$target:$direction:$active');
    return PriceAlert.fromJson(alertJson(id: id, active: active ?? true));
  }

  @override
  Future<void> deleteAlert(String id) async => calls.add('deleteAlert:$id');

  @override
  Future<PushConfig> pushConfig() async =>
      PushConfig(publicKey: pushPublicKey, devices: pushDevices);

  @override
  Future<void> pushSubscribe(Map<String, Object?> subscription) async {
    calls.add('pushSubscribe:${subscription['endpoint']}');
    pushDevices += 1;
  }

  @override
  Future<void> pushUnsubscribe(String endpoint) async {
    calls.add('pushUnsubscribe:$endpoint');
    pushDevices -= 1;
  }

  @override
  Future<int> pushTest() async {
    calls.add('pushTest');
    return pushDevices;
  }

  @override
  Future<void> deleteItem(String id) async => calls.add('deleteItem:$id');

  @override
  Future<void> addToWishlist({String? cardId, String? productId}) async =>
      calls.add('wishlist:${cardId ?? productId}');

  @override
  Future<int> bulkItems(List<String> ids, String action, {String? folderId}) async {
    calls.add('bulk:$action:${ids.join(',')}:$folderId');
    return ids.length;
  }

  @override
  Future<CollectionItem> updateItem(String id, Map<String, Object?> changes) async {
    calls.add('updateItem:$id');
    lastItemChanges = changes;
    final price = changes['purchase_price'] as String?;
    final json = itemJson()..['purchase_price'] = price;
    if (price != null) {
      final total = double.parse((itemJson()['value'] as Json)['total_value'] as String);
      final cost = double.parse(price);
      (json['value'] as Json)
        ..['cost'] = cost.toStringAsFixed(2)
        ..['profit'] = (total - cost).toStringAsFixed(2);
    }
    return CollectionItem.fromJson(json);
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
/// Schein-Gerät für Benachrichtigungen (statt Browser).
class FakePushBridge implements PushBridge {
  FakePushBridge({this.state = PushStatus.notAsked});

  PushStatus state;
  String? subscribedEndpoint;
  final calls = <String>[];

  @override
  Future<PushStatus> status() async => state;

  @override
  Future<String?> endpoint() async => subscribedEndpoint;

  @override
  Future<Map<String, Object?>> subscribe(String publicKey) async {
    calls.add('subscribe:$publicKey');
    state = PushStatus.granted;
    subscribedEndpoint = 'https://web.push.apple.com/abc';
    return {
      'endpoint': subscribedEndpoint,
      'keys': {'p256dh': 'BPub', 'auth': 'secret'},
    };
  }

  @override
  Future<String?> unsubscribe() async {
    calls.add('unsubscribe');
    final endpoint = subscribedEndpoint;
    subscribedEndpoint = null;
    return endpoint;
  }
}

Json alertJson({
  String id = 'a1',
  String direction = 'below',
  String target = '1500.00',
  bool active = true,
  String? triggeredAt,
}) => {
  'id': id,
  'card': cardJson(),
  'product': null,
  'variant': 'normal',
  'condition': 'NM',
  'direction': direction,
  'target': target,
  'active': active,
  'current_value': '1805.90',
  'created_at': '2026-10-24T10:00:00Z',
  'triggered_at': triggeredAt,
  'triggered_value': triggeredAt == null ? null : '1490.00',
};

Future<void> pumpApp(
  WidgetTester tester,
  FakeApi api, {
  FakeImageSource? images,
  PushBridge? push,
}) async {
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
        pushBridgeProvider.overrideWithValue(push ?? FakePushBridge()),
      ],
      child: const KartenkisteApp(),
    ),
  );
  await tester.pumpAndSettle();
}
