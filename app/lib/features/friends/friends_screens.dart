// Freunde: wer etwas freigegeben hat (Showcase) und deren freigegebene Ordner.
//
// Freigeben: Sammlung → Ordner verwalten → Personen-Symbol. Freunde sehen Karten, Zustand
// und Wert – nie Kaufpreise, Notizen oder Gewinn.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../dashboard/dashboard_screen.dart';
import '../trade/trade_screen.dart';

final friendsProvider = FutureProvider.autoDispose<List<Friend>>(
  (ref) => ref.watch(apiProvider).friends(),
);

typedef ShowcaseQuery = ({String userId, String? folderId});

final friendShowcaseProvider = FutureProvider.autoDispose.family<Showcase, ShowcaseQuery>(
  (ref, query) => ref.watch(apiProvider).showcase(query.userId, folderId: query.folderId),
);

class FriendsScreen extends ConsumerWidget {
  const FriendsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final friends = ref.watch(friendsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Freunde'),
        actions: [
          IconButton(
            tooltip: 'Tausch-Rechner',
            onPressed: () => context.push('/trade'),
            icon: const Icon(Icons.swap_horiz),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(friendsProvider),
        child: AsyncBody(
          value: friends,
          onRetry: () => ref.invalidate(friendsProvider),
          builder: (list) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Hier erscheint, wer Ordner für Freunde freigegeben hat. Eigene Ordner gibst du '
                'unter Sammlung → Ordner-Symbol → Personen-Symbol frei.',
                style: TextStyle(color: AppColors.textMuted),
              ),
              const SizedBox(height: 12),
              if (list.isEmpty)
                const EmptyView(
                  icon: Icons.people_outline,
                  message: 'Noch hat niemand etwas freigegeben.',
                ),
              for (final friend in list)
                Card(
                  child: ListTile(
                    key: Key('friend-${friend.userId}'),
                    leading: CircleAvatar(
                      backgroundColor: AppColors.accent,
                      child: Text(
                        friend.displayName.isEmpty ? '?' : friend.displayName[0].toUpperCase(),
                      ),
                    ),
                    title: Text(friend.displayName),
                    subtitle: Text(
                      '${friend.items} Stück · ${friend.folders} Ordner · '
                      '${money(friend.totalValue)}',
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push('/friends/${friend.userId}'),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class ShowcaseScreen extends ConsumerStatefulWidget {
  const ShowcaseScreen({required this.userId, super.key});

  final String userId;

  @override
  ConsumerState<ShowcaseScreen> createState() => _ShowcaseScreenState();
}

class _ShowcaseScreenState extends ConsumerState<ShowcaseScreen> {
  String? _folderId;

  Future<void> _actions(CollectionItem item) async {
    final card = item.card;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SectionTitle(item.title),
            ListTile(
              key: const Key('showcase-trade'),
              leading: const Icon(Icons.swap_horiz),
              title: const Text('Zum Tausch: „Ich bekomme“'),
              onTap: () => Navigator.of(sheetContext).pop('trade'),
            ),
            if (card != null)
              ListTile(
                leading: const Icon(Icons.style),
                title: const Text('Karte ansehen'),
                onTap: () => Navigator.of(sheetContext).pop('open'),
              ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    if (action == 'trade') addItemToTrade(context, ref, item, 'get');
    if (action == 'open' && card != null) await context.push('/card/${card.id}');
  }

  @override
  Widget build(BuildContext context) {
    final showcase = ref.watch(
      friendShowcaseProvider((userId: widget.userId, folderId: _folderId)),
    );
    final draftCount = ref.watch(tradeDraftProvider).length;
    return Scaffold(
      appBar: AppBar(title: Text(showcase.value?.displayName ?? 'Showcase')),
      floatingActionButton: draftCount == 0
          ? null
          : FloatingActionButton.extended(
              key: const Key('showcase-open-trade'),
              onPressed: () => context.push('/trade'),
              icon: const Icon(Icons.swap_horiz),
              label: Text('Tausch ($draftCount)'),
            ),
      body: AsyncBody(
        value: showcase,
        onRetry: () => ref.invalidate(friendShowcaseProvider),
        builder: (data) => CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      money(data.totalValue),
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    if (data.folders.length > 1)
                      Wrap(
                        spacing: 6,
                        children: [
                          for (final folder in [null, ...data.folders])
                            ChoiceChip(
                              avatar: const Icon(Icons.folder, size: 16),
                              label: Text(folder?.name ?? 'Alle'),
                              selected: _folderId == folder?.id,
                              onSelected: (_) => setState(() => _folderId = folder?.id),
                            ),
                        ],
                      ),
                    Text(
                      'Antippen: Karte zum Tausch vormerken.',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 88),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 130,
                  mainAxisSpacing: 16,
                  crossAxisSpacing: 12,
                  childAspectRatio: 0.5,
                ),
                delegate: SliverChildBuilderDelegate(
                  childCount: data.items.length,
                  (context, index) => LayoutBuilder(
                    builder: (context, constraints) => ItemThumb(
                      key: Key('showcase-item-${data.items[index].id}'),
                      item: data.items[index],
                      width: constraints.maxWidth,
                      onTap: () => _actions(data.items[index]),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
