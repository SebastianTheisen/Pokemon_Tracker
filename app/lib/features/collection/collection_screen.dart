// Sammlung: Wert und Aufteilung, Ordner, Filter, Sortierung, Positionen bearbeiten.
import '../alerts/alerts_screen.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/value_chart.dart';
import '../dashboard/dashboard_screen.dart';
import 'item_filter.dart';
import 'item_sheet.dart';

final itemsProvider = FutureProvider.autoDispose.family<ItemPage, ItemFilter>(
  (ref, filter) => ref
      .watch(apiProvider)
      .items(
        folderId: filter.folderId,
        kind: filter.kind,
        query: filter.query,
        sort: filter.sort,
        language: filter.language,
        condition: filter.condition,
        minValue: filter.minValue,
        maxValue: filter.maxValue,
        withPurchase: filter.withPurchase,
      ),
);

/// Wertkurve der ganzen Sammlung (`null`) oder eines Ordners.
final folderHistoryProvider = FutureProvider.autoDispose.family<CollectionHistory, String?>(
  (ref, folderId) => ref.watch(apiProvider).collectionHistory(folderId: folderId),
);

final collectionSetsProvider = FutureProvider.autoDispose<List<SetOverview>>(
  (ref) => ref.watch(apiProvider).collectionSets(),
);

const sortLabels = {
  'value_desc': 'Höchster Wert',
  'profit_desc': 'Höchster Gewinn',
  'profit_asc': 'Größter Verlust',
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
  ItemFilter _filter = const ItemFilter();

  /// Mehrfachauswahl (IDs); leer = normaler Modus.
  final Set<String> _selected = {};

  bool get _selecting => _selected.isNotEmpty;

  void _reload() {
    ref
      ..invalidate(itemsProvider)
      ..invalidate(foldersProvider)
      ..invalidate(folderHistoryProvider)
      ..invalidate(collectionSetsProvider);
    invalidateCollection(ref);
  }

  void _toggle(CollectionItem item) => setState(
    () => _selected.contains(item.id) ? _selected.remove(item.id) : _selected.add(item.id),
  );

  /// Verschieben/Kopieren (mit Zielordner) oder Entfernen der ausgewählten Positionen.
  Future<void> _bulk(String action, List<Folder> folders) async {
    final ids = _selected.toList();
    String? folderId;
    if (action != 'delete') {
      folderId = await _pickFolder(
        context,
        folders,
        title: action == 'move' ? 'Verschieben nach …' : 'Kopieren nach …',
      );
      if (folderId == null) return;
    } else {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('${ids.length} Positionen entfernen?'),
          content: const Text('Die ausgewählten Positionen werden aus der Sammlung entfernt.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Abbrechen'),
            ),
            FilledButton(
              key: const Key('bulk-delete-confirm'),
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Entfernen'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
    }
    if (!mounted) return;
    var count = 0;
    final ok = await runAction(
      context,
      () async => count = await ref.read(apiProvider).bulkItems(ids, action, folderId: folderId),
    );
    if (!ok || !mounted) return;
    final verb = switch (action) {
      'move' => 'verschoben',
      'copy' => 'kopiert',
      _ => 'entfernt',
    };
    showMessage(context, '$count ${count == 1 ? 'Position' : 'Positionen'} $verb');
    setState(_selected.clear);
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final summary = ref.watch(folderSummaryProvider(_filter.folderId));
    final items = ref.watch(itemsProvider(_filter));
    final folders = ref.watch(foldersProvider).value ?? const <Folder>[];
    final pageItems = items.value?.items ?? const <CollectionItem>[];
    return PopScope(
      canPop: !_selecting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) setState(_selected.clear);
      },
      child: Scaffold(
        appBar: _selecting
            ? AppBar(
                leading: IconButton(
                  tooltip: 'Auswahl beenden',
                  onPressed: () => setState(_selected.clear),
                  icon: const Icon(Icons.close),
                ),
                title: Text('${_selected.length} ausgewählt', key: const Key('selection-count')),
                actions: [
                  IconButton(
                    key: const Key('select-all'),
                    tooltip: 'Alle auswählen',
                    onPressed: () => setState(() => _selected.addAll(pageItems.map((i) => i.id))),
                    icon: const Icon(Icons.select_all),
                  ),
                  IconButton(
                    key: const Key('bulk-move'),
                    tooltip: 'In Ordner verschieben',
                    onPressed: () => _bulk('move', folders),
                    icon: const Icon(Icons.drive_file_move_outline),
                  ),
                  IconButton(
                    key: const Key('bulk-copy'),
                    tooltip: 'In Ordner kopieren',
                    onPressed: () => _bulk('copy', folders),
                    icon: const Icon(Icons.copy_all_outlined),
                  ),
                  IconButton(
                    key: const Key('bulk-delete'),
                    tooltip: 'Entfernen',
                    onPressed: () => _bulk('delete', folders),
                    icon: const Icon(Icons.delete_outline),
                  ),
                ],
              )
            : AppBar(
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
                    onSelected: (sort) => setState(() => _filter = _filter.copyWith(sort: sort)),
                    itemBuilder: (_) => [
                      for (final entry in sortLabels.entries)
                        PopupMenuItem(value: entry.key, child: Text(entry.value)),
                    ],
                  ),
                ],
              ),
        // Gut sichtbar statt Symbol in der Kopfzeile: Karten kommen über „Scannen“, Versiegeltes hier.
        floatingActionButton: _selecting
            ? null
            : FloatingActionButton.extended(
                key: const Key('add-sealed'),
                heroTag: 'add-sealed',
                tooltip: 'Versiegeltes hinzufügen (Booster, Display, ETB …)',
                onPressed: () => context.push('/sealed/add'),
                icon: const Icon(Icons.inventory_2_outlined),
                label: const Text('Versiegelt'),
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
              SliverToBoxAdapter(child: _FolderCurve(folderId: _filter.folderId)),
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
                                'Noch nichts hier. Scanne eine Karte, füge sie über die Suche '
                                'hinzu oder lege Versiegeltes an (Knopf unten rechts).',
                            action: FilledButton.icon(
                              onPressed: () => context.push('/scan'),
                              icon: const Icon(Icons.document_scanner),
                              label: const Text('Karte scannen'),
                            ),
                          ),
                        ),
                      ]
                    : [
                        SliverPadding(
                          // unten Platz für den Knopf „Versiegelt“
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                          sliver: SliverGrid(
                            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                              maxCrossAxisExtent: 130,
                              mainAxisSpacing: 16,
                              crossAxisSpacing: 12,
                              childAspectRatio: 0.5, // Bild + Wert + Name ohne Überlauf
                            ),
                            delegate: SliverChildBuilderDelegate(
                              childCount: page.items.length,
                              (context, index) => LayoutBuilder(
                                builder: (context, constraints) {
                                  final item = page.items[index];
                                  return ItemThumb(
                                    item: item,
                                    width: constraints.maxWidth,
                                    selected: _selecting ? _selected.contains(item.id) : null,
                                    onLongPress: () => _toggle(item),
                                    onTap: _selecting
                                        ? () => _toggle(item)
                                        : () => showItemActions(
                                            context,
                                            ref,
                                            item,
                                            _reload,
                                            onSelect: () => _toggle(item),
                                          ),
                                  );
                                },
                              ),
                            ),
                          ),
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
      ),
    );
  }

  Future<void> _openFilter() async {
    final filter = await showItemFilterSheet(context, _filter);
    if (filter != null && mounted) setState(() => _filter = filter);
  }

  Widget _filters(List<Folder> folders) => Column(
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: TextField(
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.search),
            hintText: 'In der Sammlung suchen',
            isDense: true,
            suffixIcon: IconButton(
              key: const Key('collection-filter'),
              tooltip: 'Filter (Sprache, Zustand, Wert, Kaufpreis)',
              onPressed: _openFilter,
              icon: Badge(
                isLabelVisible: _filter.extraCount > 0,
                label: Text('${_filter.extraCount}'),
                child: const Icon(Icons.tune),
              ),
            ),
          ),
          onSubmitted: (query) => setState(() => _filter = _filter.copyWith(query: query.trim())),
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
                  onSelected: (_) => setState(() => _filter = _filter.copyWith(kind: kind)),
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
                    onSelected: (_) =>
                        setState(() => _filter = _filter.copyWith(folderId: folder?.id)),
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
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _valueRow(context, change),
          if (summary.hasProfit)
            Text(
              'Investiert ${money(summary.invested)} · Gewinn '
              '${profitText(summary.profit, summary.profitPercent)}',
              key: const Key('collection-profit'),
              style: TextStyle(color: profitColor(summary.profit), fontSize: 13),
            ),
        ],
      ),
    );
  }

  Widget _valueRow(BuildContext context, double change) => Row(
    crossAxisAlignment: CrossAxisAlignment.end,
    children: [
      // Wert und Veränderung brechen um statt über den Rand zu laufen (schmale Handys).
      Expanded(
        child: Wrap(
          spacing: 10,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: [
            Text(
              money(summary.totalValue),
              style: Theme.of(context).textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            if (change != 0)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  signedMoney(summary.changeSinceAdded),
                  style: TextStyle(color: change > 0 ? AppColors.gain : AppColors.loss),
                ),
              ),
          ],
        ),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text('${summary.items} Karten', style: const TextStyle(color: AppColors.textMuted)),
      ),
    ],
  );
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
      leading: CardImage(url: item.image, width: 40, contain: item.card == null),
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

  Future<void> _edit(BuildContext context, WidgetRef ref) =>
      showItemActions(context, ref, item, onChanged);
}

/// Aktionen einer Position: Karte ansehen, bearbeiten, entfernen.
Future<void> showItemActions(
  BuildContext context,
  WidgetRef ref,
  CollectionItem item,
  VoidCallback onChanged, {
  VoidCallback? onSelect,
}) async {
  final action = await showModalBottomSheet<String>(
    context: context,
    builder: (_) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (item.card != null)
            ListTile(
              leading: const Icon(Icons.style),
              title: Text('${item.title} ansehen'),
              onTap: () => Navigator.of(context).pop('open'),
            ),
          ListTile(
            leading: const Icon(Icons.edit),
            title: const Text('Bearbeiten'),
            onTap: () => Navigator.of(context).pop('edit'),
          ),
          if (item.kind != 'graded')
            ListTile(
              key: const Key('item-alert'),
              leading: const Icon(Icons.add_alert_outlined),
              title: const Text('Preisalarm'),
              onTap: () => Navigator.of(context).pop('alert'),
            ),
          ListTile(
            leading: const Icon(Icons.delete_outline, color: AppColors.loss),
            title: const Text('Entfernen'),
            onTap: () => Navigator.of(context).pop('delete'),
          ),
          if (onSelect != null)
            ListTile(
              key: const Key('item-select'),
              leading: const Icon(Icons.checklist),
              title: const Text('Mehrere auswählen'),
              subtitle: const Text('Verschieben, kopieren oder entfernen – auch per langem Druck'),
              onTap: () => Navigator.of(context).pop('select'),
            ),
        ],
      ),
    ),
  );
  if (!context.mounted) return;
  if (action == 'select') {
    onSelect?.call();
  } else if (action == 'alert') {
    await showAlertSheet(
      context,
      ref,
      card: item.card,
      product: item.product,
      currentValue: item.value.unitValue,
    );
  } else if (action == 'open') {
    await context.push('/card/${item.card!.id}');
  } else if (action == 'edit') {
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
    final summaries = {
      for (final entry in ref.watch(folderSummariesProvider).value ?? const <FolderSummary>[])
        entry.folder.id: entry,
    };
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
                subtitle: switch (summaries[folder.id]) {
                  final entry? => Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: '${entry.items} Stück · ${money(entry.totalValue)}'),
                        if (entry.profitPositions > 0)
                          TextSpan(
                            text: ' · ${profitText(entry.profit, entry.profitPercent)}',
                            style: TextStyle(color: profitColor(entry.profit)),
                          ),
                      ],
                    ),
                    key: Key('folder-summary-${folder.id}'),
                  ),
                  null => null,
                },
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

/// Zielordner wählen (Verschieben/Kopieren).
Future<String?> _pickFolder(BuildContext context, List<Folder> folders, {required String title}) =>
    showModalBottomSheet<String>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SectionTitle(title),
            for (final folder in folders)
              ListTile(
                key: Key('pick-folder-${folder.id}'),
                leading: const Icon(Icons.folder),
                title: Text(folder.name),
                onTap: () => Navigator.of(sheetContext).pop(folder.id),
              ),
            if (folders.length < 2)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Tipp: Weitere Ordner legst du oben über das Ordner-Symbol an.',
                  style: TextStyle(color: AppColors.textMuted),
                ),
              ),
          ],
        ),
      ),
    );

/// Wertkurve der Sammlung bzw. des gewählten Ordners – erst ab zwei Tageswerten.
class _FolderCurve extends ConsumerWidget {
  const _FolderCurve({required this.folderId});

  final String? folderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final points = ref.watch(folderHistoryProvider(folderId)).value?.points ?? const [];
    if (points.length < 2) return const SizedBox.shrink();
    return Padding(
      key: const Key('folder-curve'),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: ValueChart(
        height: 90,
        emptyHint: false,
        points: [
          for (final point in points) ChartPoint(point.date, parseAmount(point.totalValue) ?? 0),
        ],
      ),
    );
  }
}
