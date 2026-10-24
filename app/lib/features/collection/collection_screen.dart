// Sammlung: Wert und Aufteilung, Ordner, Filter, Sortierung, Positionen bearbeiten.
import '../alerts/alerts_screen.dart';
import '../trade/trade_screen.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/prefs.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../../widgets/range_chips.dart';
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
final folderHistoryProvider = FutureProvider.autoDispose
    .family<CollectionHistory, ({String? folderId, int days})>(
      (ref, key) =>
          ref.watch(apiProvider).collectionHistory(folderId: key.folderId, days: key.days),
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

  /// Mehrfachauswahl (IDs); leer und ohne [_selectMode] = normaler Modus.
  final Set<String> _selected = {};

  /// Auswahl über das Menü gestartet (noch nichts angetippt).
  bool _selectMode = false;

  /// Wertkurve aufgeklappt – zu Beginn zu, damit die Karten sofort sichtbar sind.
  bool _curveOpen = false;

  bool get _selecting => _selectMode || _selected.isNotEmpty;

  void _endSelection() => setState(() {
    _selected.clear();
    _selectMode = false;
  });

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
    _endSelection();
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final summary = ref.watch(folderSummaryProvider(_filter.folderId));
    final items = ref.watch(itemsProvider(_filter));
    final folders = ref.watch(foldersProvider).value ?? const <Folder>[];
    final pageItems = items.value?.items ?? const <CollectionItem>[];
    final listView = ref.watch(uiPrefsProvider.select((prefs) => prefs.listView));
    return PopScope(
      canPop: !_selecting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _endSelection();
      },
      child: Scaffold(
        appBar: _selecting ? _selectionBar(pageItems, folders) : _mainBar(folders),
        body: RefreshIndicator(
          onRefresh: () async => _reload(),
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: summary.maybeWhen(
                  data: (data) => _SummaryHeader(
                    summary: data,
                    curveOpen: _curveOpen,
                    onToggleCurve: () => setState(() => _curveOpen = !_curveOpen),
                  ),
                  orElse: () => const SizedBox(height: 8),
                ),
              ),
              if (_curveOpen) SliverToBoxAdapter(child: _FolderCurve(folderId: _filter.folderId)),
              // Suche und Filter bleiben beim Scrollen oben stehen.
              SliverPersistentHeader(pinned: true, delegate: _PinnedBar(child: _filters(folders))),
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
                    ? [SliverFillRemaining(hasScrollBody: false, child: _empty())]
                    : [
                        if (listView)
                          SliverPadding(
                            padding: const EdgeInsets.only(top: 4, bottom: 24),
                            sliver: SliverList.separated(
                              itemCount: page.items.length,
                              separatorBuilder: (_, _) => const Divider(height: 1, indent: 72),
                              itemBuilder: (context, index) {
                                final item = page.items[index];
                                return _ItemRow(
                                  item: item,
                                  selected: _selecting ? _selected.contains(item.id) : null,
                                  onLongPress: () => _toggle(item),
                                  onTap: _selecting ? () => _toggle(item) : () => _open(item),
                                );
                              },
                            ),
                          )
                        else
                          SliverPadding(
                            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
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
                                      onTap: _selecting ? () => _toggle(item) : () => _open(item),
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
                                style: TextStyle(color: AppColors.textMuted),
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

  /// Wie bei Collectr: Antippen öffnet die Kartenseite (dort bearbeiten, verschieben …).
  /// Versiegeltes hat keine eigene Seite – dort gleich die Aktionen.
  Future<void> _open(CollectionItem item) async {
    if (item.card case final card?) {
      await context.push('/card/${card.id}');
      if (mounted) _reload();
    } else {
      await showItemActions(context, ref, item, _reload, onSelect: () => _toggle(item));
    }
  }

  PreferredSizeWidget _mainBar(List<Folder> folders) => AppBar(
    title: const Text('Sammlung'),
    actions: [
      Tooltip(
        message: 'Sets',
        child: TextButton.icon(
          onPressed: () => context.push('/sets'),
          icon: const Icon(Icons.layers_outlined),
          label: const Text('Sets'),
        ),
      ),
      PopupMenuButton<String>(
        key: const Key('collection-add'),
        tooltip: 'Hinzufügen',
        icon: const Icon(Icons.add),
        onSelected: (path) => path == '/search' ? context.go(path) : context.push(path),
        itemBuilder: (_) => const [
          PopupMenuItem(
            value: '/scan',
            child: ListTile(
              leading: Icon(Icons.document_scanner_outlined),
              title: Text('Karte scannen'),
            ),
          ),
          PopupMenuItem(
            value: '/search',
            child: ListTile(leading: Icon(Icons.search), title: Text('Karte suchen')),
          ),
          PopupMenuItem(
            key: Key('add-sealed'),
            value: '/sealed/add',
            child: ListTile(
              leading: Icon(Icons.inventory_2_outlined),
              title: Text('Versiegeltes'),
              subtitle: Text('Booster, Display, ETB …'),
            ),
          ),
        ],
      ),
      PopupMenuButton<String>(
        key: const Key('collection-more'),
        tooltip: 'Mehr Optionen',
        onSelected: (action) => action == 'folders'
            ? _manageFolders(context, folders)
            : setState(() => _selectMode = true),
        itemBuilder: (_) => const [
          PopupMenuItem(
            value: 'folders',
            child: ListTile(leading: Icon(Icons.folder_outlined), title: Text('Ordner verwalten')),
          ),
          PopupMenuItem(
            key: Key('collection-select'),
            value: 'select',
            child: ListTile(
              leading: Icon(Icons.checklist),
              title: Text('Mehrere auswählen'),
              subtitle: Text('auch per langem Druck auf eine Karte'),
            ),
          ),
        ],
      ),
    ],
  );

  PreferredSizeWidget _selectionBar(List<CollectionItem> pageItems, List<Folder> folders) => AppBar(
    leading: IconButton(
      tooltip: 'Auswahl beenden',
      onPressed: _endSelection,
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
        onPressed: _selected.isEmpty ? null : () => _bulk('move', folders),
        icon: const Icon(Icons.drive_file_move_outline),
      ),
      IconButton(
        key: const Key('bulk-copy'),
        tooltip: 'In Ordner kopieren',
        onPressed: _selected.isEmpty ? null : () => _bulk('copy', folders),
        icon: const Icon(Icons.copy_all_outlined),
      ),
      IconButton(
        key: const Key('bulk-delete'),
        tooltip: 'Entfernen',
        onPressed: _selected.isEmpty ? null : () => _bulk('delete', folders),
        icon: const Icon(Icons.delete_outline),
      ),
    ],
  );

  Widget _empty() {
    final filtered = _filter.query.isNotEmpty || _filter.kind != null || _filter.extraCount > 0;
    if (filtered) {
      return EmptyView(
        icon: Icons.search_off,
        message: 'Nichts gefunden – Suche oder Filter lockern.',
        action: OutlinedButton(
          key: const Key('collection-clear-filter'),
          onPressed: () => setState(() => _filter = ItemFilter(folderId: _filter.folderId)),
          child: const Text('Filter zurücksetzen'),
        ),
      );
    }
    return EmptyView(
      icon: Icons.collections_bookmark_outlined,
      message:
          'Noch nichts hier. Scanne eine Karte, füge sie über die Suche hinzu oder lege '
          'Versiegeltes über „+“ oben an.',
      action: FilledButton.icon(
        onPressed: () => context.push('/scan'),
        icon: const Icon(Icons.document_scanner),
        label: const Text('Karte scannen'),
      ),
    );
  }

  Future<void> _openFilter() async {
    final filter = await showItemFilterSheet(context, _filter);
    if (filter != null && mounted) setState(() => _filter = filter);
  }

  /// Suche plus eine Zeile beschrifteter Schalter: Filter, Sortierung, Ordner, Art.
  Widget _filters(List<Folder> folders) {
    final folderName = folders.where((f) => f.id == _filter.folderId).firstOrNull?.name;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 6, 16, 2),
          child: TextField(
            key: const Key('collection-search'),
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'In der Sammlung suchen',
              isDense: true,
            ),
            textInputAction: TextInputAction.search,
            onSubmitted: (query) => setState(() => _filter = _filter.copyWith(query: query.trim())),
          ),
        ),
        SizedBox(
          height: 48,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            children: [
              _gap(_viewToggle()),
              _gap(
                Badge(
                  isLabelVisible: _filter.extraCount > 0,
                  label: Text('${_filter.extraCount}'),
                  child: ActionChip(
                    key: const Key('collection-filter'),
                    tooltip: 'Filter (Sprache, Zustand, Wert, Kaufpreis)',
                    avatar: const Icon(Icons.tune, size: 18),
                    label: const Text('Filter'),
                    onPressed: _openFilter,
                  ),
                ),
              ),
              _gap(
                PopupMenuButton<String>(
                  key: const Key('collection-sort'),
                  tooltip: 'Sortieren',
                  initialValue: _filter.sort,
                  onSelected: (sort) => setState(() => _filter = _filter.copyWith(sort: sort)),
                  itemBuilder: (_) => [
                    for (final entry in sortLabels.entries)
                      PopupMenuItem(value: entry.key, child: Text(entry.value)),
                  ],
                  child: Chip(
                    avatar: const Icon(Icons.swap_vert, size: 18),
                    label: Text('${sortLabels[_filter.sort] ?? 'Sortieren'} ▾'),
                  ),
                ),
              ),
              if (folders.length > 1)
                _gap(
                  PopupMenuButton<String>(
                    key: const Key('collection-folder'),
                    tooltip: 'Ordner',
                    onSelected: (id) => id == '_manage'
                        ? _manageFolders(context, folders)
                        : setState(
                            () => _filter = _filter.copyWith(folderId: id.isEmpty ? null : id),
                          ),
                    itemBuilder: (_) => [
                      const PopupMenuItem(value: '', child: Text('Alle Ordner')),
                      for (final folder in folders)
                        PopupMenuItem(
                          key: Key('collection-folder-${folder.id}'),
                          value: folder.id,
                          child: Text(folder.name),
                        ),
                      const PopupMenuDivider(),
                      const PopupMenuItem(value: '_manage', child: Text('Ordner verwalten …')),
                    ],
                    child: Chip(
                      avatar: const Icon(Icons.folder_outlined, size: 18),
                      backgroundColor: folderName == null
                          ? null
                          : AppColors.accent.withValues(alpha: 0.2),
                      label: Text('${folderName ?? 'Alle Ordner'} ▾'),
                    ),
                  ),
                ),
              const VerticalDivider(indent: 6, endIndent: 6),
              for (final kind in [null, ...kindLabels.keys])
                _gap(
                  ChoiceChip(
                    label: Text(kind == null ? 'Alle' : kindLabels[kind]!),
                    selected: _filter.kind == kind,
                    onSelected: (_) => setState(() => _filter = _filter.copyWith(kind: kind)),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  /// Raster (Bilder) oder Liste (mehr auf einen Blick) – merkt sich die Wahl auf dem Gerät.
  Widget _viewToggle() {
    final listView = ref.watch(uiPrefsProvider.select((prefs) => prefs.listView));
    return IconButton.outlined(
      key: const Key('collection-view'),
      tooltip: listView ? 'Als Raster zeigen' : 'Als Liste zeigen',
      visualDensity: VisualDensity.compact,
      onPressed: () => ref.read(uiPrefsProvider.notifier).setListView(value: !listView),
      icon: Icon(listView ? Icons.grid_view : Icons.view_list),
    );
  }

  static Widget _gap(Widget child) =>
      Padding(padding: const EdgeInsets.symmetric(horizontal: 4), child: child);

  Future<void> _manageFolders(BuildContext context, List<Folder> folders) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _FolderManager(),
    );
    _reload();
  }
}

/// Feste Leiste (Suche + Schalter), die beim Scrollen oben stehen bleibt.
class _PinnedBar extends SliverPersistentHeaderDelegate {
  _PinnedBar({required this.child});

  final Widget child;

  static const _height = 106.0;

  @override
  double get minExtent => _height;

  @override
  double get maxExtent => _height;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) => Material(
    color: Theme.of(context).scaffoldBackgroundColor,
    elevation: overlapsContent || shrinkOffset > 0 ? 2 : 0,
    // Muss die feste Höhe ganz ausfüllen (sonst ungültige Sliver-Geometrie).
    child: SizedBox.expand(
      child: ClipRect(child: Center(child: child)),
    ),
  );

  @override
  bool shouldRebuild(_PinnedBar oldDelegate) => true;
}

/// Eine Zeile: Wert, Veränderung, Anzahl – antippen klappt die Wertkurve auf.
class _SummaryHeader extends StatelessWidget {
  const _SummaryHeader({
    required this.summary,
    required this.curveOpen,
    required this.onToggleCurve,
  });

  final CollectionSummary summary;
  final bool curveOpen;
  final VoidCallback onToggleCurve;

  @override
  Widget build(BuildContext context) {
    final change = parseAmount(summary.changeSinceAdded) ?? 0;
    return InkWell(
      key: const Key('toggle-curve'),
      onTap: onToggleCurve,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 8, 4),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
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
                  Text(
                    [
                      '${summary.items} ${summary.items == 1 ? 'Karte' : 'Karten'}',
                      if (summary.hasProfit)
                        'Gewinn ${profitText(summary.profit, summary.profitPercent)}',
                    ].join(' · '),
                    key: const Key('collection-profit'),
                    style: TextStyle(
                      color: summary.hasProfit ? profitColor(summary.profit) : AppColors.textMuted,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            Column(
              children: [
                Icon(curveOpen ? Icons.expand_less : Icons.show_chart, color: AppColors.textMuted),
                Text(
                  curveOpen ? 'Zuklappen' : 'Verlauf',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 11),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Listenansicht: kleines Bild, Name, Set und Fassung, Wert und Gewinn.
class _ItemRow extends StatelessWidget {
  const _ItemRow({required this.item, required this.onTap, this.onLongPress, this.selected});

  final CollectionItem item;
  final VoidCallback onTap;
  final VoidCallback? onLongPress;

  /// Auswahlmodus: Haken bzw. Kreis; `null` = kein Auswahlmodus.
  final bool? selected;

  @override
  Widget build(BuildContext context) {
    final value = item.value;
    final profit = value.profit;
    return ListTile(
      key: Key('item-row-${item.id}'),
      onTap: onTap,
      onLongPress: onLongPress,
      leading: switch (selected) {
        final isSelected? => Icon(
          isSelected ? Icons.check_circle : Icons.radio_button_unchecked,
          color: isSelected ? AppColors.primary : AppColors.textMuted,
        ),
        null => CardImage(url: item.image, width: 40, contain: item.card == null),
      },
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
        [if (item.card != null) item.card!.subtitle, item.label].join(' · '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(color: AppColors.textMuted),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(value.totalValue), style: const TextStyle(fontWeight: FontWeight.w700)),
          if (profit != null)
            Text(signedMoney(profit), style: TextStyle(color: profitColor(profit), fontSize: 12)),
        ],
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
        style: TextStyle(color: AppColors.textMuted),
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
  bool showOpen = true,
}) async {
  final action = await showModalBottomSheet<String>(
    context: context,
    builder: (_) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showOpen && item.card != null)
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
          ListTile(
            key: const Key('item-trade'),
            leading: const Icon(Icons.swap_horiz),
            title: const Text('Zum Tausch geben'),
            onTap: () => Navigator.of(context).pop('trade'),
          ),
          if (item.kind != 'graded')
            ListTile(
              key: const Key('item-alert'),
              leading: const Icon(Icons.add_alert_outlined),
              title: const Text('Preisalarm'),
              onTap: () => Navigator.of(context).pop('alert'),
            ),
          ListTile(
            leading: Icon(Icons.delete_outline, color: AppColors.loss),
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
  } else if (action == 'trade') {
    addItemToTrade(context, ref, item, 'give');
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
                      key: Key('share-${folder.id}'),
                      tooltip: folder.shared
                          ? 'Für Freunde sichtbar – antippen für privat'
                          : 'Privat – antippen, um ihn Freunden zu zeigen',
                      isSelected: folder.shared,
                      icon: const Icon(Icons.people_outline),
                      selectedIcon: Icon(Icons.people, color: AppColors.gain),
                      onPressed: () async {
                        final ok = await runAction(
                          context,
                          () => api.shareFolder(folder.id, shared: !folder.shared),
                        );
                        if (!ok || !context.mounted) return;
                        ref.invalidate(foldersProvider);
                        showMessage(
                          context,
                          folder.shared
                              ? '„${folder.name}“ ist wieder privat.'
                              : '„${folder.name}“ ist für Freunde sichtbar (ohne Kaufpreise '
                                    'und Notizen).',
                        );
                      },
                    ),
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
              Padding(
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
class _FolderCurve extends ConsumerStatefulWidget {
  const _FolderCurve({required this.folderId});

  final String? folderId;

  @override
  ConsumerState<_FolderCurve> createState() => _FolderCurveState();
}

class _FolderCurveState extends ConsumerState<_FolderCurve> {
  ChartRange _range = ChartRange.quarter;

  @override
  Widget build(BuildContext context) {
    final history = ref.watch(
      folderHistoryProvider((folderId: widget.folderId, days: _range.days)),
    );
    final points = [
      for (final point in history.value?.points ?? const <ValuePoint>[])
        ChartPoint(point.date, parseAmount(point.totalValue) ?? 0),
    ];
    // Erst ab zwei Tageswerten – im kürzesten Zeitraum trotzdem die Auswahl zeigen.
    if (points.length < 2 && _range == ChartRange.quarter) return const SizedBox.shrink();
    return Padding(
      key: const Key('folder-curve'),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ValueChart(height: 90, emptyHint: false, points: points),
          Row(
            children: [
              Expanded(
                child: RangeChange(points: points, range: _range),
              ),
            ],
          ),
          RangeChips(value: _range, onChanged: (range) => setState(() => _range = range)),
        ],
      ),
    );
  }
}
