// Sets durchblättern (wie „Browse“ bei TCGplayer/Collectr): alle Sets einer Sprache nach Serie,
// mit Logo – antippen öffnet die Set-Seite mit allen Karten.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/images.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

final catalogSetsProvider = FutureProvider.autoDispose.family<List<CardSet>, String>(
  (ref, language) => cached(ref, ref.watch(apiProvider).catalogSets(language: language)),
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
    final sets = ref.watch(catalogSetsProvider(_language));
    return Scaffold(
      appBar: AppBar(title: const Text('Sets durchblättern')),
      body: Column(
        children: [
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
                for (final entry in languageLabels.entries)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ChoiceChip(
                      key: Key('set-language-${entry.key}'),
                      label: Text(entry.value),
                      selected: _language == entry.key,
                      onSelected: (_) => setState(() => _language = entry.key),
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: AsyncBody(
              value: sets,
              onRetry: () => ref.invalidate(catalogSetsProvider(_language)),
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
                  groups.putIfAbsent(set.seriesName ?? 'Weitere', () => []).add(set);
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
