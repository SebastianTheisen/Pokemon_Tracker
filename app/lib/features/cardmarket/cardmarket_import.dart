// Cardmarket-Angebote übernehmen: Lesezeichen „An Kartenkiste senden“ und Import-Seite.
//
// Ablauf: In der Karte öffnet „Cardmarket-Angebote“ die gefilterte Angebotsseite (Sprache +
// Mindestzustand, Sprungmarke #kartenkiste=<Karten-ID>). Dort liest das Lesezeichen die
// sichtbaren Angebote aus und öffnet Kartenkiste unter /#/cardmarket-import?d=<Daten>.
// Diese Seite zeigt eine Vorschau (Server wertet aus) und speichert erst nach Bestätigung.
// Kartenkiste selbst ruft Cardmarket nie ab.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../card/card_detail_screen.dart';

/// JavaScript des Lesezeichens; `appOrigin` ist die Adresse von Kartenkiste.
///
/// Absichtlich einfach: liest nur Rohtexte (Zustand, Preis, Beschriftungen der Symbole);
/// ausgewertet wird auf dem Server, damit sich Regeln ohne neues Lesezeichen ändern lassen.
String bookmarkletCode(String appOrigin) {
  final script =
      '''
(()=>{const A=${jsonEncode(appOrigin)};const r=[];let k='cardmarket';
const T=(e,s)=>{const x=e.querySelector(s);return x?x.textContent.trim().replace(/\\s+/g,' '):''};
if(/(^|\\.)ebay\\./.test(location.hostname)){k='ebay';
document.querySelectorAll('li.s-item,li.s-card').forEach(e=>{
const t=T(e,'.s-item__title,.s-card__title');const p=T(e,'.s-item__price,.s-card__price');
if(!t||!p||/^Shop on eBay/i.test(t))return;
const m=(e.innerText||'').match(/(Verkauft|Sold)[^\\n]*/);const a=e.querySelector('a[href*="/itm/"]');
r.push({title:t.slice(0,300),price:p.slice(0,80),sold:m?m[0].slice(0,120):'',url:a?a.href.split('?')[0]:''})})}
else{document.querySelectorAll('[id^="articleRow"],.article-row').forEach(e=>{
const c=e.querySelector('.article-condition');const p=e.querySelector('.price-container');
if(!c||!p)return;const l=[];
e.querySelectorAll('.product-attributes [aria-label],.product-attributes [data-bs-original-title],.product-attributes [data-original-title],.product-attributes [title]').forEach(x=>{
const t=x.getAttribute('aria-label')||x.getAttribute('data-bs-original-title')||x.getAttribute('data-original-title')||x.getAttribute('title');
if(t&&l.indexOf(t)<0)l.push(t.slice(0,80))});
r.push({condition:c.textContent.trim().split(/\\s+/)[0],price:p.textContent.trim().slice(0,40),labels:l.slice(0,12)})})}
if(!r.length){alert('Kartenkiste: Keine Angebote oder Verkäufe gefunden. Bitte die Seite ganz laden und erneut tippen.');return}
const m=location.hash.match(/kartenkiste=([0-9a-f-]+)/);
const d={c:m?m[1]:null,u:location.href.split('#')[0],r:r.slice(0,k==='ebay'?120:60)};
const b=btoa(unescape(encodeURIComponent(JSON.stringify(d)))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+\$/,'');
location.href=A+'/#/'+k+'-import?d='+b})();''';
  return 'javascript:${script.replaceAll('\n', '')}';
}

/// Inhalt des Lesezeichens (Base64url-JSON aus dem Parameter `d`): Karten-ID (falls die
/// Seite aus Kartenkiste geöffnet wurde), Seitenadresse und Rohzeilen der Seite.
class BookmarkletPayload {
  const BookmarkletPayload({required this.pageUrl, required this.rows, this.cardId});

  final String? cardId;
  final String pageUrl;
  final List<Json> rows;

  List<CardmarketOfferRow> get offerRows => [
    for (final row in rows) CardmarketOfferRow.fromJson(row),
  ];

  static BookmarkletPayload? decode(String? data) {
    if (data == null || data.isEmpty) return null;
    try {
      final json = jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(data))));
      if (json is! Map<String, Object?>) return null;
      final rows = json['r'];
      final url = json['u'];
      if (rows is! List || url is! String) return null;
      return BookmarkletPayload(
        cardId: json['c'] is String ? json['c']! as String : null,
        pageUrl: url,
        rows: [
          for (final row in rows)
            if (row is Map<String, Object?>) row,
        ],
      );
    } on FormatException {
      return null;
    }
  }
}

class CardmarketImportScreen extends ConsumerStatefulWidget {
  const CardmarketImportScreen({required this.data, super.key});

  final String? data;

  @override
  ConsumerState<CardmarketImportScreen> createState() => _CardmarketImportScreenState();
}

class _CardmarketImportScreenState extends ConsumerState<CardmarketImportScreen> {
  late final BookmarkletPayload? _payload = BookmarkletPayload.decode(widget.data);
  String? _cardId;
  Future<CardmarketOffersResult>? _preview;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _cardId = _payload?.cardId;
    _loadPreview();
  }

  void _loadPreview() {
    final payload = _payload;
    final cardId = _cardId;
    if (payload == null || cardId == null) return;
    _preview = ref
        .read(apiProvider)
        .cardmarketOffers(cardId, pageUrl: payload.pageUrl, rows: payload.offerRows);
  }

  Future<void> _save() async {
    final payload = _payload!;
    setState(() => _saving = true);
    final ok = await runAction(context, () async {
      await ref
          .read(apiProvider)
          .cardmarketOffers(
            _cardId!,
            pageUrl: payload.pageUrl,
            rows: payload.offerRows,
            save: true,
          );
    });
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) {
      ref.invalidate(pricesProvider(_cardId!));
      showMessage(context, 'Cardmarket-Preise gespeichert.');
      context.go('/card/$_cardId');
    }
  }

  @override
  Widget build(BuildContext context) {
    final payload = _payload;
    return Scaffold(
      appBar: AppBar(title: const Text('Cardmarket-Angebote')),
      body: payload == null
          ? const EmptyView(
              icon: Icons.link_off,
              message: 'Keine gültigen Daten vom Lesezeichen erhalten.',
            )
          : _cardId == null
          ? CardPicker(
              onPicked: (id) => setState(() {
                _cardId = id;
                _loadPreview();
              }),
            )
          : FutureBuilder<CardmarketOffersResult>(
              future: _preview,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return ErrorView(message: '${snapshot.error}');
                }
                final result = snapshot.data;
                if (result == null) return const Center(child: CircularProgressIndicator());
                return _PreviewView(
                  cardId: _cardId!,
                  result: result,
                  saving: _saving,
                  onSave: result.prices.isEmpty ? null : _save,
                );
              },
            ),
    );
  }
}

class _PreviewView extends ConsumerWidget {
  const _PreviewView({
    required this.cardId,
    required this.result,
    required this.saving,
    required this.onSave,
  });

  final String cardId;
  final CardmarketOffersResult result;
  final bool saving;
  final VoidCallback? onSave;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(cardProvider(cardId)).value;
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        if (card != null) CardTile(card: card),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text(
            '${result.accepted} passende Angebote ausgelesen, '
            '${result.skipped} übersprungen (andere Sprache, signiert, …).',
            style: const TextStyle(color: AppColors.textMuted),
          ),
        ),
        for (final warning in result.warnings)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(warning, style: const TextStyle(color: AppColors.warning)),
          ),
        if (result.prices.isNotEmpty) const SectionTitle('Preise je Zustand'),
        for (final price in result.prices)
          ListTile(
            dense: true,
            title: Text(
              '${price.condition} · ${conditionLabels[price.condition] ?? ''}'
              '${price.variant == 'reverse' ? ' · Reverse Holo' : ''}',
            ),
            subtitle: Text('${price.offers} Angebote · Ø 3 günstigste ${money(price.low3)}'),
            trailing: Text('ab ${money(price.low)}', style: const TextStyle(fontSize: 16)),
          ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            onPressed: saving ? null : onSave,
            icon: const Icon(Icons.save),
            label: const Text('Preise speichern'),
          ),
        ),
      ],
    );
  }
}

/// Karte wählen, wenn das Lesezeichen keine Karten-ID mitgebracht hat.
class CardPicker extends ConsumerStatefulWidget {
  const CardPicker({required this.onPicked, super.key});

  final ValueChanged<String> onPicked;

  @override
  ConsumerState<CardPicker> createState() => _CardPickerState();
}

class _CardPickerState extends ConsumerState<CardPicker> {
  final _query = TextEditingController();
  Future<List<SearchHit>>? _hits;

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      const Text(
        'Zu welcher Karte gehören die Angebote? '
        '(Tipp: Cardmarket über den Knopf in der Karte öffnen, dann entfällt dieser Schritt.)',
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _query,
        decoration: const InputDecoration(
          labelText: 'Karte suchen',
          prefixIcon: Icon(Icons.search),
        ),
        onSubmitted: (value) =>
            setState(() => _hits = ref.read(apiProvider).search(value, limit: 15)),
      ),
      if (_hits != null)
        FutureBuilder<List<SearchHit>>(
          future: _hits,
          builder: (context, snapshot) => Column(
            children: [
              for (final hit in snapshot.data ?? const <SearchHit>[])
                CardTile(card: hit.card, onTap: () => widget.onPicked(hit.card.id)),
            ],
          ),
        ),
    ],
  );
}

/// Einrichtung des Lesezeichens (in den Einstellungen).
class BookmarkletSetupScreen extends StatelessWidget {
  const BookmarkletSetupScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final code = bookmarkletCode(apiBaseUrl());
    return Scaffold(
      appBar: AppBar(title: const Text('Cardmarket-Lesezeichen')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'Mit diesem Lesezeichen übernimmst du echte Preise in Kartenkiste: die Angebote '
            'von Cardmarket (gefiltert nach Sprache und Zustand) und verkaufte Angebote von '
            'eBay (auch gegradete Karten). Es liest nur die Seite, die du gerade selbst '
            'geöffnet hast.',
          ),
          const SectionTitle('1. Code kopieren'),
          FilledButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: code));
              if (context.mounted) showMessage(context, 'Code kopiert.');
            },
            icon: const Icon(Icons.copy),
            label: const Text('Lesezeichen-Code kopieren'),
          ),
          const SectionTitle('2. Lesezeichen anlegen'),
          const Text(
            'iPhone (Safari): beliebige Seite als Lesezeichen sichern (Teilen → Lesezeichen), '
            'Name „An Kartenkiste senden“. Dann Lesezeichen → Bearbeiten → das neue '
            'Lesezeichen antippen und die Adresse durch den kopierten Code ersetzen.\n\n'
            'Android (Chrome): beliebige Seite als Lesezeichen sichern (⋮ → ☆), dann '
            'Lesezeichen bearbeiten, Name „An Kartenkiste senden“, URL durch den Code '
            'ersetzen. Aufrufen: in der Adresszeile „An Kartenkiste“ tippen und das '
            'Lesezeichen wählen.',
          ),
          const SectionTitle('3. Benutzen'),
          const Text(
            'In einer Karte auf „Cardmarket-Angebote“ oder „Verkaufte Angebote bei eBay“ tippen '
            '→ Seite laden lassen → Lesezeichen „An Kartenkiste senden“ öffnen → Vorschau '
            'prüfen und speichern.\n\n'
            'Auf dem iPhone öffnet sich Kartenkiste dabei in Safari: dort einmal anmelden.',
          ),
          const SectionTitle('Code'),
          SelectableText(code, style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
        ],
      ),
    );
  }
}
