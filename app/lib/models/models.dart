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
    this.translatedName,
  });

  factory SetSummary.fromJson(Json json) => SetSummary(
    id: json.str('id'),
    externalId: json.str('external_id'),
    language: json.str('language'),
    name: json.str('name'),
    translatedName: json.strOrNull('translated_name'),
  );

  final String id;
  final String externalId;
  final String language;
  final String name;

  /// Englischer Name japanischer, koreanischer und taiwanischer Sets („Paradigm Trigger“).
  final String? translatedName;

  /// Angezeigter Name: übersetzt, sonst wie geliefert.
  String get displayName => translatedName ?? name;

  /// Originalname, wenn übersetzt angezeigt wird (z. B. „パラダイムトリガー“).
  String? get originalName => translatedName == null ? null : name;
}

class CardSet extends SetSummary {
  const CardSet({
    required super.id,
    required super.externalId,
    required super.language,
    required super.name,
    super.translatedName,
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
    translatedName: json.strOrNull('translated_name'),
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

  String get subtitle => '${cardSet.displayName} · $number';
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
  const SearchHit({
    required this.score,
    required this.card,
    this.price,
    this.priceEstimated = false,
  });

  factory SearchHit.fromJson(Json json) => SearchHit(
    score: json.number('score'),
    card: CardInfo.fromJson(json.obj('card')),
    price: json.strOrNull('price'),
    priceEstimated: json['price_estimated'] as bool? ?? false,
  );

  final double score;
  final CardInfo card;

  /// Near-Mint-Preis zur Orientierung (`null` = noch unbekannt).
  final String? price;

  /// Näherung (Preisführer bzw. Zustandsfaktor) – in der Liste mit „≈“.
  final bool priceEstimated;
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
  'elite_trainer_box': 'Top-Trainer-Box',
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
    this.expansionId,
    this.setName,
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
    expansionId: json.intOrNull('expansion_id'),
    setName: json.strOrNull('set_name'),
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

  /// Cardmarket-Ausgabe (Set) und deren Name (deutsch, sonst englisch).
  final int? expansionId;
  final String? setName;
}

/// Set mit versiegelten Produkten (zum Durchblättern, neueste zuerst).
class SealedSet {
  const SealedSet({
    required this.expansionId,
    required this.name,
    required this.products,
    this.releaseDate,
    this.logoUrl,
    this.imageUrl,
  });

  factory SealedSet.fromJson(Json json) => SealedSet(
    expansionId: json.integer('expansion_id'),
    name: json.str('name'),
    products: json.integer('products'),
    releaseDate: json.timeOrNull('release_date'),
    logoUrl: json.strOrNull('logo_url'),
    imageUrl: json.strOrNull('image_url'),
  );

  final int expansionId;
  final String name;
  final int products;
  final DateTime? releaseDate;
  final String? logoUrl;

  /// Bild eines Produkts aus dem Set (Display bevorzugt).
  final String? imageUrl;
}

class Folder {
  const Folder({
    required this.id,
    required this.name,
    required this.sortOrder,
    this.shared = false,
  });

  factory Folder.fromJson(Json json) => Folder(
    id: json.str('id'),
    name: json.str('name'),
    sortOrder: json.integer('sort_order'),
    shared: json['shared'] == true,
  );

  final String id;
  final String name;
  final int sortOrder;

  /// Showcase: für Freunde sichtbar (ohne Kaufpreise und Notizen).
  final bool shared;
}

class ItemValue {
  const ItemValue({
    required this.kind,
    this.unitValue,
    this.totalValue,
    this.source,
    this.basis,
    this.change,
    this.cost,
    this.profit,
  });

  factory ItemValue.fromJson(Json json) => ItemValue(
    kind: json.str('kind'),
    unitValue: json.strOrNull('unit_value'),
    totalValue: json.strOrNull('total_value'),
    source: json.strOrNull('source'),
    basis: json.strOrNull('basis'),
    change: json.strOrNull('change'),
    cost: json.strOrNull('cost'),
    profit: json.strOrNull('profit'),
  );

  final String kind; // manual | external | estimated | none
  final String? unitValue;
  final String? totalValue;
  final String? source;
  final String? basis;
  final String? change;

  /// Kaufpreis × Menge (falls angegeben).
  final String? cost;

  /// Wert minus Kaufpreis (gesamt) – nur mit Kaufpreis und Wert.
  final String? profit;

  /// Gewinn in Prozent des Kaufpreises.
  double? get profitPercent {
    final costValue = cost == null ? null : double.tryParse(cost!);
    final profitValue = profit == null ? null : double.tryParse(profit!);
    if (costValue == null || profitValue == null || costValue == 0) return null;
    return profitValue / costValue;
  }

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
    this.trend7dPct,
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
    trend7dPct: json.strOrNull('trend_7d_pct'),
  );

  /// Veränderung des Marktpreises in 7 Tagen in Prozent („4.2“) – nur Rohkarten mit Verlauf.
  final String? trend7dPct;

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
    this.invested = '0.00',
    this.profit = '0.00',
    this.profitCost = '0.00',
    this.profitPercent,
    this.profitPositions = 0,
    this.bestProfit,
    this.worstProfit,
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
      invested: json.strOrNull('invested') ?? '0.00',
      profit: json.strOrNull('profit') ?? '0.00',
      profitCost: json.strOrNull('profit_cost') ?? '0.00',
      profitPercent: json.strOrNull('profit_percent'),
      profitPositions: json.intOrNull('profit_positions') ?? 0,
      bestProfit: item('best_profit'),
      worstProfit: item('worst_profit'),
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

  /// Summe aller Kaufpreise.
  final String invested;

  /// Wert minus Kaufpreis der Positionen mit Kaufpreis und Wert.
  final String profit;
  final String profitCost;

  /// Gewinn in % (eine Nachkommastelle, z. B. "20.0").
  final String? profitPercent;
  final int profitPositions;
  final CollectionItem? bestProfit;
  final CollectionItem? worstProfit;

  bool get hasProfit => profitPositions > 0;
}

/// Ein Ordner als Portfolio: Wert, Kaufpreise, Gewinn.
class FolderSummary {
  const FolderSummary({
    required this.folder,
    required this.totalValue,
    required this.positions,
    required this.items,
    required this.invested,
    required this.profit,
    required this.profitPositions,
    this.profitPercent,
  });

  factory FolderSummary.fromJson(Json json) => FolderSummary(
    folder: Folder.fromJson(json.obj('folder')),
    totalValue: json.str('total_value'),
    positions: json.integer('positions'),
    items: json.integer('items'),
    invested: json.str('invested'),
    profit: json.str('profit'),
    profitPositions: json.integer('profit_positions'),
    profitPercent: json.strOrNull('profit_percent'),
  );

  final Folder folder;
  final String totalValue;
  final int positions;
  final int items;
  final String invested;
  final String profit;
  final int profitPositions;
  final String? profitPercent;
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
    this.cardsTotal,
    this.masterTotal,
    this.masterOwned,
  });

  factory SetOverview.fromJson(Json json) => SetOverview(
    cardSet: CardSet.fromJson(json.obj('card_set')),
    positions: json.integer('positions'),
    value: json.str('value'),
    ownedCards: json.integer('owned_cards'),
    cardsTotal: json.intOrNull('cards_total'),
    masterTotal: json.intOrNull('master_total'),
    masterOwned: json.intOrNull('master_owned'),
  );

  final CardSet cardSet;
  final int positions;
  final String value;
  final int ownedCards;

  /// Karten des Sets im Katalog (inkl. Secret Rares).
  final int? cardsTotal;

  /// Master-Set: Plätze inkl. Reverse Holo.
  final int? masterTotal;
  final int? masterOwned;
}

/// Eine Karte im Set-Fortschritt: Besitz je Fassung, Merkliste, Preis.
class CardProgress {
  const CardProgress({
    required this.card,
    required this.ownedNormal,
    required this.ownedReverse,
    required this.reverse,
    required this.onWishlist,
    this.nmValue,
    this.reverseValue,
  });

  factory CardProgress.fromJson(Json json) => CardProgress(
    card: CardInfo.fromJson(json.obj('card')),
    ownedNormal: json.integer('owned_normal'),
    ownedReverse: json.integer('owned_reverse'),
    reverse: json.flag('reverse'),
    onWishlist: json.flag('on_wishlist'),
    nmValue: json.strOrNull('nm_value'),
    reverseValue: json.strOrNull('reverse_value'),
  );

  final CardInfo card;
  final int ownedNormal;
  final int ownedReverse;

  /// Gibt es die Karte als Reverse Holo (eigener Platz im Master-Set)?
  final bool reverse;
  final bool onWishlist;
  final String? nmValue;
  final String? reverseValue;

  bool get owned => ownedNormal + ownedReverse > 0;

  /// Im Master-Set komplett (Hauptfassung und ggf. Reverse)?
  bool get masterComplete => ownedNormal > 0 && (!reverse || ownedReverse > 0);
}

class SetProgress {
  const SetProgress({
    required this.cardSet,
    required this.cardsTotal,
    required this.cardsOwned,
    required this.masterTotal,
    required this.masterOwned,
    required this.missingSetValue,
    required this.missingValue,
    required this.cards,
  });

  factory SetProgress.fromJson(Json json) => SetProgress(
    cardSet: CardSet.fromJson(json.obj('card_set')),
    cardsTotal: json.integer('cards_total'),
    cardsOwned: json.integer('cards_owned'),
    masterTotal: json.integer('master_total'),
    masterOwned: json.integer('master_owned'),
    missingSetValue: json.str('missing_set_value'),
    missingValue: json.str('missing_value'),
    cards: json.list('cards', CardProgress.fromJson),
  );

  final CardSet cardSet;
  final int cardsTotal;
  final int cardsOwned;
  final int masterTotal;
  final int masterOwned;
  final String missingSetValue;
  final String missingValue;
  final List<CardProgress> cards;
}

class WishlistEntry {
  const WishlistEntry({
    required this.id,
    required this.createdAt,
    this.card,
    this.product,
    this.nmValue,
    this.nmValueKind,
    this.change,
    this.changePct,
    this.changeDays = 7,
  });

  factory WishlistEntry.fromJson(Json json) => WishlistEntry(
    id: json.str('id'),
    createdAt: json.time('created_at'),
    card: json.objOrNull('card') == null ? null : CardInfo.fromJson(json.obj('card')),
    product: json.objOrNull('product') == null ? null : Product.fromJson(json.obj('product')),
    nmValue: json.strOrNull('nm_value'),
    nmValueKind: json.strOrNull('nm_value_kind'),
    change: json.strOrNull('change'),
    changePct: json.strOrNull('change_pct'),
    changeDays: json.intOrNull('change_days') ?? 7,
  );

  /// Veränderung des Stückpreises (Cardmarket-Trend) in [changeDays] Tagen.
  final String? change;
  final String? changePct;
  final int changeDays;

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
  'graded' => 'gegradet',
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

/// Ein Verkauf in den USA (PriceCharting, meist eBay.com) – Preis in US-Dollar.
class MarketSale {
  const MarketSale({
    required this.grade,
    required this.priceUsd,
    this.date,
    this.title,
    this.source,
    this.url,
  });

  factory MarketSale.fromJson(Json json) => MarketSale(
    grade: json.str('grade'),
    priceUsd: json.number('price_usd'),
    date: json.strOrNull('date'),
    title: json.strOrNull('title'),
    source: json.strOrNull('source'),
    url: json.strOrNull('url'),
  );

  final String grade;
  final double priceUsd;
  final String? date;
  final String? title;
  final String? source;
  final String? url;
}

/// US-Markt laut PriceCharting: POP-Report, Verkäufe je Note, letzte Verkäufe.
class PriceChartingDetails {
  const PriceChartingDetails({
    required this.available,
    this.fetchedAt,
    this.productUrl,
    this.population = const {},
    this.salesVolume = const {},
    this.recentSales = const [],
  });

  factory PriceChartingDetails.fromJson(Json json) => PriceChartingDetails(
    available: json.flag('available'),
    fetchedAt: json.timeOrNull('fetched_at'),
    productUrl: json.strOrNull('product_url'),
    population: {
      for (final entry in (json['population'] as Json? ?? const {}).entries)
        entry.key: {
          for (final grade in (entry.value as Json).entries)
            grade.key: (grade.value as num).toInt(),
        },
    },
    salesVolume: {
      for (final entry in (json['sales_volume'] as Json? ?? const {}).entries)
        entry.key: (entry.value as num).toInt(),
    },
    recentSales: json.list('recent_sales', MarketSale.fromJson),
  );

  final bool available;
  final DateTime? fetchedAt;
  final String? productUrl;
  final Map<String, Map<String, int>> population;
  final Map<String, int> salesVolume;
  final List<MarketSale> recentSales;
}

/// Preisalarm: Zielpreis für eine Karte (Variante + Zustand) oder ein versiegeltes Produkt.
class PriceAlert {
  const PriceAlert({
    required this.id,
    required this.variant,
    required this.condition,
    required this.direction,
    required this.target,
    required this.active,
    required this.createdAt,
    this.card,
    this.product,
    this.currentValue,
    this.triggeredAt,
    this.triggeredValue,
  });

  factory PriceAlert.fromJson(Json json) => PriceAlert(
    id: json.str('id'),
    card: json.objOrNull('card') == null ? null : CardInfo.fromJson(json.obj('card')),
    product: json.objOrNull('product') == null ? null : Product.fromJson(json.obj('product')),
    variant: json.str('variant'),
    condition: json.str('condition'),
    direction: json.str('direction'),
    target: json.str('target'),
    active: json.flag('active'),
    currentValue: json.strOrNull('current_value'),
    createdAt: json.time('created_at'),
    triggeredAt: json.timeOrNull('triggered_at'),
    triggeredValue: json.strOrNull('triggered_value'),
  );

  final String id;
  final CardInfo? card;
  final Product? product;
  final String variant;
  final String condition;

  /// `above` (steigt auf/über) oder `below` (fällt auf/unter).
  final String direction;
  final String target;
  final bool active;
  final String? currentValue;
  final DateTime createdAt;
  final DateTime? triggeredAt;
  final String? triggeredValue;

  bool get above => direction == 'above';

  String get title => card?.displayName ?? product?.name ?? 'Unbekannt';

  /// „Reverse Holo · LP“ – nur Abweichungen vom Standard (normal, NM).
  String? get detail {
    if (card == null) return null;
    final parts = [if (variant == 'reverse') 'Reverse Holo', if (condition != 'NM') condition];
    return parts.isEmpty ? null : parts.join(' · ');
  }
}

/// Benachrichtigungen auf dem Server: Schlüssel (null = nicht eingerichtet) und Geräte.
class PushConfig {
  const PushConfig({required this.devices, this.publicKey, this.weeklySummary = true});

  factory PushConfig.fromJson(Json json) => PushConfig(
    publicKey: json.strOrNull('public_key'),
    devices: json.integer('devices'),
    weeklySummary: json['weekly_summary'] != false,
  );

  final String? publicKey;
  final int devices;

  /// Sonntags „Deine Woche“ als Mitteilung.
  final bool weeklySummary;
}

/// Freund mit freigegebenen Ordnern.
class Friend {
  const Friend({
    required this.userId,
    required this.displayName,
    required this.folders,
    required this.items,
    required this.totalValue,
  });

  factory Friend.fromJson(Json json) => Friend(
    userId: json.str('user_id'),
    displayName: json.str('display_name'),
    folders: json.integer('folders'),
    items: json.integer('items'),
    totalValue: json.str('total_value'),
  );

  final String userId;
  final String displayName;
  final int folders;
  final int items;
  final String totalValue;
}

/// Freigegebene Sammlung eines Freundes (ohne Kaufpreise, Notizen, Gewinn).
class Showcase {
  const Showcase({
    required this.userId,
    required this.displayName,
    required this.folders,
    required this.items,
    required this.totalValue,
  });

  factory Showcase.fromJson(Json json) => Showcase(
    userId: json.str('user_id'),
    displayName: json.str('display_name'),
    folders: json.list('folders', Folder.fromJson),
    items: json.list('items', CollectionItem.fromJson),
    totalValue: json.str('total_value'),
  );

  final String userId;
  final String displayName;
  final List<Folder> folders;
  final List<CollectionItem> items;
  final String totalValue;
}

/// Zeile im Tausch-Rechner (Entwurf): Quelle ist eine Position (eigene oder vom Freund)
/// oder eine Katalogkarte.
class TradeDraftLine {
  const TradeDraftLine({
    required this.side,
    this.itemId,
    this.cardId,
    this.productId,
    this.quantity = 1,
    this.maxQuantity,
  });

  /// `give` (ich gebe) oder `get` (ich bekomme).
  final String side;
  final String? itemId;
  final String? cardId;
  final String? productId;
  final int quantity;

  /// Höchstmenge bei Positionen (so viele besitzt man).
  final int? maxQuantity;

  /// Gleiche Quelle auf gleicher Seite → Menge erhöhen statt neue Zeile.
  bool sameSource(TradeDraftLine other) =>
      side == other.side &&
      itemId == other.itemId &&
      cardId == other.cardId &&
      productId == other.productId;

  TradeDraftLine withQuantity(int value) => TradeDraftLine(
    side: side,
    itemId: itemId,
    cardId: cardId,
    productId: productId,
    quantity: value,
    maxQuantity: maxQuantity,
  );

  Json toJson() => {
    'side': side,
    'item_id': ?itemId,
    'card_id': ?cardId,
    'product_id': ?productId,
    'quantity': quantity,
  };
}

class TradeLineValue {
  const TradeLineValue({
    required this.side,
    required this.label,
    required this.quantity,
    this.cardId,
    this.imageUrl,
    this.unitValue,
    this.total,
  });

  factory TradeLineValue.fromJson(Json json) => TradeLineValue(
    side: json.str('side'),
    label: json.str('label'),
    quantity: json.integer('quantity'),
    cardId: json.strOrNull('card_id'),
    imageUrl: json.strOrNull('image_url'),
    unitValue: json.strOrNull('unit_value'),
    total: json.strOrNull('total'),
  );

  final String side;
  final String label;
  final int quantity;
  final String? cardId;
  final String? imageUrl;
  final String? unitValue;
  final String? total;
}

class TradeValue {
  const TradeValue({
    required this.lines,
    required this.giveValue,
    required this.getValue,
    required this.difference,
    required this.unvalued,
  });

  factory TradeValue.fromJson(Json json) => TradeValue(
    lines: json.list('lines', TradeLineValue.fromJson),
    giveValue: json.str('give_value'),
    getValue: json.str('get_value'),
    difference: json.str('difference'),
    unvalued: json.integer('unvalued'),
  );

  final List<TradeLineValue> lines;
  final String giveValue;
  final String getValue;

  /// Bekomme minus gebe (positiv = gut für mich).
  final String difference;
  final int unvalued;
}

/// Gespeicherter Tausch: Werte damals und dieselben Karten heute.
class SavedTrade {
  const SavedTrade({
    required this.id,
    required this.createdAt,
    required this.giveValue,
    required this.getValue,
    required this.now,
    this.partner,
    this.note,
  });

  factory SavedTrade.fromJson(Json json) => SavedTrade(
    id: json.str('id'),
    partner: json.strOrNull('partner'),
    note: json.strOrNull('note'),
    createdAt: json.time('created_at'),
    giveValue: json.str('give_value'),
    getValue: json.str('get_value'),
    now: TradeValue.fromJson(json.obj('now')),
  );

  final String id;
  final String? partner;
  final String? note;
  final DateTime createdAt;
  final String giveValue;
  final String getValue;
  final TradeValue now;

  /// Differenz damals (bekomme minus gebe).
  double get differenceThen => (double.tryParse(getValue) ?? 0) - (double.tryParse(giveValue) ?? 0);
}

/// Bestand einer Karte je Ordner und Fassung („schon in deiner Sammlung“).
class OwnedEntry {
  const OwnedEntry({
    required this.cardId,
    required this.folderId,
    required this.folderName,
    required this.variant,
    required this.quantity,
    this.gradingCompany,
    this.grade,
    this.condition,
    this.unitValue,
    this.valueKind = 'none',
    this.valueSource,
    this.valueBasis,
    this.itemIds = const [],
  });

  factory OwnedEntry.fromJson(Json json) => OwnedEntry(
    cardId: json.str('card_id'),
    folderId: json.str('folder_id'),
    folderName: json.str('folder_name'),
    variant: json.str('variant'),
    gradingCompany: json.strOrNull('grading_company'),
    grade: json.strOrNull('grade'),
    quantity: json.integer('quantity'),
    condition: json.strOrNull('condition'),
    unitValue: json.strOrNull('unit_value'),
    valueKind: json.strOrNull('value_kind') ?? 'none',
    valueSource: json.strOrNull('value_source'),
    valueBasis: json.strOrNull('value_basis'),
    itemIds: json.containsKey('item_ids') ? json.strings('item_ids') : const [],
  );

  /// Zusammengefasste Positionen – zum Bearbeiten direkt von der Kartenseite.
  final List<String> itemIds;

  final String? condition;

  /// Stückwert, mit dem die Position in der Sammlung zählt (`null`: noch kein Preis).
  final String? unitValue;

  /// manual | external | estimated | none
  final String valueKind;
  final String? valueSource;
  final String? valueBasis;

  bool get isSlab => gradingCompany != null;

  final String cardId;
  final String folderId;
  final String folderName;
  final String variant;
  final String? gradingCompany;
  final String? grade;
  final int quantity;

  /// „Reverse Holo“, „PSA 10“, „LP“ – `null` bei normaler Rohkarte in Near Mint.
  String? get version {
    if (gradingCompany != null) return '$gradingCompany ${grade ?? ''}'.trim();
    final parts = [
      if (variant == 'reverse') 'Reverse Holo',
      if (condition != null && condition != 'NM') condition!,
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }
}

/// Karte in der Set-Analyse (Cardmarket-Preisführer).
class MarketCard {
  const MarketCard({required this.card, required this.trend, this.avg30, this.change});

  factory MarketCard.fromJson(Json json) => MarketCard(
    card: CardInfo.fromJson(json.obj('card')),
    trend: json.str('trend'),
    avg30: json.strOrNull('avg30'),
    change: (json['change'] as num?)?.toDouble(),
  );

  final CardInfo card;
  final String trend;
  final String? avg30;

  /// Trend gegenüber Ø 30 Tage (0.12 = +12 %).
  final double? change;
}

class SetAnalytics {
  const SetAnalytics({
    required this.cardSet,
    required this.cardsTotal,
    required this.cardsPriced,
    required this.setValue,
    required this.masterValue,
    required this.gainers,
    required this.losers,
    required this.topCards,
    this.change,
    this.volatility,
    this.stability,
  });

  factory SetAnalytics.fromJson(Json json) => SetAnalytics(
    cardSet: CardSet.fromJson(json.obj('card_set')),
    cardsTotal: json.integer('cards_total'),
    cardsPriced: json.integer('cards_priced'),
    setValue: json.str('set_value'),
    masterValue: json.str('master_value'),
    change: (json['change'] as num?)?.toDouble(),
    volatility: (json['volatility'] as num?)?.toDouble(),
    stability: json.strOrNull('stability'),
    gainers: json.list('gainers', MarketCard.fromJson),
    losers: json.list('losers', MarketCard.fromJson),
    topCards: json.list('top_cards', MarketCard.fromJson),
  );

  final CardSet cardSet;
  final int cardsTotal;
  final int cardsPriced;
  final String setValue;
  final String masterValue;
  final double? change;
  final double? volatility;

  /// ruhig | normal | bewegt
  final String? stability;
  final List<MarketCard> gainers;
  final List<MarketCard> losers;
  final List<MarketCard> topCards;
}

/// Meldung „Das fehlt“ (an die Admins).
class MissingReport {
  const MissingReport({
    required this.id,
    required this.kind,
    required this.text,
    required this.createdAt,
    required this.reporter,
    this.context,
    this.doneAt,
  });

  factory MissingReport.fromJson(Json json) => MissingReport(
    id: json.str('id'),
    kind: json.str('kind'),
    text: json.str('text'),
    context: json.strOrNull('context'),
    createdAt: json.time('created_at'),
    doneAt: json.timeOrNull('done_at'),
    reporter: json.str('reporter'),
  );

  final String id;

  /// card | sealed | wrong | other
  final String kind;
  final String text;
  final String? context;
  final DateTime createdAt;
  final DateTime? doneAt;
  final String reporter;

  bool get done => doneAt != null;
}
