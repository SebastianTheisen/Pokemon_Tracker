// Datenmodelle der API (/api/v1). Geldbeträge kommen als Text („1805.90“), damit
// keine Rundungsfehler entstehen; formatiert wird erst in der Anzeige.
import 'json.dart';

export 'json.dart';

// ------------------------------------------------------------------ Nutzer

class User {
  const User({
    required this.id,
    required this.email,
    required this.displayName,
    required this.role,
    required this.isActive,
    required this.createdAt,
    this.lastLoginAt,
  });

  factory User.fromJson(Json json) => User(
    id: json.str('id'),
    email: json.str('email'),
    displayName: json.str('display_name'),
    role: json.str('role'),
    isActive: json.flag('is_active'),
    createdAt: json.time('created_at'),
    lastLoginAt: json.timeOrNull('last_login_at'),
  );

  final String id;
  final String email;
  final String displayName;
  final String role;
  final bool isActive;
  final DateTime createdAt;
  final DateTime? lastLoginAt;

  bool get isAdmin => role == 'admin';
}

class TokenPair {
  const TokenPair({required this.accessToken, required this.refreshToken, required this.user});

  factory TokenPair.fromJson(Json json) => TokenPair(
    accessToken: json.str('access_token'),
    refreshToken: json.str('refresh_token'),
    user: User.fromJson(json.obj('user')),
  );

  final String accessToken;
  final String refreshToken;
  final User user;
}

class SessionInfo {
  const SessionInfo({
    required this.id,
    required this.createdAt,
    required this.expiresAt,
    this.userAgent,
  });

  factory SessionInfo.fromJson(Json json) => SessionInfo(
    id: json.str('id'),
    createdAt: json.time('created_at'),
    expiresAt: json.time('expires_at'),
    userAgent: json.strOrNull('user_agent'),
  );

  final String id;
  final DateTime createdAt;
  final DateTime expiresAt;
  final String? userAgent;
}

class Invite {
  const Invite({
    required this.id,
    required this.createdAt,
    required this.expiresAt,
    required this.status,
    this.note,
    this.code,
  });

  factory Invite.fromJson(Json json) => Invite(
    id: json.str('id'),
    note: json.strOrNull('note'),
    createdAt: json.time('created_at'),
    expiresAt: json.time('expires_at'),
    status: json.str('status'),
    code: json.strOrNull('code'),
  );

  final String id;
  final String? note;
  final DateTime createdAt;
  final DateTime expiresAt;
  final String status; // open | used | revoked | expired
  final String? code; // nur direkt nach dem Erzeugen

  String get statusLabel => switch (status) {
    'open' => 'offen',
    'used' => 'benutzt',
    'revoked' => 'widerrufen',
    'expired' => 'abgelaufen',
    _ => status,
  };
}

class ResetCode {
  const ResetCode({required this.code, required this.expiresAt});

  factory ResetCode.fromJson(Json json) =>
      ResetCode(code: json.str('code'), expiresAt: json.time('expires_at'));

  final String code;
  final DateTime expiresAt;
}

class UserSettings {
  const UserSettings({
    required this.conditionFactors,
    required this.customFactors,
    this.languageFactors = const {},
    this.customLanguageFactors = const {},
    this.defaultLanguage,
  });

  factory UserSettings.fromJson(Json json) => UserSettings(
    conditionFactors: {
      for (final entry in json.obj('condition_factors').entries)
        entry.key: double.parse('${entry.value}'),
    },
    customFactors: json.strings('custom_condition_factors').toSet(),
    languageFactors: {
      for (final entry in (json.objOrNull('language_factors') ?? const {}).entries)
        entry.key: double.parse('${entry.value}'),
    },
    customLanguageFactors:
        (json['custom_language_factors'] == null
                ? const <String>[]
                : json.strings('custom_language_factors'))
            .toSet(),
    defaultLanguage: json.strOrNull('default_language'),
  );

  final Map<String, double> conditionFactors;
  final Set<String> customFactors;

  /// Faktor je Kartensprache auf den Cardmarket-Preis (Standard 1,00).
  final Map<String, double> languageFactors;
  final Set<String> customLanguageFactors;
  final String? defaultLanguage;
}

// ------------------------------------------------------------------ Katalog

class SetSummary {
  const SetSummary({
    required this.id,
    required this.externalId,
    required this.language,
    required this.name,
  });

  factory SetSummary.fromJson(Json json) => SetSummary(
    id: json.str('id'),
    externalId: json.str('external_id'),
    language: json.str('language'),
    name: json.str('name'),
  );

  final String id;
  final String externalId;
  final String language;
  final String name;
}

class CardSet extends SetSummary {
  const CardSet({
    required super.id,
    required super.externalId,
    required super.language,
    required super.name,
    this.seriesName,
    this.releaseDate,
    this.officialCount,
    this.logoUrl,
  });

  factory CardSet.fromJson(Json json) => CardSet(
    id: json.str('id'),
    externalId: json.str('external_id'),
    language: json.str('language'),
    name: json.str('name'),
    seriesName: json.strOrNull('series_name'),
    releaseDate: json.timeOrNull('release_date'),
    officialCount: json.intOrNull('card_count_official'),
    logoUrl: json.strOrNull('logo_url'),
  );

  final String? seriesName;
  final DateTime? releaseDate;
  final int? officialCount;
  final String? logoUrl;
}

class CardInfo {
  const CardInfo({
    required this.id,
    required this.language,
    required this.name,
    required this.number,
    required this.source,
    required this.cardSet,
    this.externalId,
    this.imageUrl,
    this.imageLanguage,
    this.rarity,
    this.translatedName,
    this.variants,
    this.illustrator,
  });

  factory CardInfo.fromJson(Json json) => CardInfo(
    id: json.str('id'),
    externalId: json.strOrNull('external_id'),
    language: json.str('language'),
    name: json.str('name'),
    number: json.str('number'),
    imageUrl: json.strOrNull('image_url'),
    imageLanguage: json.strOrNull('image_language'),
    rarity: json.strOrNull('rarity'),
    source: json.str('source'),
    cardSet: SetSummary.fromJson(json.obj('card_set')),
    translatedName: json.strOrNull('translated_name'),
    variants: json.objOrNull('variants')?.map((key, value) => MapEntry(key, value == true)),
    illustrator: json.strOrNull('illustrator'),
  );

  final String id;
  final String? externalId;
  final String language;
  final String name;
  final String number;
  final String? imageUrl;

  /// Sprache des Bildes, wenn es aus einer anderen Sprachfassung stammt (sonst `null`).
  final String? imageLanguage;
  final String? rarity;
  final String source; // tcgdex | user | official
  final SetSummary cardSet;

  /// Deutscher Name bei japanischen, koreanischen und chinesischen Karten (sonst `null`).
  final String? translatedName;

  /// Welche Fassungen es gibt (normal, reverse, holo, firstEdition); `null` = unbekannt.
  final Map<String, bool>? variants;
  final String? illustrator;

  /// Lesbarer Name: übersetzt, falls vorhanden.
  String get displayName => translatedName ?? name;

  /// Fassungen als Text, z. B. „Holo · Reverse Holo“ (`null`, wenn unbekannt).
  String? get variantText {
    final known = variants;
    if (known == null) return null;
    final labels = [
      for (final (key, label) in [
        ('normal', 'Normal'),
        ('holo', 'Holo'),
        ('reverse', 'Reverse Holo'),
        ('firstEdition', '1. Edition'),
      ])
        if (known[key] ?? false) label,
    ];
    return labels.isEmpty ? null : labels.join(' · ');
  }

  /// Originalname, wenn er sich vom angezeigten Namen unterscheidet (z. B. „ピカチュウex“).
  String? get originalName => translatedName == null ? null : name;

  /// Bildadresse für Listen (`high: false`) bzw. Details.
  ///
  /// TCGdex liefert Adressen ohne Endung (`…/low.webp`, `…/high.webp`). pokemontcg.io und
  /// scrydex haben eine kleine Fassung neben der gespeicherten großen; alle anderen Quellen
  /// (offizielle Datenbanken) gibt es nur in einer Größe.
  String? image({bool high = false}) => cardImageUrl(imageUrl, high: high);

  String get subtitle => '${cardSet.name} · $number';
}

/// Siehe [CardInfo.image].
String? cardImageUrl(String? url, {bool high = false}) {
  if (url == null) return null;
  final uri = Uri.tryParse(url);
  switch (uri?.host) {
    case 'assets.tcgdex.net':
      final lower = url.toLowerCase();
      if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.webp')) {
        return url;
      }
      return '$url/${high ? 'high' : 'low'}.webp';
    case 'images.pokemontcg.io':
      return high ? url : url.replaceFirst(RegExp(r'_hires\.png$'), '.png');
    case 'images.scrydex.com':
      return high ? url : url.replaceFirst(RegExp(r'/large$'), '/small');
    default:
      return url;
  }
}

class SearchHit {
  const SearchHit({required this.score, required this.card});

  factory SearchHit.fromJson(Json json) =>
      SearchHit(score: json.number('score'), card: CardInfo.fromJson(json.obj('card')));

  final double score;
  final CardInfo card;
}

// ------------------------------------------------------------------ Preise

class Offer {
  const Offer({
    required this.source,
    required this.variant,
    required this.currency,
    required this.kind,
    required this.updatedAt,
    required this.metrics,
    this.condition,
    this.url,
  });

  factory Offer.fromJson(Json json) => Offer(
    source: json.str('source'),
    variant: json.str('variant'),
    condition: json.strOrNull('condition'),
    currency: json.str('currency'),
    kind: json.str('kind'),
    updatedAt: json.time('updated_at'),
    url: json.strOrNull('url'),
    metrics: {for (final entry in json.obj('metrics').entries) entry.key: '${entry.value}'},
  );

  final String source;
  final String variant;
  final String? condition;
  final String currency;
  final String kind;
  final DateTime updatedAt;
  final String? url;
  final Map<String, String> metrics;
}

class ConditionPrice {
  const ConditionPrice({
    required this.variant,
    required this.condition,
    required this.value,
    required this.currency,
    required this.kind,
    required this.source,
    required this.updatedAt,
    this.url,
    this.basisMetric,
    this.basisValue,
    this.factor,
    this.languageFactor,
  });

  factory ConditionPrice.fromJson(Json json) => ConditionPrice(
    variant: json.str('variant'),
    condition: json.str('condition'),
    value: json.str('value'),
    currency: json.str('currency'),
    kind: json.str('kind'),
    source: json.str('source'),
    updatedAt: json.time('updated_at'),
    url: json.strOrNull('url'),
    basisMetric: json.strOrNull('basis_metric'),
    basisValue: json.strOrNull('basis_value'),
    factor: json.strOrNull('factor'),
    languageFactor: json.strOrNull('language_factor'),
  );

  final String variant;
  final String condition;
  final String value;
  final String currency;
  final String kind; // estimated | external
  final String source;
  final DateTime updatedAt;
  final String? url;
  final String? basisMetric;
  final String? basisValue;
  final String? factor;

  /// Sprachfaktor der Karte bei Schätzungen (`"1.00"` = keiner).
  final String? languageFactor;

  bool get isEstimate => kind == 'estimated';
}

class CardPrices {
  const CardPrices({
    required this.status,
    required this.offers,
    required this.conditions,
    this.lastCheckedAt,
    this.cardmarketLink,
  });

  factory CardPrices.fromJson(Json json) => CardPrices(
    status: json.str('status'),
    lastCheckedAt: json.timeOrNull('last_checked_at'),
    offers: json.list('offers', Offer.fromJson),
    conditions: json.list('conditions', ConditionPrice.fromJson),
    cardmarketLink: json.strOrNull('cardmarket_link'),
  );

  final String status; // ok | no_data
  final DateTime? lastCheckedAt;
  final List<Offer> offers;
  final List<ConditionPrice> conditions;

  /// Korrigierte Cardmarket-Seite: per Lesezeichen gemerkt oder – wenn das richtige Produkt
  /// keinen Preis hat – die Seite des richtigen Produkts.
  final String? cardmarketLink;

  /// Cardmarket-Seite der Karte: korrigierte Seite, sonst der Link aus dem TCGdex-Preis.
  String? get cardmarketPage =>
      cardmarketLink ?? offers.where((o) => o.source == 'cardmarket').firstOrNull?.url;
}

/// Dieselbe Karte in einer Cardmarket-Ausgabe (Sprachfassung), z. B. japanisch oder chinesisch.
class CardmarketOption {
  const CardmarketOption({
    required this.productId,
    required this.expansionId,
    required this.name,
    required this.url,
    required this.selected,
    required this.fromTcgdex,
    this.expansionLabel,
    this.expansionSize,
    this.trend,
    this.low,
  });

  factory CardmarketOption.fromJson(Json json) => CardmarketOption(
    productId: json.integer('product_id'),
    expansionId: json.integer('expansion_id'),
    expansionLabel: json.strOrNull('expansion_label'),
    expansionSize: json.intOrNull('expansion_size'),
    name: json.str('name'),
    trend: json.strOrNull('trend'),
    low: json.strOrNull('low'),
    url: json.str('url'),
    selected: json.flag('selected'),
    fromTcgdex: json.flag('from_tcgdex'),
  );

  final int productId;
  final int expansionId;

  /// Bezeichnung der Ausgabe („Japanisch“); steht nicht im Cardmarket-Download.
  final String? expansionLabel;
  final int? expansionSize;
  final String name;
  final String? trend;
  final String? low;
  final String url;
  final bool selected;
  final bool fromTcgdex;

  String get expansionTitle => expansionLabel ?? 'Ausgabe $expansionId';
}

/// Cardmarket-Produkt einer Karte und die Alternativen (gleiche Karte, andere Sprachfassung).
class CardmarketChoice {
  const CardmarketChoice({
    required this.reason,
    required this.uncertain,
    required this.catalogReady,
    required this.options,
    this.productId,
    this.expansionId,
    this.setSource,
    this.url,
    this.setChanged,
    this.cardsAffected,
  });

  factory CardmarketChoice.fromJson(Json json) => CardmarketChoice(
    productId: json.intOrNull('product_id'),
    expansionId: json.intOrNull('expansion_id'),
    reason: json.str('reason'),
    setSource: json.strOrNull('set_source'),
    uncertain: json.flag('uncertain'),
    catalogReady: json.flag('catalog_ready'),
    url: json.strOrNull('url'),
    options: json.list('options', CardmarketOption.fromJson),
    setChanged: json['set_changed'] as bool?,
    cardsAffected: json.intOrNull('cards_affected'),
  );

  final int? productId;
  final int? expansionId;

  /// tcgdex | set (über die Ausgabe des Sets umgehängt) | card (für diese Karte gewählt) |
  /// unmapped (in der Ausgabe nicht gefunden) | none (kein Produkt bekannt).
  final String reason;

  /// Woher die Ausgabe des Sets stammt: tcgdex | builtin | user.
  final String? setSource;

  /// Es gibt Sprachfassungen und die Ausgabe stammt nur von TCGdex → bitte prüfen.
  final bool uncertain;
  final bool catalogReady;
  final String? url;
  final List<CardmarketOption> options;

  /// Nur nach einer Auswahl: Galt sie für das ganze Set, wie viele Karten betrifft sie?
  final bool? setChanged;
  final int? cardsAffected;

  CardmarketOption? get selected => options.where((o) => o.selected).firstOrNull;

  /// Lohnt sich die Anzeige? Nur wenn es etwas zu wählen oder zu prüfen gibt.
  bool get hasAlternatives => options.length > 1 || uncertain;
}

class PricePoint {
  const PricePoint({required this.date, required this.value});

  factory PricePoint.fromJson(Json json) =>
      PricePoint(date: json.time('date'), value: json.str('value'));

  final DateTime date;
  final String value;
}

class PriceHistory {
  const PriceHistory({
    required this.points,
    this.currency,
    this.lowest,
    this.highest,
    this.observedSince,
  });

  factory PriceHistory.fromJson(Json json) => PriceHistory(
    currency: json.strOrNull('currency'),
    points: json.list('points', PricePoint.fromJson),
    lowest: json.strOrNull('lowest'),
    highest: json.strOrNull('highest'),
    observedSince: json.timeOrNull('observed_since'),
  );

  final String? currency;
  final List<PricePoint> points;
  final String? lowest;
  final String? highest;
  final DateTime? observedSince;
}

// ------------------------------------------------------------------ Sammlung

class Product {
  const Product({
    required this.id,
    required this.kind,
    required this.language,
    required this.name,
    this.imageUrl,
    this.cardSet,
    this.cardmarketProductId,
  });

  factory Product.fromJson(Json json) => Product(
    id: json.str('id'),
    kind: json.str('kind'),
    language: json.str('language'),
    name: json.str('name'),
    imageUrl: json.strOrNull('image_url'),
    cardSet: json.objOrNull('card_set') == null ? null : SetSummary.fromJson(json.obj('card_set')),
    cardmarketProductId: json.intOrNull('cardmarket_product_id'),
  );

  final String id;
  final String kind;
  final String language;
  final String name;
  final String? imageUrl;
  final SetSummary? cardSet;

  /// Mit Cardmarket verknüpft → Wert täglich aus dem Preisführer.
  final int? cardmarketProductId;
}

/// Art eines versiegelten Produkts → Anzeige.
const productKindLabels = {
  'booster': 'Booster',
  'booster_bundle': 'Booster-Bundle',
  'elite_trainer_box': 'Elite Trainer Box',
  'display': 'Display',
  'tin': 'Tin',
  'collection_box': 'Kollektion/Box',
  'blister': 'Blister',
  'case': 'Case',
  'other': 'Sonstiges',
};

/// Versiegeltes Produkt aus dem Cardmarket-Katalog (Suchtreffer) mit Preisen in Euro.
class SealedOffer {
  const SealedOffer({
    required this.cardmarketProductId,
    required this.name,
    required this.kind,
    required this.url,
    this.category,
    this.trend,
    this.low,
    this.value,
    this.imageUrl,
  });

  factory SealedOffer.fromJson(Json json) => SealedOffer(
    cardmarketProductId: json.integer('cardmarket_product_id'),
    name: json.str('name'),
    category: json.strOrNull('category'),
    kind: json.str('kind'),
    trend: json.strOrNull('trend'),
    low: json.strOrNull('low'),
    value: json.strOrNull('value'),
    url: json.str('url'),
    imageUrl: json.strOrNull('image_url'),
  );

  final int cardmarketProductId;
  final String name;
  final String? category;
  final String kind;
  final String? trend;
  final String? low;

  /// Wert je Stück: Median aus Trend, Ø 7 und Ø 30 Tagen.
  final String? value;
  final String url;

  /// Bild aus dem TCGplayer-Katalog (englische bzw. japanische Verpackung).
  final String? imageUrl;
}

class Folder {
  const Folder({required this.id, required this.name, required this.sortOrder});

  factory Folder.fromJson(Json json) =>
      Folder(id: json.str('id'), name: json.str('name'), sortOrder: json.integer('sort_order'));

  final String id;
  final String name;
  final int sortOrder;
}

class ItemValue {
  const ItemValue({
    required this.kind,
    this.unitValue,
    this.totalValue,
    this.source,
    this.basis,
    this.change,
  });

  factory ItemValue.fromJson(Json json) => ItemValue(
    kind: json.str('kind'),
    unitValue: json.strOrNull('unit_value'),
    totalValue: json.strOrNull('total_value'),
    source: json.strOrNull('source'),
    basis: json.strOrNull('basis'),
    change: json.strOrNull('change'),
  );

  final String kind; // manual | external | estimated | none
  final String? unitValue;
  final String? totalValue;
  final String? source;
  final String? basis;
  final String? change;

  String get kindLabel => switch (kind) {
    'manual' => 'Eigenpreis',
    'external' => 'Beleg',
    'estimated' => 'Schätzung',
    _ => 'kein Wert',
  };
}

class CollectionItem {
  const CollectionItem({
    required this.id,
    required this.folderId,
    required this.kind,
    required this.variant,
    required this.quantity,
    required this.value,
    required this.createdAt,
    this.card,
    this.product,
    this.condition,
    this.purchasePrice,
    this.purchaseDate,
    this.customPrice,
    this.note,
    this.gradingCompany,
    this.grade,
  });

  factory CollectionItem.fromJson(Json json) => CollectionItem(
    id: json.str('id'),
    folderId: json.str('folder_id'),
    kind: json.str('kind'),
    card: json.objOrNull('card') == null ? null : CardInfo.fromJson(json.obj('card')),
    product: json.objOrNull('product') == null ? null : Product.fromJson(json.obj('product')),
    variant: json.str('variant'),
    condition: json.strOrNull('condition'),
    quantity: json.integer('quantity'),
    purchasePrice: json.strOrNull('purchase_price'),
    purchaseDate: json.timeOrNull('purchase_date'),
    customPrice: json.strOrNull('custom_price'),
    note: json.strOrNull('note'),
    gradingCompany: json.strOrNull('grading_company'),
    grade: json.strOrNull('grade'),
    value: ItemValue.fromJson(json.obj('value')),
    createdAt: json.time('created_at'),
  );

  final String id;
  final String folderId;
  final String kind; // raw | graded | sealed
  final CardInfo? card;
  final Product? product;

  /// Bild der Position: Kartenbild bzw. Bild des versiegelten Produkts.
  String? get image => card?.image() ?? product?.imageUrl;
  final String variant;
  final String? condition;
  final int quantity;
  final String? purchasePrice;
  final DateTime? purchaseDate;
  final String? customPrice;
  final String? note;
  final String? gradingCompany;
  final String? grade;
  final ItemValue value;
  final DateTime createdAt;

  String get title => card?.displayName ?? product?.name ?? '?';

  String get label {
    if (kind == 'graded') return '${gradingCompany ?? ''} ${grade ?? ''}'.trim();
    if (kind == 'sealed') return 'versiegelt';
    return [condition ?? 'NM', if (variant == 'reverse') 'Reverse'].join(' · ');
  }
}

class ItemPage {
  const ItemPage({required this.items, required this.total});

  factory ItemPage.fromJson(Json json) =>
      ItemPage(items: json.list('items', CollectionItem.fromJson), total: json.integer('total'));

  final List<CollectionItem> items;
  final int total;
}

class KindTotals {
  const KindTotals({required this.value, required this.positions, required this.items});

  factory KindTotals.fromJson(Json json) => KindTotals(
    value: json.str('value'),
    positions: json.integer('positions'),
    items: json.integer('items'),
  );

  final String value;
  final int positions;
  final int items;
}

class CollectionSummary {
  const CollectionSummary({
    required this.totalValue,
    required this.estimatedValue,
    required this.changeSinceAdded,
    required this.positions,
    required this.items,
    required this.cards,
    required this.sets,
    required this.unvaluedPositions,
    required this.raw,
    required this.graded,
    required this.sealed,
    this.topItem,
    this.biggestGain,
    this.biggestLoss,
  });

  factory CollectionSummary.fromJson(Json json) {
    CollectionItem? item(String key) =>
        json.objOrNull(key) == null ? null : CollectionItem.fromJson(json.obj(key));
    return CollectionSummary(
      totalValue: json.str('total_value'),
      estimatedValue: json.str('estimated_value'),
      changeSinceAdded: json.str('change_since_added'),
      positions: json.integer('positions'),
      items: json.integer('items'),
      cards: json.integer('cards'),
      sets: json.integer('sets'),
      unvaluedPositions: json.integer('unvalued_positions'),
      raw: KindTotals.fromJson(json.obj('raw')),
      graded: KindTotals.fromJson(json.obj('graded')),
      sealed: KindTotals.fromJson(json.obj('sealed')),
      topItem: item('top_item'),
      biggestGain: item('biggest_gain'),
      biggestLoss: item('biggest_loss'),
    );
  }

  final String totalValue;
  final String estimatedValue;
  final String changeSinceAdded;
  final int positions;
  final int items;
  final int cards;
  final int sets;
  final int unvaluedPositions;
  final KindTotals raw;
  final KindTotals graded;
  final KindTotals sealed;
  final CollectionItem? topItem;
  final CollectionItem? biggestGain;
  final CollectionItem? biggestLoss;
}

class ValuePoint {
  const ValuePoint({
    required this.date,
    required this.totalValue,
    required this.estimatedValue,
    required this.isLive,
  });

  factory ValuePoint.fromJson(Json json) => ValuePoint(
    date: json.time('date'),
    totalValue: json.str('total_value'),
    estimatedValue: json.str('estimated_value'),
    isLive: json.flag('is_live'),
  );

  final DateTime date;
  final String totalValue;
  final String estimatedValue;
  final bool isLive;
}

class CollectionHistory {
  const CollectionHistory({required this.points, required this.markers});

  factory CollectionHistory.fromJson(Json json) => CollectionHistory(
    points: json.list('points', ValuePoint.fromJson),
    markers: json.list('markers', (m) => m.time('date')),
  );

  final List<ValuePoint> points;
  final List<DateTime> markers;
}

class SetOverview {
  const SetOverview({
    required this.cardSet,
    required this.positions,
    required this.value,
    required this.ownedCards,
  });

  factory SetOverview.fromJson(Json json) => SetOverview(
    cardSet: CardSet.fromJson(json.obj('card_set')),
    positions: json.integer('positions'),
    value: json.str('value'),
    ownedCards: json.integer('owned_cards'),
  );

  final CardSet cardSet;
  final int positions;
  final String value;
  final int ownedCards;
}

class WishlistEntry {
  const WishlistEntry({
    required this.id,
    required this.createdAt,
    this.card,
    this.product,
    this.nmValue,
    this.nmValueKind,
  });

  factory WishlistEntry.fromJson(Json json) => WishlistEntry(
    id: json.str('id'),
    createdAt: json.time('created_at'),
    card: json.objOrNull('card') == null ? null : CardInfo.fromJson(json.obj('card')),
    product: json.objOrNull('product') == null ? null : Product.fromJson(json.obj('product')),
    nmValue: json.strOrNull('nm_value'),
    nmValueKind: json.strOrNull('nm_value_kind'),
  );

  final String id;
  final DateTime createdAt;
  final CardInfo? card;
  final Product? product;
  final String? nmValue;
  final String? nmValueKind;
}

// ------------------------------------------------------------------ Scanner

class ScanMatch {
  const ScanMatch({
    required this.card,
    required this.confidence,
    required this.reasons,
    this.imageInliers,
  });

  factory ScanMatch.fromJson(Json json) => ScanMatch(
    card: CardInfo.fromJson(json.obj('card')),
    confidence: json.number('confidence'),
    reasons: json.strings('reasons'),
    imageInliers: json.intOrNull('image_inliers'),
  );

  final CardInfo card;
  final double confidence;
  final List<String> reasons;
  final int? imageInliers;
}

class Grading {
  const Grading({required this.company, this.grade, this.cert});

  factory Grading.fromJson(Json json) => Grading(
    company: json.str('company'),
    grade: json.strOrNull('grade'),
    cert: json.strOrNull('cert'),
  );

  final String company;
  final String? grade;

  /// Zertifikatsnummer vom Etikett (falls lesbar).
  final String? cert;
}

/// Von PSA bestätigtes Zertifikat (offizielle PSA-API).
class PsaCert {
  const PsaCert({
    required this.cert,
    this.year,
    this.brand,
    this.cardNumber,
    this.subject,
    this.gradeDescription,
    this.grade,
    this.population,
    this.populationHigher,
  });

  factory PsaCert.fromJson(Json json) => PsaCert(
    cert: json.str('cert'),
    year: json.strOrNull('year'),
    brand: json.strOrNull('brand'),
    cardNumber: json.strOrNull('card_number'),
    subject: json.strOrNull('subject'),
    gradeDescription: json.strOrNull('grade_description'),
    grade: json.strOrNull('grade'),
    population: json.intOrNull('population'),
    populationHigher: json.intOrNull('population_higher'),
  );

  final String cert;
  final String? year;
  final String? brand;
  final String? cardNumber;
  final String? subject;
  final String? gradeDescription;
  final String? grade;
  final int? population;
  final int? populationHigher;
}

class ScanResult {
  const ScanResult({
    required this.scanId,
    required this.confident,
    required this.hint,
    required this.alternatives,
    required this.durationMs,
    required this.canSaveReference,
    this.best,
    this.grading,
    this.psa,
    this.psaWarning,
  });

  factory ScanResult.fromJson(Json json) => ScanResult(
    scanId: json.str('scan_id'),
    confident: json.flag('confident'),
    hint: json.str('hint'),
    best: json.objOrNull('best') == null ? null : ScanMatch.fromJson(json.obj('best')),
    alternatives: json.list('alternatives', ScanMatch.fromJson),
    grading: json.objOrNull('grading') == null ? null : Grading.fromJson(json.obj('grading')),
    psa: json.objOrNull('psa') == null ? null : PsaCert.fromJson(json.obj('psa')),
    psaWarning: json.strOrNull('psa_warning'),
    durationMs: json.integer('duration_ms'),
    canSaveReference: json.flag('can_save_reference'),
  );

  final String scanId;
  final bool confident;
  final String hint;
  final ScanMatch? best;
  final List<ScanMatch> alternatives;
  final Grading? grading;

  /// Von PSA bestätigt (nur mit PSA-Token und lesbarer Zertifikatsnummer).
  final PsaCert? psa;

  /// PSA nennt eine andere Kartennummer als der beste Treffer.
  final String? psaWarning;
  final int durationMs;
  final bool canSaveReference;

  List<ScanMatch> get matches => [?best, ...alternatives];
}

class BatchItem {
  const BatchItem({required this.filename, this.result, this.error});

  factory BatchItem.fromJson(Json json) => BatchItem(
    filename: json.str('filename'),
    result: json.objOrNull('result') == null ? null : ScanResult.fromJson(json.obj('result')),
    error: json.strOrNull('error'),
  );

  final String filename;
  final ScanResult? result;
  final String? error;
}

class BinderCell {
  const BinderCell({required this.row, required this.column, required this.result});

  factory BinderCell.fromJson(Json json) => BinderCell(
    row: json.integer('row'),
    column: json.integer('column'),
    result: ScanResult.fromJson(json.obj('result')),
  );

  final int row;
  final int column;
  final ScanResult result;
}

class BinderResult {
  const BinderResult({required this.method, required this.cells});

  factory BinderResult.fromJson(Json json) =>
      BinderResult(method: json.str('method'), cells: json.list('cells', BinderCell.fromJson));

  final String method;
  final List<BinderCell> cells;
}

class ConfirmResult {
  const ConfirmResult({required this.referenceSaved, this.note});

  factory ConfirmResult.fromJson(Json json) =>
      ConfirmResult(referenceSaved: json.flag('reference_saved'), note: json.strOrNull('note'));

  final bool referenceSaved;
  final String? note;
}

// ------------------------------------------------------------ Cardmarket-Angebote

/// Ein vom Lesezeichen ausgelesenes Angebot (Rohtexte der Cardmarket-Seite).
class CardmarketOfferRow {
  const CardmarketOfferRow({required this.condition, required this.price, this.labels = const []});

  factory CardmarketOfferRow.fromJson(Json json) => CardmarketOfferRow(
    condition: '${json['condition'] ?? ''}',
    price: '${json['price'] ?? ''}',
    labels: [for (final label in (json['labels'] as List<Object?>? ?? const [])) '$label'],
  );

  final String condition;
  final String price;
  final List<String> labels;

  Json toJson() => {'condition': condition, 'price': price, 'labels': labels};
}

class CardmarketConditionOffer {
  const CardmarketConditionOffer({
    required this.variant,
    required this.condition,
    required this.low,
    required this.low3,
    required this.offers,
  });

  factory CardmarketConditionOffer.fromJson(Json json) => CardmarketConditionOffer(
    variant: json.str('variant'),
    condition: json.str('condition'),
    low: json.str('low'),
    low3: json.str('low3'),
    offers: json.integer('offers'),
  );

  final String variant;
  final String condition;
  final String low;
  final String low3;
  final int offers;
}

class CardmarketOffersResult {
  const CardmarketOffersResult({
    required this.accepted,
    required this.skipped,
    required this.prices,
    required this.warnings,
    required this.saved,
  });

  factory CardmarketOffersResult.fromJson(Json json) => CardmarketOffersResult(
    accepted: json.integer('accepted'),
    skipped: json.integer('skipped'),
    prices: parseList(json['prices'], CardmarketConditionOffer.fromJson),
    warnings: json.strings('warnings'),
    saved: json.integer('saved'),
  );

  final int accepted;
  final int skipped;
  final List<CardmarketConditionOffer> prices;
  final List<String> warnings;
  final int saved;
}

/// Sprach-IDs der Cardmarket-Filter (`?language=3` = Deutsch).
const cardmarketLanguageIds = {'en': 1, 'de': 3, 'zh-cn': 6, 'ja': 7, 'ko': 10, 'zh-tw': 11};

/// Zustands-IDs der Cardmarket-Filter (`?minCondition=2` = ab Near Mint).
const cardmarketConditionIds = {'MT': 1, 'NM': 2, 'EX': 3, 'GD': 4, 'LP': 5, 'PL': 6, 'PO': 7};

/// Angebotsseite einer Karte auf Cardmarket, gefiltert nach Sprache und Mindestzustand.
///
/// Nur mit Produkt-ID bzw. Produktseite (nicht die Suche); die Sprungmarke `#kartenkiste=<id>`
/// sagt dem Lesezeichen, zu welcher Karte die Angebote gehören.
String? cardmarketOffersUrl({
  required String? productUrl,
  required String cardId,
  required String language,
  String condition = 'NM',
}) {
  if (productUrl == null ||
      !(productUrl.contains('idProduct=') || productUrl.contains('/Products/Singles/'))) {
    return null;
  }
  final params = [
    if (cardmarketLanguageIds[language] case final id?) 'language=$id',
    if (cardmarketConditionIds[condition] case final id?) 'minCondition=$id',
  ];
  final separator = productUrl.contains('?') ? '&' : '?';
  return '$productUrl$separator${params.join('&')}#kartenkiste=$cardId';
}

// --------------------------------------------------------------- eBay-Verkäufe

class EbaySale {
  const EbaySale({
    required this.index,
    required this.title,
    required this.group,
    required this.issues,
    required this.suggested,
    this.price,
    this.soldOn,
    this.url = '',
  });

  factory EbaySale.fromJson(Json json) => EbaySale(
    index: json.integer('index'),
    title: json.str('title'),
    price: json.strOrNull('price'),
    soldOn: json.timeOrNull('sold_on'),
    group: json.str('group'),
    url: json.strOrNull('url') ?? '',
    issues: json.strings('issues'),
    suggested: json.flag('suggested'),
  );

  final int index;
  final String title;
  final String? price;
  final DateTime? soldOn;

  /// `raw` (ungegradet) oder z. B. `PSA 10`.
  final String group;
  final String url;
  final List<String> issues;
  final bool suggested;
}

/// Verkaufte Artikel von ebay.de, über Apify geholt – Rohzeilen wie vom Lesezeichen.
class EbayFetch {
  const EbayFetch({
    required this.cardId,
    required this.query,
    required this.pageUrl,
    required this.rows,
    required this.fetchedAt,
    required this.cached,
    this.costUsd,
    this.usedUsd,
    this.budgetUsd,
  });

  factory EbayFetch.fromJson(Json json) => EbayFetch(
    cardId: json.str('card_id'),
    query: json.str('query'),
    pageUrl: json.str('page_url'),
    rows: [for (final row in json['rows'] as List<dynamic>) row as Json],
    fetchedAt: json.time('fetched_at'),
    cached: json.flag('cached'),
    costUsd: json.strOrNull('cost_usd'),
    usedUsd: (json['used_usd'] as num?)?.toDouble(),
    budgetUsd: (json['budget_usd'] as num?)?.toDouble(),
  );

  final String cardId;

  /// Suche wie bei eBay eingetippt, z. B. „Glurak ex 183/165 -PSA -BGS …“.
  final String query;

  /// Dieselbe Suche zum Nachsehen im Browser.
  final String pageUrl;
  final List<Json> rows;
  final DateTime fetchedAt;

  /// Gemerkt (kostenlos) statt neu abgerufen.
  final bool cached;
  final String? costUsd;
  final double? usedUsd;
  final double? budgetUsd;
}

/// Ist der eBay-Abruf über Apify eingerichtet, und wie viel Monatsbudget ist verbraucht?
class ApifyStatus {
  const ApifyStatus({required this.configured, this.usedUsd, this.budgetUsd, this.remainingUsd});

  factory ApifyStatus.fromJson(Json json) => ApifyStatus(
    configured: json.flag('configured'),
    usedUsd: (json['used_usd'] as num?)?.toDouble(),
    budgetUsd: (json['budget_usd'] as num?)?.toDouble(),
    remainingUsd: (json['remaining_usd'] as num?)?.toDouble(),
  );

  final bool configured;
  final double? usedUsd;
  final double? budgetUsd;
  final double? remainingUsd;
}

class EbaySoldResult {
  const EbaySoldResult({required this.sales, required this.warnings, required this.saved});

  factory EbaySoldResult.fromJson(Json json) => EbaySoldResult(
    sales: json.list('sales', EbaySale.fromJson),
    warnings: json.strings('warnings'),
    saved: json.integer('saved'),
  );

  final List<EbaySale> sales;
  final List<String> warnings;
  final int saved;
}

/// Median, günstigster und teuerster Wert einer Gruppe gewählter Verkäufe (für die Vorschau).
({double median, double low, double high, int count}) soldStats(Iterable<double> prices) {
  final sorted = prices.toList()..sort();
  final middle = sorted.length ~/ 2;
  final median = sorted.length.isOdd ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  return (median: median, low: sorted.first, high: sorted.last, count: sorted.length);
}

/// Lesbarer Name einer Preis-Variante (`reverse`, `raw`, `graded:PSA 10` …).
String variantLabel(String variant) => switch (variant) {
  'normal' => 'Normal',
  'reverse' => 'Reverse Holo',
  'holo' => 'Holo',
  'raw' => 'ungegradet',
  _ when variant.startsWith('graded:') => variant.substring('graded:'.length),
  _ => variant,
};

/// Karte, deren Cardmarket-Trend sich im Zeitraum deutlich bewegt hat.
class Mover {
  const Mover({
    required this.card,
    required this.variant,
    required this.quantity,
    required this.before,
    required this.now,
    required this.change,
    required this.changePct,
  });

  factory Mover.fromJson(Json json) => Mover(
    card: CardInfo.fromJson(json.obj('card')),
    variant: json.str('variant'),
    quantity: json.integer('quantity'),
    before: json.str('before'),
    now: json.str('now'),
    change: json.str('change'),
    changePct: json.str('change_pct'),
  );

  final CardInfo card;
  final String variant;
  final int quantity;

  /// Trend je Stück zu Beginn des Zeitraums bzw. jetzt.
  final String before;
  final String now;

  /// Veränderung des Gesamtwerts (alle Exemplare) und in Prozent.
  final String change;
  final String changePct;
}

class Movers {
  const Movers({required this.days, required this.gainers, required this.losers});

  factory Movers.fromJson(Json json) => Movers(
    days: json.integer('days'),
    gainers: json.list('gainers', Mover.fromJson),
    losers: json.list('losers', Mover.fromJson),
  );

  final int days;
  final List<Mover> gainers;
  final List<Mover> losers;

  bool get isEmpty => gainers.isEmpty && losers.isEmpty;
}
