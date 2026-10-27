// Sets durchblättern (wie „Browse“ bei TCGplayer/Collectr): alle Sets einer Sprache nach Serie,
// mit Logo – antippen öffnet die Set-Seite mit allen Karten.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/images.dart';
import '../../core/games.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

/// Alle Sets einer Sprache, optional nur eines Spiels (`game` = `null`: alle Spiele).
final catalogSetsProvider = FutureProvider.autoDispose
    .family<List<CardSet>, ({String language, String? game})>(
      (ref, key) =>
          cached(ref, ref.watch(apiProvider).catalogSets(language: key.language, game: key.game)),
    );

class SetBrowserScreen extends ConsumerStatefulWidget {
  const SetBrowserScreen({super.key});

  @override
  ConsumerState<SetBrowserScreen> createState() => _SetBrowserScreenState();
}

class _SetBrowserScreenState extends ConsumerState<SetBrowserScreen> {
  String _language = 'de';
  String _filter = '';

  @override
  Widget build(BuildContext context) {
    final game = ref.watch(gameFilterProvider);
    // One Piece gibt es nur auf Englisch und Japanisch – Auswahl passend einschränken.
    final languages = game?.languages ?? languageLabels.keys.toList();
    final language = languages.contains(_language) ? _language : languages.first;
    final key = (language: language, game: game?.id);
    final sets = ref.watch(catalogSetsProvider(key));
    return Scaffold(
      appBar: AppBar(title: const Text('Sets durchblättern')),
      body: Column(
        children: [
          const GameSwitcher(padding: EdgeInsets.fromLTRB(16, 8, 16, 0)),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              key: const Key('set-filter'),
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Set-Name, z. B. „151“ oder „Karmesin“',
                isDense: true,
              ),
              onChanged: (text) => setState(() => _filter = text.trim().toLowerCase()),
            ),
          ),
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final code in languages)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ChoiceChip(
                      key: Key('set-language-$code'),
                      label: Text(languageLabels[code] ?? code),
                      selected: language == code,
                      onSelected: (_) => setState(() => _language = code),
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: AsyncBody(
              value: sets,
              onRetry: () => ref.invalidate(catalogSetsProvider(key)),
              builder: (list) {
                final shown = [
                  for (final set in list)
                    if (_filter.isEmpty ||
                        set.displayName.toLowerCase().contains(_filter) ||
                        set.name.toLowerCase().contains(_filter) ||
                        set.externalId.toLowerCase().contains(_filter))
                      set,
                ];
                if (shown.isEmpty) {
                  return const EmptyView(icon: Icons.layers_clear, message: 'Kein Set gefunden.');
                }
                // Nach Serie gruppiert, Reihenfolge der Liste (neueste zuerst) bleibt.
                final groups = <String, List<CardSet>>{};
                for (final set in shown) {
                  // Bei „Alle“ das Spiel davorschreiben – sonst stünde „Booster“ ohne Bezug da.
                  final series = set.seriesName ?? 'Weitere';
                  final label = game == null && set.game != Game.pokemon.id
                      ? '${Game.fromId(set.game)?.label ?? set.game} · $series'
                      : series;
                  groups.putIfAbsent(label, () => []).add(set);
                }
                return ListView(
                  padding: const EdgeInsets.only(bottom: 24),
                  children: [
                    for (final MapEntry(key: series, value: entries) in groups.entries) ...[
                      SectionTitle(series),
                      for (final set in entries) _SetTile(set: set),
                    ],
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SetTile extends StatelessWidget {
  const _SetTile({required this.set});

  final CardSet set;

  @override
  Widget build(BuildContext context) {
    final details = [
      if (set.releaseDate != null) '${set.releaseDate!.year}',
      if (set.officialCount != null) '${set.officialCount} Karten',
    ].join(' · ');
    final logo = set.logoUrl;
    return ListTile(
      key: Key('browse-set-${set.id}'),
      onTap: () => context.push('/sets/${set.id}'),
      leading: SizedBox(
        width: 72,
        height: 36,
        child: logo == null
            ? Icon(Icons.layers_outlined, color: AppColors.textMuted)
            : Image.network(
                proxiedImageUrl(
                      setLogoUrl(logo),
                      logicalWidth: 72,
                      pixelRatio: MediaQuery.devicePixelRatioOf(context),
                    ) ??
                    setLogoUrl(logo),
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => Icon(Icons.layers_outlined, color: AppColors.textMuted),
              ),
      ),
      title: Text(set.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: details.isEmpty
          ? null
          : Text(details, style: TextStyle(color: AppColors.textMuted)),
      trailing: const Icon(Icons.chevron_right),
    );
  }
}
