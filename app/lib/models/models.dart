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
    this.defaultLanguage,
  });

  factory UserSettings.fromJson(Json json) => UserSettings(
    conditionFactors: {
      for (final entry in json.obj('condition_factors').entries)
        entry.key: double.parse('${entry.value}'),
    },
    customFactors: json.strings('custom_condition_factors').toSet(),
    defaultLanguage: json.strOrNull('default_language'),
  );

  final Map<String, double> conditionFactors;
  final Set<String> customFactors;
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
    this.rarity,
  });

  factory CardInfo.fromJson(Json json) => CardInfo(
    id: json.str('id'),
    externalId: json.strOrNull('external_id'),
    language: json.str('language'),
    name: json.str('name'),
    number: json.str('number'),
    imageUrl: json.strOrNull('image_url'),
    rarity: json.strOrNull('rarity'),
    source: json.str('source'),
    cardSet: SetSummary.fromJson(json.obj('card_set')),
  );

  final String id;
  final String? externalId;
  final String language;
  final String name;
  final String number;
  final String? imageUrl;
  final String? rarity;
  final String source; // tcgdex | user
  final SetSummary cardSet;

  /// TCGdex liefert Bild-URLs ohne Endung; `low` für Listen, `high` für Details.
  String? image({bool high = false}) {
    final url = imageUrl;
    if (url == null) return null;
    final lower = url.toLowerCase();
    if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.webp')) {
      return url;
    }
    return '$url/${high ? 'high' : 'low'}.webp';
  }

  String get subtitle => '${cardSet.name} · $number';
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

  bool get isEstimate => kind == 'estimated';
}

class CardPrices {
  const CardPrices({
    required this.status,
    required this.offers,
    required this.conditions,
    this.lastCheckedAt,
  });

  factory CardPrices.fromJson(Json json) => CardPrices(
    status: json.str('status'),
    lastCheckedAt: json.timeOrNull('last_checked_at'),
    offers: json.list('offers', Offer.fromJson),
    conditions: json.list('conditions', ConditionPrice.fromJson),
  );

  final String status; // ok | no_data
  final DateTime? lastCheckedAt;
  final List<Offer> offers;
  final List<ConditionPrice> conditions;
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
  });

  factory Product.fromJson(Json json) => Product(
    id: json.str('id'),
    kind: json.str('kind'),
    language: json.str('language'),
    name: json.str('name'),
    imageUrl: json.strOrNull('image_url'),
    cardSet: json.objOrNull('card_set') == null ? null : SetSummary.fromJson(json.obj('card_set')),
  );

  final String id;
  final String kind;
  final String language;
  final String name;
  final String? imageUrl;
  final SetSummary? cardSet;
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

  String get title => card?.name ?? product?.name ?? '?';

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
  const Grading({required this.company, this.grade});

  factory Grading.fromJson(Json json) =>
      Grading(company: json.str('company'), grade: json.strOrNull('grade'));

  final String company;
  final String? grade;
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
  });

  factory ScanResult.fromJson(Json json) => ScanResult(
    scanId: json.str('scan_id'),
    confident: json.flag('confident'),
    hint: json.str('hint'),
    best: json.objOrNull('best') == null ? null : ScanMatch.fromJson(json.obj('best')),
    alternatives: json.list('alternatives', ScanMatch.fromJson),
    grading: json.objOrNull('grading') == null ? null : Grading.fromJson(json.obj('grading')),
    durationMs: json.integer('duration_ms'),
    canSaveReference: json.flag('can_save_reference'),
  );

  final String scanId;
  final bool confident;
  final String hint;
  final ScanMatch? best;
  final List<ScanMatch> alternatives;
  final Grading? grading;
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
