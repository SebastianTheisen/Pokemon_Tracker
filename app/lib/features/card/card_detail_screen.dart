// Karten-Detail: Bild, Zustandspreise (mit Beleg oder als Schätzung markiert),
// Quellen mit Datum und Link, Preisverlauf, eBay, Sammlung/Merkliste.
import '../alerts/alerts_screen.dart';
import '../collection/owned.dart';
import '../reports/reports.dart';

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
import '../../widgets/range_chips.dart';
import '../../widgets/value_chart.dart';
import '../cardmarket/cardmarket_edition.dart';
import '../collection/collection_screen.dart';
import '../sets/sets_screens.dart';
import 'card_viewer.dart';
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
    .family<PriceHistory, ({String cardId, String variant, int days})>(
      (ref, key) =>
          ref.watch(apiProvider).priceHistory(key.cardId, variant: key.variant, days: key.days),
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

/// Eigene Position von der Kartenseite aus bearbeiten (wie aus der Sammlung, ohne „ansehen“).
Future<void> _editOwned(BuildContext context, WidgetRef ref, OwnedEntry entry) async {
  CollectionItem? item;
  final ok = await runAction(
    context,
    () async => item = await ref.read(apiProvider).item(entry.itemIds.first),
  );
  final loaded = item;
  if (!ok || loaded == null || !context.mounted) return;
  await showItemActions(context, ref, loaded, () {
    ref.invalidate(itemsProvider);
    invalidateCollection(ref);
  }, showOpen: false);
}

class CardDetailScreen extends ConsumerWidget {
  const CardDetailScreen({required this.cardId, super.key});

  final String cardId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(cardProvider(cardId));
    return Scaffold(
      appBar: AppBar(
        title: Text(card.value?.displayName ?? 'Karte'),
        actions: [
          if (card.value case final info?)
            IconButton(
              key: const Key('card-alert'),
              tooltip: 'Preisalarm',
              onPressed: () => showAlertSheet(
                context,
                ref,
                card: info,
                prices: ref.read(pricesProvider(info.id)).value,
              ),
              icon: const Icon(Icons.add_alert_outlined),
            ),
        ],
      ),
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
    final neighbors = _neighbors(ref.watch(setProgressProvider(card.cardSet.id)).value);
    return KeyedSubtree(
      key: const Key('card-body'),
      child: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(pricesProvider(card.id));
          await ref.read(pricesProvider(card.id).future);
        },
        child: ListView(
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            _SwipeHeader(
              neighbors: neighbors,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Antippen: Vollbild mit Zoom und Holo-Effekt
                  GestureDetector(
                    key: const Key('card-image'),
                    onTap: () => openCardViewer(context, card),
                    child: Hero(
                      tag: 'card-image-${card.id}',
                      child: CardImage(url: card.image(high: true), width: 130),
                    ),
                  ),
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
                        // Antippen → Set-Seite (Fortschritt, fehlende Karten)
                        InkWell(
                          key: const Key('card-set-link'),
                          onTap: () => context.push('/sets/${card.cardSet.id}'),
                          child: Text(
                            '${[card.cardSet.displayName, ?card.cardSet.originalName].join(' · ')} ›',
                            style: const TextStyle(
                              color: AppColors.primary,
                              decoration: TextDecoration.underline,
                              decorationColor: AppColors.primary,
                            ),
                          ),
                        ),
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                'Nr. ${card.number}',
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(color: AppColors.textMuted),
                              ),
                            ),
                            if (neighbors != null) ...[
                              const Spacer(),
                              _StepButton(
                                key: const Key('card-previous'),
                                icon: Icons.chevron_left,
                                tooltip: 'Vorige Karte im Set',
                                target: neighbors.previous,
                              ),
                              Text(
                                '${neighbors.index + 1}/${neighbors.total}',
                                key: const Key('card-position'),
                                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                              ),
                              _StepButton(
                                key: const Key('card-next'),
                                icon: Icons.chevron_right,
                                tooltip: 'Nächste Karte im Set',
                                target: neighbors.next,
                              ),
                            ],
                          ],
                        ),
                        if (card.variantText case final variants?)
                          Text(
                            variants,
                            key: const Key('card-variants'),
                            style: TextStyle(color: AppColors.textMuted),
                          ),
                        if (card.illustrator case final illustrator?)
                          Text(
                            'Illustration: $illustrator',
                            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
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
                              Tag('selbst angelegt', color: AppColors.warning),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: OwnedPanel(
                cardId: card.id,
                onFetchSlabPrice: (grading) => openEbaySold(context, ref, card, grading: grading),
                onEdit: (entry) => _editOwned(context, ref, entry),
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
            const SizedBox(height: 16),
            // Weiteres aufklappbar – die Seite bleibt kurz, nichts geht verloren.
            FoldSection(
              id: 'history',
              title: 'Preisverlauf (Cardmarket-Trend)',
              initiallyOpen: true,
              child: _History(cardId: card.id, variant: _variant),
            ),
            if (prices.value case final data?) _GradeComparison(card: card, prices: data),
            _UsMarket(cardId: card.id),
            if (prices.value case final data? when data.offers.isNotEmpty)
              FoldSection(
                id: 'sources',
                title: 'Quellen und Belege',
                summary: '${data.offers.length}',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final offer in data.offers) _OfferTile(offer: offer),
                    if (data.lastCheckedAt != null)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                        child: Text(
                          'Zuletzt geprüft: ${dateTime(data.lastCheckedAt)}',
                          style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                        ),
                      ),
                  ],
                ),
              ),
            const Divider(height: 1, indent: 16, endIndent: 16),
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
            Center(
              child: TextButton.icon(
                key: const Key('card-report'),
                onPressed: () => showReportDialog(
                  context,
                  ref,
                  kind: 'wrong',
                  reportContext: 'Karte ${card.id} (${card.displayName} · ${card.subtitle})',
                ),
                icon: const Icon(Icons.flag_outlined, size: 18),
                label: const Text('Bild, Name oder Preis falsch? Melden'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Vorige/nächste Karte im Set (Reihenfolge der Set-Seite) – `null`, solange unbekannt.
  ({CardInfo? previous, CardInfo? next, int index, int total})? _neighbors(SetProgress? progress) {
    final cards = progress?.cards;
    if (cards == null) return null;
    final index = cards.indexWhere((entry) => entry.card.id == widget.card.id);
    if (index < 0 || cards.length < 2) return null;
    return (
      previous: index > 0 ? cards[index - 1].card : null,
      next: index < cards.length - 1 ? cards[index + 1].card : null,
      index: index,
      total: cards.length,
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
        const SectionTitle('Preis ungegradet (Rohkarte)'),
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
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: selected == null
                  ? Text(
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
        // Andere Zustände erst auf Wunsch; Antippen zeigt den Zustand oben groß.
        if (byCondition.length > 1)
          FoldSection(
            id: 'conditions',
            title: 'Alle Zustände',
            summary: '${byCondition.length}',
            child: Column(
              children: [
                for (final condition in conditions)
                  if (byCondition[condition] case final price?)
                    ListTile(
                      key: Key('condition-$condition'),
                      dense: true,
                      selected: condition == _condition,
                      onTap: () => setState(() => _condition = condition),
                      title: Text('$condition · ${conditionLabels[condition]}'),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (price.isEstimate)
                            Padding(
                              padding: EdgeInsets.only(right: 8),
                              child: Tag('Schätzung', color: AppColors.warning),
                            ),
                          Text(money(price.value)),
                        ],
                      ),
                    ),
              ],
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
          style: TextStyle(color: AppColors.textMuted, fontSize: 12),
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
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
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

class _History extends ConsumerStatefulWidget {
  const _History({required this.cardId, required this.variant});

  final String cardId;
  final String variant;

  @override
  ConsumerState<_History> createState() => _HistoryState();
}

class _HistoryState extends ConsumerState<_History> {
  ChartRange _range = ChartRange.quarter;

  /// Punkt unter dem Finger (Kurve zum Anfassen).
  ChartPoint? _scrub;

  @override
  Widget build(BuildContext context) {
    final history = ref.watch(
      priceHistoryProvider((cardId: widget.cardId, variant: widget.variant, days: _range.days)),
    );
    final data = history.value;
    final points = [
      for (final point in data?.points ?? const <PricePoint>[])
        ChartPoint(point.date, parseAmount(point.value) ?? 0),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          RangeChips(value: _range, onChanged: (range) => setState(() => _range = range)),
          const SizedBox(height: 4),
          if (_scrub case final point? when points.isNotEmpty)
            ScrubLine(point: point, first: points.first, currency: data?.currency ?? 'EUR')
          else
            RangeChange(points: points, range: _range, currency: data?.currency ?? 'EUR'),
          if (history.hasError)
            Text('${history.error}', style: TextStyle(color: AppColors.textMuted))
          else if (data == null)
            const SizedBox(height: 160)
          else ...[
            ValueChart(
              currency: data.currency ?? 'EUR',
              points: points,
              onScrub: (point) => setState(() => _scrub = point),
            ),
            if (data.lowest != null)
              Text(
                'Tiefster Preis: ${money(data.lowest)} · Höchster Preis: ${money(data.highest)}'
                '\nseit Beobachtungsbeginn ${date(data.observedSince)}',
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
          ],
        ],
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
    final muted = TextStyle(color: AppColors.textMuted, fontSize: 12);
    final volume = details.salesVolume.entries.toList()..sort((a, b) => b.value - a.value);
    return FoldSection(
      key: const Key('us-market'),
      id: 'us-market',
      title: 'US-Markt (PriceCharting)',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
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
                const SizedBox(height: 8),
              ],
            ),
          ),
        ],
      ),
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

/// Ein Eintrag im Notenvergleich.
typedef _GradeRow = ({String label, double value, String source, Grading? grading});

/// Collectr „Compare Grades“: Roh gegen Slabs je Note und Firma, mit Faktor gegenüber Roh.
///
/// Quellen: Roh = Near-Mint-Preis (Cardmarket); Noten = PriceCharting (US-Verkäufe in €) und
/// gespeicherte eBay-Verkäufe (Median, gleiche Firma und Note). Gibt es beides, zählt eBay.
class _GradeComparison extends StatelessWidget {
  const _GradeComparison({required this.card, required this.prices});

  final CardInfo card;
  final CardPrices prices;

  /// PriceCharting-Kennzahl → Slab (generische Noten werden als PSA gewertet – der Markt dort).
  static Grading? _gradingFor(String metric) {
    final generic = RegExp(r'^grade_(\d+)(_5)?$').firstMatch(metric);
    if (generic != null) {
      return Grading(
        company: 'PSA',
        grade: '${generic.group(1)}${generic.group(2) != null ? '.5' : ''}',
      );
    }
    final company = RegExp(r'^([a-z]+)_10(_black)?').firstMatch(metric);
    if (company == null) return null;
    final name = company.group(1)!.toUpperCase();
    return Grading(company: name, grade: company.group(2) != null ? '10 BL' : '10');
  }

  List<_GradeRow> _rows() {
    final rows = <String, _GradeRow>{};
    for (final offer in prices.offers) {
      if (offer.source == 'pricecharting' && offer.variant == 'graded') {
        for (final MapEntry(:key, :value) in offer.metrics.entries) {
          final amount = double.tryParse(value);
          if (amount == null || amount <= 0) continue;
          final label = key == 'psa_10' ? 'PSA 10' : metricLabel(key).replaceFirst('Note', 'PSA');
          rows[label] = (
            label: label,
            value: amount,
            source: 'PriceCharting',
            grading: _gradingFor(key),
          );
        }
      }
    }
    for (final offer in prices.offers) {
      if (offer.source == 'ebay_sold' && offer.variant.startsWith('graded:')) {
        final median = double.tryParse(offer.metrics['median'] ?? '');
        if (median == null) continue;
        final label = offer.variant.substring('graded:'.length);
        final parts = label.split(' ');
        rows[label] = (
          label: label,
          value: median,
          source: 'eBay (${offer.metrics['count'] ?? '?'} Verkäufe)',
          grading: Grading(company: parts.first, grade: parts.skip(1).join(' ')),
        );
      }
    }
    return rows.values.toList()..sort((a, b) => a.value.compareTo(b.value));
  }

  @override
  Widget build(BuildContext context) {
    final rows = _rows();
    if (rows.isEmpty) return const SizedBox.shrink();
    final raw = prices.conditions
        .where((c) => c.variant == 'normal' && c.condition == 'NM')
        .map((c) => double.tryParse(c.value))
        .firstOrNull;
    final best = rows.last.value;
    return FoldSection(
      key: const Key('grade-comparison'),
      id: 'grades',
      title: 'Noten vergleichen',
      summary: 'bis ${money(best.toStringAsFixed(2))}',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (raw != null)
            _GradeTile(
              label: 'Roh (Near Mint)',
              value: raw,
              source: 'Cardmarket',
              share: raw / best,
            ),
          for (final row in rows)
            _GradeTile(
              label: row.label,
              value: row.value,
              source: row.source,
              share: row.value / best,
              factor: raw == null || raw == 0 ? null : row.value / raw,
              onAdd: row.grading == null
                  ? null
                  : () => showItemSheet(context, card: card, grading: row.grading),
            ),
          Padding(
            padding: EdgeInsets.fromLTRB(16, 4, 16, 0),
            child: Text(
              'Slab-Preise: US-Verkäufe (PriceCharting, in € umgerechnet) bzw. deine gespeicherten '
              'eBay-Verkäufe. „×“ = Vielfaches des Rohpreises. Antippen: als Slab hinzufügen.',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

class _GradeTile extends StatelessWidget {
  const _GradeTile({
    required this.label,
    required this.value,
    required this.source,
    required this.share,
    this.factor,
    this.onAdd,
  });

  final String label;
  final double value;
  final String source;

  /// Anteil am höchsten Preis (Balkenlänge).
  final double share;
  final double? factor;
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context) => InkWell(
    key: Key('grade-$label'),
    onTap: onAdd,
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
              ),
              if (factor != null)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Text(
                    '×${factor!.toStringAsFixed(1).replaceAll('.', ',')}',
                    style: const TextStyle(color: AppColors.accent, fontSize: 12),
                  ),
                ),
              Text(
                money(value.toStringAsFixed(2)),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 3),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(value: share.clamp(0, 1), minHeight: 5),
          ),
          Text(source, style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
        ],
      ),
    ),
  );
}

/// Pfeil zur Nachbarkarte im Set (ausgegraut am Anfang/Ende).
class _StepButton extends StatelessWidget {
  const _StepButton({required this.icon, required this.tooltip, this.target, super.key});

  final IconData icon;
  final String tooltip;
  final CardInfo? target;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    padding: EdgeInsets.zero,
    constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
    onPressed: target == null ? null : () => context.pushReplacement('/card/${target!.id}'),
    icon: Icon(icon),
  );
}

/// Kopf der Kartenseite (Bild, Name, Set): Wischen links/rechts blättert im Set – wie im Album.
/// Bewusst nur hier: auf der Preiskurve gehört die Bewegung dem Finger.
class _SwipeHeader extends StatelessWidget {
  const _SwipeHeader({required this.neighbors, required this.child});

  final ({CardInfo? previous, CardInfo? next, int index, int total})? neighbors;
  final Widget child;

  @override
  Widget build(BuildContext context) => GestureDetector(
    key: const Key('card-header'),
    behavior: HitTestBehavior.opaque,
    onHorizontalDragEnd: (details) {
      final velocity = details.primaryVelocity ?? 0;
      final target = velocity < -300
          ? neighbors?.next
          : velocity > 300
          ? neighbors?.previous
          : null;
      if (target != null) context.pushReplacement('/card/${target.id}');
    },
    child: Padding(padding: const EdgeInsets.all(16), child: child),
  );
}
