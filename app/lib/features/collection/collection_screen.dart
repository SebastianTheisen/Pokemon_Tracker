// Sammlung: Wert und Aufteilung, Ordner, Filter, Sortierung, Positionen bearbeiten.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../dashboard/dashboard_screen.dart';
import 'item_sheet.dart';

typedef ItemFilter = ({String? folderId, String? kind, String query, String sort});

final itemsProvider = FutureProvider.autoDispose.family<ItemPage, ItemFilter>(
  (ref, filter) => ref
      .watch(apiProvider)
      .items(folderId: filter.folderId, kind: filter.kind, query: filter.query, sort: filter.sort),
);

final collectionSetsProvider = FutureProvider.autoDispose<List<SetOverview>>(
  (ref) => ref.watch(apiProvider).collectionSets(),
);

const sortLabels = {
  'value_desc': 'Höchster Wert',
  'added_desc': 'Neueste zuerst',
  'added_asc': 'Älteste zuerst',
  'name': 'Name A–Z',
  'set_number': 'Set und Nummer',
};

const kindLabels = {'raw': 'Roh', 'graded': 'Gegradet', 'sealed': 'Versiegelt'};

class CollectionScreen extends ConsumerStatefulWidget {
  const CollectionScreen({super.key});

  @override
  ConsumerState<CollectionScreen> createState() => _CollectionScreenState();
}

class _CollectionScreenState extends ConsumerState<CollectionScreen> {
  ItemFilter _filter = (folderId: null, kind: null, query: '', sort: 'value_desc');

  void _reload() {
    ref
      ..invalidate(itemsProvider)
      ..invalidate(foldersProvider)
      ..invalidate(collectionSetsProvider);
    invalidateCollection(ref);
  }

  @override
  Widget build(BuildContext context) {
    final summary = ref.watch(dashboardProvider);
    final items = ref.watch(itemsProvider(_filter));
    final folders = ref.watch(foldersProvider).value ?? const <Folder>[];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sammlung'),
        actions: [
          IconButton(
            tooltip: 'Sets',
            onPressed: () => context.push('/sets'),
            icon: const Icon(Icons.layers_outlined),
          ),
          IconButton(
            tooltip: 'Ordner verwalten',
            onPressed: () => _manageFolders(context, folders),
            icon: const Icon(Icons.folder_outlined),
          ),
          PopupMenuButton<String>(
            tooltip: 'Sortieren',
            icon: const Icon(Icons.sort),
            initialValue: _filter.sort,
            onSelected: (sort) => setState(
              () => _filter = (
                folderId: _filter.folderId,
                kind: _filter.kind,
                query: _filter.query,
                sort: sort,
              ),
            ),
            itemBuilder: (_) => [
              for (final entry in sortLabels.entries)
                PopupMenuItem(value: entry.key, child: Text(entry.value)),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: summary.maybeWhen(
                data: (data) => _SummaryHeader(summary: data),
                orElse: () => const SizedBox(height: 8),
              ),
            ),
            SliverToBoxAdapter(child: _filters(folders)),
            ...items.when(
              loading: () => [
                const SliverFillRemaining(child: Center(child: CircularProgressIndicator())),
              ],
              error: (error, _) => [
                SliverFillRemaining(
                  child: ErrorView(message: '$error', onRetry: _reload),
                ),
              ],
              data: (page) => page.items.isEmpty
                  ? [
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: EmptyView(
                          icon: Icons.collections_bookmark_outlined,
                          message:
                              'Noch nichts hier. Scanne eine Karte oder füge sie über '
                              'die Suche hinzu.',
                          action: FilledButton.icon(
                            onPressed: () => context.push('/scan'),
                            icon: const Icon(Icons.document_scanner),
                            label: const Text('Karte scannen'),
                          ),
                        ),
                      ),
                    ]
                  : [
                      SliverList.separated(
                        itemCount: page.items.length,
                        separatorBuilder: (_, _) => const Divider(indent: 72),
                        itemBuilder: (context, index) =>
                            _ItemTile(item: page.items[index], onChanged: _reload),
                      ),
                      if (page.total > page.items.length)
                        SliverToBoxAdapter(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              '${page.items.length} von ${page.total} Positionen – '
                              'Filter oder Suche nutzen.',
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: AppColors.textMuted),
                            ),
                          ),
                        ),
                    ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _filters(List<Folder> folders) => Column(
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.filter_list),
            hintText: 'In der Sammlung suchen',
            isDense: true,
          ),
          onSubmitted: (query) => setState(
            () => _filter = (
              folderId: _filter.folderId,
              kind: _filter.kind,
              query: query.trim(),
              sort: _filter.sort,
            ),
          ),
        ),
      ),
      SizedBox(
        height: 44,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          children: [
            for (final kind in [null, ...kindLabels.keys])
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: ChoiceChip(
                  label: Text(kind == null ? 'Alle' : kindLabels[kind]!),
                  selected: _filter.kind == kind,
                  onSelected: (_) => setState(
                    () => _filter = (
                      folderId: _filter.folderId,
                      kind: kind,
                      query: _filter.query,
                      sort: _filter.sort,
                    ),
                  ),
                ),
              ),
            if (folders.length > 1) ...[
              const VerticalDivider(indent: 8, endIndent: 8),
              for (final folder in [null, ...folders])
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: ChoiceChip(
                    avatar: const Icon(Icons.folder, size: 16),
                    label: Text(folder?.name ?? 'Alle Ordner'),
                    selected: _filter.folderId == folder?.id,
                    onSelected: (_) => setState(
                      () => _filter = (
                        folderId: folder?.id,
                        kind: _filter.kind,
                        query: _filter.query,
                        sort: _filter.sort,
                      ),
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    ],
  );

  Future<void> _manageFolders(BuildContext context, List<Folder> folders) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _FolderManager(),
    );
    _reload();
  }
}

class _SummaryHeader extends StatelessWidget {
  const _SummaryHeader({required this.summary});

  final CollectionSummary summary;

  @override
  Widget build(BuildContext context) {
    final change = parseAmount(summary.changeSinceAdded) ?? 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      money(summary.totalValue),
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    Text(
                      signedMoney(summary.changeSinceAdded),
                      style: TextStyle(color: change >= 0 ? AppColors.gain : AppColors.loss),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('${summary.positions} Positionen · ${summary.items} Stück'),
                  Text(
                    'Roh ${money(summary.raw.value)} · Graded ${money(summary.graded.value)}'
                    '\nVersiegelt ${money(summary.sealed.value)}',
                    textAlign: TextAlign.end,
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ItemTile extends ConsumerWidget {
  const _ItemTile({required this.item, required this.onChanged, this.readOnly = false});

  final CollectionItem item;
  final VoidCallback onChanged;
  final bool readOnly;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = item.value;
    return ListTile(
      onTap: item.card == null ? null : () => context.push('/card/${item.card!.id}'),
      onLongPress: readOnly ? null : () => _edit(context, ref),
      leading: CardImage(url: item.card?.image(), width: 40),
      title: Row(
        children: [
          Flexible(child: Text(item.title, overflow: TextOverflow.ellipsis)),
          if (item.quantity > 1) ...[
            const SizedBox(width: 6),
            Tag('×${item.quantity}', color: AppColors.accent),
          ],
        ],
      ),
      subtitle: Text(
        [
          if (item.card != null) item.card!.subtitle,
          if (item.card != null) languageTag(item.card!.language),
          item.label,
        ].join(' · '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(color: AppColors.textMuted),
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(money(value.totalValue), style: const TextStyle(fontWeight: FontWeight.w600)),
              Text(
                value.kindLabel,
                style: TextStyle(
                  fontSize: 11,
                  color: value.kind == 'estimated'
                      ? AppColors.warning
                      : value.kind == 'none'
                      ? AppColors.loss
                      : AppColors.textMuted,
                ),
              ),
            ],
          ),
          if (!readOnly)
            IconButton(
              tooltip: 'Bearbeiten',
              onPressed: () => _edit(context, ref),
              icon: const Icon(Icons.more_vert),
            ),
        ],
      ),
    );
  }

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit),
              title: const Text('Bearbeiten'),
              onTap: () => Navigator.of(context).pop('edit'),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: AppColors.loss),
              title: const Text('Entfernen'),
              onTap: () => Navigator.of(context).pop('delete'),
            ),
          ],
        ),
      ),
    );
    if (!context.mounted) return;
    if (action == 'edit') {
      if (await showItemSheet(context, item: item) != null) onChanged();
    } else if (action == 'delete') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Position entfernen?'),
          content: Text('„${item.title}“ (${item.label}) wird aus der Sammlung entfernt.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Abbrechen'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Entfernen'),
            ),
          ],
        ),
      );
      if (confirmed != true || !context.mounted) return;
      if (await runAction(context, () => ref.read(apiProvider).deleteItem(item.id))) {
        onChanged();
      }
    }
  }
}

/// Liste der Positionen nur zum Ansehen (Admin-Ansicht fremder Sammlungen).
class ReadOnlyItemTile extends StatelessWidget {
  const ReadOnlyItemTile({required this.item, super.key});

  final CollectionItem item;

  @override
  Widget build(BuildContext context) => _ItemTile(item: item, onChanged: () {}, readOnly: true);
}

class _FolderManager extends ConsumerWidget {
  const _FolderManager();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final folders = ref.watch(foldersProvider);
    final api = ref.read(apiProvider);
    Future<String?> askName(String title, [String initial = '']) =>
        showTextInput(context, title: title, initial: initial);

    return SafeArea(
      child: AsyncBody(
        value: folders,
        builder: (list) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SectionTitle('Ordner'),
            for (final folder in list)
              ListTile(
                leading: const Icon(Icons.folder),
                title: Text(folder.name),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      tooltip: 'Umbenennen',
                      icon: const Icon(Icons.edit),
                      onPressed: () async {
                        final name = await askName('Ordner umbenennen', folder.name);
                        if (name == null || name.isEmpty || !context.mounted) return;
                        await runAction(context, () => api.renameFolder(folder.id, name));
                        ref.invalidate(foldersProvider);
                      },
                    ),
                    if (list.length > 1)
                      IconButton(
                        tooltip: 'Löschen (Inhalt wandert in einen anderen Ordner)',
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () async {
                          final target = list.firstWhere((f) => f.id != folder.id);
                          await runAction(
                            context,
                            () => api.deleteFolder(folder.id, moveTo: target.id),
                          );
                          ref.invalidate(foldersProvider);
                        },
                      ),
                  ],
                ),
              ),
            ListTile(
              leading: const Icon(Icons.create_new_folder_outlined),
              title: const Text('Neuer Ordner'),
              onTap: () async {
                final name = await askName('Neuer Ordner');
                if (name == null || name.isEmpty || !context.mounted) return;
                await runAction(context, () => api.createFolder(name));
                ref.invalidate(foldersProvider);
              },
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}

class SetOverviewScreen extends ConsumerWidget {
  const SetOverviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sets = ref.watch(collectionSetsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Sets')),
      body: AsyncBody(
        value: sets,
        onRetry: () => ref.invalidate(collectionSetsProvider),
        builder: (list) => list.isEmpty
            ? const EmptyView(icon: Icons.layers_outlined, message: 'Noch keine Karten.')
            : ListView.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const Divider(),
                itemBuilder: (context, index) {
                  final entry = list[index];
                  final total = entry.cardSet.officialCount;
                  final progress = total == null || total == 0 ? null : entry.ownedCards / total;
                  return ListTile(
                    title: Text('${entry.cardSet.name} (${languageTag(entry.cardSet.language)})'),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${entry.ownedCards}${total == null ? '' : ' / $total'} Karten · '
                          '${money(entry.value)}',
                        ),
                        if (progress != null) ...[
                          const SizedBox(height: 6),
                          LinearProgressIndicator(value: progress.clamp(0, 1)),
                        ],
                      ],
                    ),
                  );
                },
              ),
      ),
    );
  }
}
