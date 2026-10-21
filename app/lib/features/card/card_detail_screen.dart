// Karten-Detail: Bild, Zustandspreise (mit Beleg oder als Schätzung markiert),
// Quellen mit Datum und Link, Preisverlauf, eBay, Sammlung/Merkliste.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/value_chart.dart';
import '../cardmarket/cardmarket_edition.dart';
import '../collection/item_sheet.dart';
import '../dashboard/dashboard_screen.dart';
import '../wishlist/wishlist_screen.dart';

final cardProvider = FutureProvider.autoDispose.family<CardInfo, String>(
  (ref, id) => ref.watch(apiProvider).card(id),
);

final pricesProvider = FutureProvider.autoDispose.family<CardPrices, String>(
  (ref, id) => ref.watch(apiProvider).prices(id),
);

final pricechartingProvider = FutureProvider.autoDispose.family<PriceChartingDetails, String>(
  (ref, id) => ref.watch(apiProvider).pricecharting(id),
);

final priceHistoryProvider = FutureProvider.autoDispose
    .family<PriceHistory, ({String cardId, String variant})>(
      (ref, key) => ref.watch(apiProvider).priceHistory(key.cardId, variant: key.variant),
    );

const metricLabels = {
  'trend': 'Trend',
  'low': 'ab',
  'avg': 'Ø',
  'avg1': 'Ø 1 Tag',
  'avg7': 'Ø 7 Tage',
  'avg30': 'Ø 30 Tage',
  'market': 'Markt',
  'mid': 'Mitte',
  'high': 'höchstes',
  'direct_low': 'Direkt ab',
  'low3': 'Ø 3 günstigste',
  'median': 'Median',
  // PriceCharting (US-Verkäufe, in Euro umgerechnet); Noten siehe [metricLabel]
  'ungraded': 'Roh',
};

/// Beschriftung einer Kennzahl – auch PriceCharting-Noten wie `grade_9_5` („Note 9,5“),
/// `bgs_10_black` („BGS 10 Black Label“) oder `cgc_10_pristine` („CGC 10 Pristine“).
String metricLabel(String key) {
  final known = metricLabels[key];
  if (known != null) return known;
  final grade = RegExp(r'^grade_(\d+)(_5)?$').firstMatch(key);
  if (grade != null) return 'Note ${grade.group(1)}${grade.group(2) != null ? ',5' : ''}';
  final company = RegExp(r'^([a-z]+)_10(_black|_pristine)?$').firstMatch(key);
  if (company != null) {
    final suffix = switch (company.group(2)) {
      '_black' => ' Black Label',
      '_pristine' => ' Pristine',
      _ => '',
    };
    return '${company.group(1)!.toUpperCase()} 10$suffix';
  }
  return key;
}

String sourceLabel(String source) => switch (source) {
  'cardmarket' => 'Cardmarket',
  'tcgplayer' => 'TCGplayer',
  'pokemontcg' => 'pokemontcg.io',
  'cardmarket_offers' => 'Cardmarket-Angebote',
  'ebay_sold' => 'eBay verkauft',
  'pricecharting' => 'PriceCharting (US-Preis in €)',
  _ => source,
};

/// eBay-Suche „Verkaufte Artikel“; die Sprungmarke sagt dem Lesezeichen, welche Karte es ist.
///
/// Asiatische Karten werden auf eBay mit lateinischem Namen und „japanese“ o. Ä. angeboten,
/// deshalb dort der übersetzte Name. Mit [grading] (z. B. „PSA 10“) nur gegradete Verkäufe.
Uri ebaySoldSearch(CardInfo card, {String? grading}) {
  final language = switch (card.language) {
    'ja' => 'japanese',
    'ko' => 'korean',
    'zh-tw' || 'zh-cn' => 'chinese',
    _ => null,
  };
  final query = [card.translatedName ?? card.name, card.number, ?grading, ?language].join(' ');
  return Uri.https('www.ebay.de', '/sch/i.html', {
    '_nkw': query,
    'LH_Sold': '1',
    'LH_Complete': '1',
  }).replace(fragment: 'kartenkiste=${card.id}');
}

/// Preis-Variante gespeicherter eBay-Verkäufe zu einer Grading-Angabe („graded:PSA 10“).
String gradedVariant(String company, String? grade) {
  var normalized = (grade ?? '').trim().replaceAll(',', '.');
  if (normalized.endsWith('.0')) normalized = normalized.substring(0, normalized.length - 2);
  return 'graded:${company.toUpperCase()} $normalized'.trim();
}

/// Preis-Seite (Cardmarket/eBay) öffnen und die Karte vorher auf dem Server merken – so
/// findet das Lesezeichen sie auch, wenn man dort weiterklickt (z. B. „Reprints“).
Future<void> openPriceLink(BuildContext context, WidgetRef ref, String cardId, String url) async {
  try {
    await ref.read(apiProvider).setPriceTarget(cardId);
  } on ApiException {
    // Nicht kritisch: Ohne gemerkte Karte fragt die Import-Seite nach.
  }
  if (context.mounted) await openLink(context, url);
}

/// eBay-Verkäufe holen: eingerichtet → direkt in der App von ebay.de (Apify), sonst die
/// eBay-Suche im Browser öffnen (dort überträgt das Lesezeichen die Verkäufe).
Future<void> openEbaySold(
  BuildContext context,
  WidgetRef ref,
  CardInfo card, {
  String? grading,
}) async {
  ApifyStatus? status;
  try {
    status = await ref.read(apiProvider).apifyStatus();
  } on ApiException {
    status = null; // Apify gestört → Lesezeichen-Weg funktioniert trotzdem
  }
  if (!context.mounted) return;
  if (status?.configured ?? false) {
    await context.push(
      Uri(path: '/ebay-fetch/${card.id}', queryParameters: {'grading': ?grading}).toString(),
    );
  } else {
    await openPriceLink(context, ref, card.id, ebaySoldSearch(card, grading: grading).toString());
  }
}

Future<void> openLink(BuildContext context, String url) async {
  final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  if (!ok && context.mounted) showMessage(context, 'Link konnte nicht geöffnet werden.');
}

class CardDetailScreen extends ConsumerWidget {
  const CardDetailScreen({required this.cardId, super.key});

  final String cardId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(cardProvider(cardId));
    return Scaffold(
      appBar: AppBar(title: Text(card.value?.displayName ?? 'Karte')),
      body: AsyncBody(
        value: card,
        onRetry: () => ref.invalidate(cardProvider(cardId)),
        builder: (data) => _CardBody(card: data),
      ),
      bottomNavigationBar: card.value == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _addToWishlist(context, ref, card.value!),
                        icon: const Icon(Icons.favorite_border),
                        label: const Text('Merkliste'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FilledButton.icon(
                        key: const Key('add-to-collection'),
                        onPressed: () async {
                          final saved = await showItemSheet(context, card: card.value);
                          if (saved != null && context.mounted) {
                            invalidateCollection(ref);
                            showMessage(context, 'Zur Sammlung hinzugefügt.');
                          }
                        },
                        icon: const Icon(Icons.add),
                        label: const Text('Sammlung'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }

  Future<void> _addToWishlist(BuildContext context, WidgetRef ref, CardInfo card) async {
    final ok = await runAction(context, () => ref.read(apiProvider).addToWishlist(cardId: card.id));
    if (ok && context.mounted) {
      ref.invalidate(wishlistProvider);
      showMessage(context, 'Auf die Merkliste gesetzt.');
    }
  }
}

class _CardBody extends ConsumerStatefulWidget {
  const _CardBody({required this.card});

  final CardInfo card;

  @override
  ConsumerState<_CardBody> createState() => _CardBodyState();
}

class _CardBodyState extends ConsumerState<_CardBody> {
  String _condition = 'NM';
  String _variant = 'normal';

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    final prices = ref.watch(pricesProvider(card.id));
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(pricesProvider(card.id));
        await ref.read(pricesProvider(card.id).future);
      },
      child: ListView(
        padding: const EdgeInsets.only(bottom: 24),
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CardImage(url: card.image(high: true), width: 130),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        card.displayName,
                        style: Theme.of(context).textTheme.titleLarge
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      if (card.originalName != null)
                        Text(card.originalName!, style: const TextStyle(fontSize: 16)),
                      const SizedBox(height: 4),
                      Text(card.cardSet.name, style: const TextStyle(color: AppColors.textMuted)),
                      Text(
                        'Nr. ${card.number}',
                        style: const TextStyle(color: AppColors.textMuted),
                      ),
                      if (card.variantText case final variants?)
                        Text(
                          variants,
                          key: const Key('card-variants'),
                          style: const TextStyle(color: AppColors.textMuted),
                        ),
                      if (card.illustrator case final illustrator?)
                        Text(
                          'Illustration: $illustrator',
                          style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                        ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          Tag(languageLabels[card.language] ?? card.language),
                          if (card.imageLanguage != null)
                            Tag(
                              'Bild ${languageLabels[card.imageLanguage] ?? card.imageLanguage}',
                              color: AppColors.textMuted,
                            ),
                          if (card.rarity != null) Tag(card.rarity!, color: AppColors.accent),
                          if (card.source == 'user')
                            const Tag('selbst angelegt', color: AppColors.warning),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          CardmarketEditionTile(
            cardId: card.id,
            padding: const EdgeInsets.symmetric(horizontal: 16),
          ),
          AsyncBody(
            value: prices,
            onRetry: () => ref.invalidate(pricesProvider(card.id)),
            builder: _priceSection,
          ),
          const SectionTitle('Preisverlauf (Cardmarket-Trend)'),
          _History(cardId: card.id, variant: _variant),
          _UsMarket(cardId: card.id),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: OutlinedButton.icon(
              key: const Key('card-ebay'),
              onPressed: () => openEbaySold(context, ref, card),
              icon: const Icon(Icons.sell_outlined),
              label: const Text('Verkaufte Angebote bei eBay'),
            ),
          ),
        ],
      ),
    );
  }

  /// Angebotsseite auf Cardmarket, gefiltert nach Kartensprache und gewähltem Zustand.
  String? _cardmarketLink(CardPrices prices) => cardmarketOffersUrl(
    productUrl: prices.cardmarketPage,
    cardId: widget.card.id,
    language: widget.card.language,
    condition: _condition,
  );

  Widget _priceSection(CardPrices prices) {
    final variants = {for (final c in prices.conditions) c.variant}.toList()..sort();
    final variant = variants.contains(_variant) ? _variant : (variants.firstOrNull ?? 'normal');
    final byCondition = {
      for (final c in prices.conditions.where((c) => c.variant == variant)) c.condition: c,
    };
    final selected = byCondition[_condition];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionTitle('Preis'),
        if (variants.length > 1)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SegmentedButton<String>(
              segments: [
                for (final v in variants)
                  ButtonSegment(value: v, label: Text(v == 'reverse' ? 'Reverse Holo' : 'Normal')),
              ],
              selected: {variant},
              onSelectionChanged: (value) => setState(() => _variant = value.first),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final condition in conditions)
                ChoiceChip(
                  label: Text(condition),
                  tooltip: conditionLabels[condition],
                  selected: _condition == condition,
                  onSelected: (_) => setState(() => _condition = condition),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: selected == null
                  ? const Text(
                      'Kein belegter Preis vorhanden – wir erfinden keine Zahl. '
                      'Du kannst in der Sammlung einen Eigenpreis eintragen.',
                      key: Key('no-price'),
                      style: TextStyle(color: AppColors.textMuted),
                    )
                  : _ConditionValue(price: selected),
            ),
          ),
        ),
        if (_cardmarketLink(prices) case final link?)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: OutlinedButton.icon(
              key: const Key('cardmarket-offers'),
              onPressed: () => openPriceLink(context, ref, widget.card.id, link),
              icon: const Icon(Icons.storefront),
              label: Text(
                'Cardmarket-Angebote: ${languageLabels[widget.card.language] ?? widget.card.language}, '
                'ab $_condition',
              ),
            ),
          ),
        if (byCondition.length > 1) ...[
          const SectionTitle('Andere Zustände'),
          for (final condition in conditions)
            if (condition != _condition && byCondition[condition] != null)
              ListTile(
                dense: true,
                title: Text('$condition · ${conditionLabels[condition]}'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (byCondition[condition]!.isEstimate)
                      const Padding(
                        padding: EdgeInsets.only(right: 8),
                        child: Tag('Schätzung', color: AppColors.warning),
                      ),
                    Text(money(byCondition[condition]!.value)),
                  ],
                ),
              ),
        ],
        if (prices.offers.isNotEmpty) ...[
          const SectionTitle('Quellen'),
          for (final offer in prices.offers) _OfferTile(offer: offer),
        ],
        if (prices.lastCheckedAt != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(
              'Zuletzt geprüft: ${dateTime(prices.lastCheckedAt)}',
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ),
      ],
    );
  }
}

class _ConditionValue extends StatelessWidget {
  const _ConditionValue({required this.price});

  final ConditionPrice price;

  @override
  Widget build(BuildContext context) {
    // Verständlich statt technisch: nur den Zustandsfaktor nennen, wenn er nicht 1 ist.
    final factor = double.tryParse(price.factor ?? '');
    final languageFactor = double.tryParse(price.languageFactor ?? '');
    final parts = [
      if (factor != null && factor != 1) 'Zustand ${price.factor!.replaceAll('.', ',')}',
      if (languageFactor != null && languageFactor != 1)
        'Sprache ${price.languageFactor!.replaceAll('.', ',')}',
    ];
    final basis = price.isEstimate && parts.isNotEmpty
        ? 'Near-Mint-Preis × ${parts.join(' × ')}'
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              money(price.value, currency: price.currency),
              key: const Key('condition-value'),
              style: Theme.of(context).textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            Tag(
              price.isEstimate ? 'Schätzung' : 'Beleg',
              color: price.isEstimate ? AppColors.warning : AppColors.gain,
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          [
            '${conditionLabels[price.condition] ?? price.condition} · ${sourceLabel(price.source)} · '
                'Stand ${date(price.updatedAt)}',
            ?basis,
          ].join('\n'),
          style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
        ),
        if (price.url != null)
          TextButton.icon(
            style: TextButton.styleFrom(padding: EdgeInsets.zero),
            onPressed: () => openLink(context, price.url!),
            icon: const Icon(Icons.open_in_new, size: 16),
            label: const Text('Beleg ansehen'),
          ),
      ],
    );
  }
}

class _OfferTile extends StatelessWidget {
  const _OfferTile({required this.offer});

  final Offer offer;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Flexible(
                  child: Text(
                    sourceLabel(offer.source),
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 6),
                Tag(variantLabel(offer.variant)),
                if (offer.condition != null) ...[const SizedBox(width: 6), Tag(offer.condition!)],
                const Spacer(),
                Text(
                  date(offer.updatedAt),
                  style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 16,
              runSpacing: 4,
              children: [
                for (final entry in offer.metrics.entries)
                  Text(
                    entry.key == 'count'
                        ? '${double.parse(entry.value).round()} Verkäufe'
                        : '${metricLabel(entry.key)}: '
                              '${money(entry.value, currency: offer.currency)}',
                    style: const TextStyle(fontSize: 13),
                  ),
              ],
            ),
            if (offer.url != null)
              TextButton.icon(
                style: TextButton.styleFrom(padding: EdgeInsets.zero),
                onPressed: () => openLink(context, offer.url!),
                icon: const Icon(Icons.open_in_new, size: 16),
                label: Text('Bei ${sourceLabel(offer.source)} ansehen'),
              ),
          ],
        ),
      ),
    ),
  );
}

class _History extends ConsumerWidget {
  const _History({required this.cardId, required this.variant});

  final String cardId;
  final String variant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(priceHistoryProvider((cardId: cardId, variant: variant)));
    return history.when(
      loading: () => const SizedBox(height: 160),
      error: (error, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text('$error', style: const TextStyle(color: AppColors.textMuted)),
      ),
      data: (data) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ValueChart(
              currency: data.currency ?? 'EUR',
              points: [
                for (final point in data.points)
                  ChartPoint(point.date, parseAmount(point.value) ?? 0),
              ],
            ),
            if (data.lowest != null)
              Text(
                'Tiefster Preis: ${money(data.lowest)} · Höchster Preis: ${money(data.highest)}'
                '\nseit Beobachtungsbeginn ${date(data.observedSince)}',
                style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
          ],
        ),
      ),
    );
  }
}

/// US-Markt (PriceCharting): Verkäufe je Note, POP-Report, letzte Verkäufe – nur wenn
/// die Karte schon über die Produktseite abgerufen wurde (Slabs, Korea/China).
class _UsMarket extends ConsumerWidget {
  const _UsMarket({required this.cardId});

  final String cardId;

  static const _shownSales = 5;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final details = ref.watch(pricechartingProvider(cardId)).value;
    if (details == null || !details.available) return const SizedBox.shrink();
    const muted = TextStyle(color: AppColors.textMuted, fontSize: 12);
    final volume = details.salesVolume.entries.toList()..sort((a, b) => b.value - a.value);
    return Column(
      key: const Key('us-market'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionTitle('US-Markt (PriceCharting)'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (volume.isNotEmpty) ...[
                const Text('Verkäufe je Note', style: TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final entry in volume.take(10)) Tag('${entry.key}: ${entry.value}×'),
                  ],
                ),
                const SizedBox(height: 12),
              ],
              for (final company in details.population.entries) ...[
                Text(
                  '${company.key}-Population: ${_population(company.value)}',
                  style: const TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 4),
              ],
              if (details.recentSales.isNotEmpty) ...[
                const SizedBox(height: 8),
                const Text('Letzte Verkäufe', style: TextStyle(fontWeight: FontWeight.w600)),
                for (final sale in details.recentSales.take(_shownSales))
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      '${sale.grade} · ${money(sale.priceUsd.toStringAsFixed(2), currency: 'USD')}',
                    ),
                    subtitle: Text(
                      [sale.date, sale.title].whereType<String>().join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: sale.url == null ? null : const Icon(Icons.open_in_new, size: 16),
                    onTap: sale.url == null ? null : () => openLink(context, sale.url!),
                  ),
              ],
              Text('US-Dollar, meist eBay.com · Stand ${date(details.fetchedAt)}', style: muted),
            ],
          ),
        ),
      ],
    );
  }

  /// „10: 27.631 · 9: 47.519 · 8: 17.805“ – höchste Noten zuerst.
  static String _population(Map<String, int> grades) {
    final entries = grades.entries.where((e) => e.value > 0).toList()
      ..sort((a, b) => (double.tryParse(b.key) ?? 0).compareTo(double.tryParse(a.key) ?? 0));
    return entries.take(4).map((e) => '${e.key}: ${_thousands(e.value)}').join(' · ');
  }

  static String _thousands(int value) =>
      value.toString().replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => '.');
}
