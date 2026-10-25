// Suche: Name (DE/EN gemischt, tippfehlertolerant) und/oder Nummer, z. B. „nachtara 215“.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/prefs.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../collection/item_sheet.dart';
import '../collection/owned.dart';
import '../reports/reports.dart';
import '../dashboard/dashboard_screen.dart';

typedef SearchQuery = ({String text, String? language});

final searchProvider = FutureProvider.autoDispose.family<List<SearchHit>, SearchQuery>(
  (ref, query) => query.text.trim().isEmpty
      ? Future.value(const <SearchHit>[])
      : ref.watch(apiProvider).search(query.text.trim(), language: query.language),
);

/// Suchfeld mit Ergebnisliste. [onSelect] statt Navigation (z. B. im Scanner „Selbst suchen“).
class CardSearch extends ConsumerStatefulWidget {
  const CardSearch({this.onSelect, this.initialLanguage, this.autofocus = false, super.key});

  final void Function(CardInfo card)? onSelect;
  final String? initialLanguage;
  final bool autofocus;

  @override
  ConsumerState<CardSearch> createState() => _CardSearchState();
}

class _CardSearchState extends ConsumerState<CardSearch> {
  final _controller = TextEditingController();
  Timer? _debounce;
  late SearchQuery _query = (text: '', language: widget.initialLanguage);

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(
      const Duration(milliseconds: 350),
      () => setState(() => _query = (text: text, language: _query.language)),
    );
  }

  /// Beispiel antippen: wie getippt, nur ohne Warten.
  void _searchFor(String text) {
    _controller.text = text;
    _debounce?.cancel();
    setState(() => _query = (text: text, language: _query.language));
  }

  void _setLanguage(String? language) =>
      setState(() => _query = (text: _controller.text, language: language));

  @override
  Widget build(BuildContext context) {
    final results = ref.watch(searchProvider(_query));
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: TextField(
            key: const Key('search-field'),
            controller: _controller,
            autofocus: widget.autofocus,
            onChanged: _onChanged,
            onSubmitted: (text) {
              ref.read(uiPrefsProvider.notifier).rememberSearch(text);
              setState(() => _query = (text: text, language: _query.language));
            },
            textInputAction: TextInputAction.search,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Name und/oder Nummer, z. B. „nachtara 215“',
            ),
          ),
        ),
        SizedBox(
          height: 44,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            children: [
              for (final language in [null, ...languageLabels.keys])
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: ChoiceChip(
                    label: Text(
                      language == null ? 'Alle Sprachen' : languageLabels[language] ?? language,
                    ),
                    selected: _query.language == language,
                    onSelected: (_) => _setLanguage(language),
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: _query.text.trim().isEmpty
              ? _StartHint(onExample: _searchFor, showScan: widget.onSelect == null)
              : AsyncBody(
                  value: results,
                  onRetry: () => ref.invalidate(searchProvider(_query)),
                  builder: (hits) => hits.isEmpty
                      ? EmptyView(
                          icon: Icons.search_off,
                          message: 'Keine Treffer.',
                          action: Wrap(
                            alignment: WrapAlignment.center,
                            spacing: 8,
                            children: [
                              OutlinedButton.icon(
                                onPressed: () => _createCard(context),
                                icon: const Icon(Icons.add),
                                label: const Text('Fehlende Karte anlegen'),
                              ),
                              TextButton.icon(
                                key: const Key('search-report'),
                                onPressed: () => showReportDialog(
                                  context,
                                  ref,
                                  text: _query.text.trim(),
                                  reportContext: 'Suche: ${_query.text.trim()}',
                                ),
                                icon: const Icon(Icons.flag_outlined),
                                label: const Text('Dem Admin melden'),
                              ),
                            ],
                          ),
                        )
                      : Consumer(
                          builder: (context, ref, _) {
                            final owned =
                                ref
                                    .watch(ownedProvider(ownedKey(hits.map((h) => h.card.id))))
                                    .value ??
                                const <String, List<OwnedEntry>>{};
                            return ListView.separated(
                              itemCount: hits.length,
                              separatorBuilder: (_, _) => const Divider(indent: 72),
                              itemBuilder: (context, index) {
                                final hit = hits[index];
                                final card = hit.card;
                                final price = _HitPrice(hit: hit);
                                return CardTile(
                                  below: switch (owned[card.id]) {
                                    final entries? => OwnedLine(entries: entries),
                                    null => null,
                                  },
                                  card: card,
                                  onTap: () {
                                    // Wer einen Treffer öffnet, hat gefunden, was er suchte.
                                    ref.read(uiPrefsProvider.notifier).rememberSearch(_query.text);
                                    widget.onSelect != null
                                        ? widget.onSelect!(card)
                                        : context.push('/card/${card.id}');
                                  },
                                  trailing: widget.onSelect == null
                                      ? Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            price,
                                            QuickAddButton(card: card),
                                          ],
                                        )
                                      : price,
                                );
                              },
                            );
                          },
                        ),
                ),
        ),
      ],
    );
  }

  Future<void> _createCard(BuildContext context) async {
    final card = await showDialog<CardInfo>(
      context: context,
      builder: (_) => CreateCardDialog(initialName: _controller.text),
    );
    if (card == null || !context.mounted) return;
    if (widget.onSelect != null) {
      widget.onSelect!(card);
    } else {
      await context.push('/card/${card.id}');
    }
  }
}

/// Preis am Treffer: „87,45 €“ (Beleg) bzw. „≈ 87,45 €“ (Näherung); leer, wenn unbekannt.
class _HitPrice extends StatelessWidget {
  const _HitPrice({required this.hit});

  final SearchHit hit;

  @override
  Widget build(BuildContext context) => hit.price == null
      ? const SizedBox.shrink()
      : Text(
          '${hit.priceEstimated ? '≈ ' : ''}${money(hit.price)}',
          key: Key('hit-price-${hit.card.id}'),
          style: const TextStyle(fontWeight: FontWeight.w700),
        );
}

/// Leere Suche: Beispiele zum Antippen statt einer leeren Fläche – und der Weg zum Scanner.
class _StartHint extends ConsumerWidget {
  const _StartHint({required this.onExample, required this.showScan});

  final ValueChanged<String> onExample;
  final bool showScan;

  static const _examples = ['Glurak', 'Pikachu', 'Mew', 'Nachtara 215', 'Evoli'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recent = ref.watch(uiPrefsProvider.select((prefs) => prefs.recentSearches));
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
      children: [
        if (recent.isNotEmpty) ...[
          Row(
            children: [
              const Expanded(
                child: Text('Zuletzt gesucht', style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              TextButton(
                key: const Key('recent-clear'),
                onPressed: () => ref.read(uiPrefsProvider.notifier).clearSearches(),
                child: const Text('Leeren'),
              ),
            ],
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final query in recent)
                ActionChip(
                  key: Key('recent-$query'),
                  avatar: const Icon(Icons.history, size: 16),
                  label: Text(query),
                  onPressed: () => onExample(query),
                ),
            ],
          ),
          const SizedBox(height: 24),
        ] else ...[
          const SizedBox(height: 16),
          Icon(Icons.search, size: 48, color: AppColors.textMuted),
          const SizedBox(height: 12),
        ],
        Text(
          'Tippe den Namen der Karte – Deutsch oder Englisch. Mit Nummer findest du '
          'genau die richtige.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.textMuted),
        ),
        const SizedBox(height: 16),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final example in _examples)
              ActionChip(
                key: Key('search-example-$example'),
                avatar: const Icon(Icons.north_west, size: 16),
                label: Text(example),
                onPressed: () => onExample(example),
              ),
          ],
        ),
        if (showScan) ...[
          const SizedBox(height: 24),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                key: const Key('search-scan'),
                onPressed: () => context.push('/scan'),
                icon: const Icon(Icons.document_scanner),
                label: const Text('Karte scannen'),
              ),
              OutlinedButton.icon(
                key: const Key('search-browse-sets'),
                onPressed: () => context.push('/sets/browse'),
                icon: const Icon(Icons.layers_outlined),
                label: const Text('Sets durchblättern'),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

class SearchScreen extends StatelessWidget {
  const SearchScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Suche')),
    body: const CardSearch(),
  );
}

/// Karte anlegen, die im Katalog fehlt (für alle sichtbar, Plan 5.1).
class CreateCardDialog extends ConsumerStatefulWidget {
  const CreateCardDialog({this.initialName = '', super.key});

  final String initialName;

  @override
  ConsumerState<CreateCardDialog> createState() => _CreateCardDialogState();
}

class _CreateCardDialogState extends ConsumerState<CreateCardDialog> {
  final _form = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.initialName);
  final _number = TextEditingController();
  final _set = TextEditingController();
  String _language = 'de';
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _number.dispose();
    _set.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    CardInfo? card;
    final ok = await runAction(context, () async {
      card = await ref
          .read(apiProvider)
          .createCard(
            name: _name.text.trim(),
            number: _number.text.trim(),
            language: _language,
            setName: _set.text.trim().isEmpty ? null : _set.text.trim(),
          );
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.of(context).pop(card);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Karte anlegen'),
    content: Form(
      key: _form,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Die Karte ist danach für alle Nutzer sichtbar.',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Name'),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Bitte ausfüllen' : null,
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _number,
              decoration: const InputDecoration(labelText: 'Nummer, z. B. 165/103'),
              validator: (v) => (v ?? '').trim().isEmpty ? 'Bitte ausfüllen' : null,
            ),
            const SizedBox(height: 8),
            TextFormField(
              controller: _set,
              decoration: const InputDecoration(labelText: 'Set (optional)'),
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _language,
              decoration: const InputDecoration(labelText: 'Sprache'),
              items: [
                for (final entry in languageLabels.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) => setState(() => _language = value ?? 'de'),
            ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(onPressed: _busy ? null : _save, child: const Text('Anlegen')),
    ],
  );
}

/// „+“ in der Suche: Tippen fügt 1× Near Mint hinzu (mit „Rückgängig“), langer Druck öffnet
/// das Schnellmenü (Reverse Holo, mit Details, Merkliste).
class QuickAddButton extends ConsumerStatefulWidget {
  const QuickAddButton({required this.card, super.key});

  final CardInfo card;

  @override
  ConsumerState<QuickAddButton> createState() => _QuickAddButtonState();
}

class _QuickAddButtonState extends ConsumerState<QuickAddButton> {
  /// Kurz nach dem Hinzufügen: Häkchen statt Plus (sichtbare Bestätigung).
  bool _done = false;
  Timer? _reset;

  CardInfo get card => widget.card;

  @override
  void dispose() {
    _reset?.cancel();
    super.dispose();
  }

  void _confirm() {
    unawaited(HapticFeedback.mediumImpact());
    setState(() => _done = true);
    _reset?.cancel();
    _reset = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) setState(() => _done = false);
    });
  }

  Future<void> _add(BuildContext context, WidgetRef ref, {String variant = 'normal'}) async {
    final api = ref.read(apiProvider);
    final folders = ref.read(foldersProvider).value ?? const <Folder>[];
    final folderId = effectiveFolderId(ref.read(folderChoiceProvider), folders);
    final folderName = folders.length > 1
        ? folders.firstWhere((folder) => folder.id == folderId).name
        : null;
    CollectionItem? item;
    final ok = await runAction(context, () async {
      item = await api.addItem({
        'card_id': card.id,
        'quantity': 1,
        'condition': 'NM',
        if (variant != 'normal') 'variant': variant,
        'folder_id': ?folderId,
      });
    });
    if (!ok || !context.mounted) return;
    _confirm();
    invalidateCollection(ref);
    final added = item!;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            '${card.displayName}${variant == 'reverse' ? ' (Reverse Holo)' : ''} hinzugefügt'
            '${folderName == null ? '' : ' → $folderName'}',
          ),
          action: SnackBarAction(
            label: 'Rückgängig',
            onPressed: () async {
              await api.deleteItem(added.id);
              invalidateCollection(ref);
            },
          ),
        ),
      );
  }

  Future<void> _menu(BuildContext context, WidgetRef ref) async {
    final hasReverse = card.variants?['reverse'] ?? false;
    final choice = await showModalBottomSheet<String>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SectionTitle(card.displayName),
            ListTile(
              key: const Key('quick-normal'),
              leading: const Icon(Icons.add),
              title: const Text('1× Near Mint hinzufügen'),
              onTap: () => Navigator.of(sheetContext).pop('normal'),
            ),
            if (hasReverse)
              ListTile(
                key: const Key('quick-reverse'),
                leading: const Icon(Icons.auto_awesome),
                title: const Text('1× Reverse Holo hinzufügen'),
                onTap: () => Navigator.of(sheetContext).pop('reverse'),
              ),
            ListTile(
              key: const Key('quick-details'),
              leading: const Icon(Icons.edit_note),
              title: const Text('Mit Details …'),
              subtitle: const Text('Zustand, Anzahl, Kaufpreis, Ordner, Slab'),
              onTap: () => Navigator.of(sheetContext).pop('details'),
            ),
            ListTile(
              key: const Key('quick-wishlist'),
              leading: const Icon(Icons.favorite_border),
              title: const Text('Auf die Merkliste'),
              onTap: () => Navigator.of(sheetContext).pop('wishlist'),
            ),
          ],
        ),
      ),
    );
    if (choice == null || !context.mounted) return;
    switch (choice) {
      case 'details':
        if (await showItemSheet(context, card: card) != null) invalidateCollection(ref);
      case 'wishlist':
        if (await runAction(context, () => ref.read(apiProvider).addToWishlist(cardId: card.id)) &&
            context.mounted) {
          showMessage(context, 'Auf der Merkliste');
        }
      default:
        await _add(context, ref, variant: choice);
    }
  }

  @override
  Widget build(BuildContext context) => Semantics(
    // Eigener Knoten: sonst verschmilzt der Knopf mit der Trefferzeile und ein Tipp auf die
    // Zeile (Bedienungshilfen, Web-Semantik) würde hinzufügen statt die Karte zu öffnen.
    container: true,
    button: true,
    label: '${card.displayName} hinzufügen',
    child: Tooltip(
      message: 'Hinzufügen – lange drücken für mehr',
      child: InkResponse(
        key: Key('quick-add-${card.id}'),
        radius: 24,
        onTap: () => _add(context, ref),
        onLongPress: () => _menu(context, ref),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 250),
            transitionBuilder: (child, animation) =>
                ScaleTransition(scale: animation, child: child),
            child: _done
                ? Icon(Icons.check_circle, key: const ValueKey('done'), color: AppColors.gain)
                : const Icon(
                    Icons.add_circle_outline,
                    key: ValueKey('add'),
                    color: AppColors.primary,
                  ),
          ),
        ),
      ),
    ),
  );
}
