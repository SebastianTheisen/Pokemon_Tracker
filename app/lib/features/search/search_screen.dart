// Suche: Name (DE/EN gemischt, tippfehlertolerant) und/oder Nummer, z. B. „nachtara 215“.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

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
            onSubmitted: (text) => setState(() => _query = (text: text, language: _query.language)),
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
                    label: Text(language == null ? 'Alle' : languageTag(language)),
                    selected: _query.language == language,
                    onSelected: (_) => _setLanguage(language),
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: _query.text.trim().isEmpty
              ? const EmptyView(
                  icon: Icons.search,
                  message: 'Suche nach Name (Deutsch oder Englisch) und/oder Kartennummer.',
                )
              : AsyncBody(
                  value: results,
                  onRetry: () => ref.invalidate(searchProvider(_query)),
                  builder: (hits) => hits.isEmpty
                      ? EmptyView(
                          icon: Icons.search_off,
                          message: 'Keine Treffer.',
                          action: OutlinedButton.icon(
                            onPressed: () => _createCard(context),
                            icon: const Icon(Icons.add),
                            label: const Text('Fehlende Karte anlegen'),
                          ),
                        )
                      : ListView.separated(
                          itemCount: hits.length,
                          separatorBuilder: (_, _) => const Divider(indent: 72),
                          itemBuilder: (context, index) {
                            final card = hits[index].card;
                            return CardTile(
                              card: card,
                              onTap: () => widget.onSelect != null
                                  ? widget.onSelect!(card)
                                  : context.push('/card/${card.id}'),
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
            const Text(
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
