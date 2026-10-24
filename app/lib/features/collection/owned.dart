// „Schon in deiner Sammlung“ (Suche, Kartenseite, Scan) und die Ordnerwahl beim Hinzufügen.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import 'item_sheet.dart';

/// Bestand je Karte. Schlüssel: Karten-IDs, mit Komma verbunden (eine Abfrage für eine Liste).
final ownedProvider = FutureProvider.autoDispose.family<Map<String, List<OwnedEntry>>, String>((
  ref,
  key,
) async {
  final ids = key.isEmpty ? const <String>[] : key.split(',');
  final entries = await ref.watch(apiProvider).owned(ids);
  final grouped = <String, List<OwnedEntry>>{};
  for (final entry in entries) {
    grouped.putIfAbsent(entry.cardId, () => []).add(entry);
  }
  return grouped;
});

String ownedKey(Iterable<String> cardIds) => cardIds.toSet().join(',');

int ownedTotal(List<OwnedEntry> entries) =>
    entries.fold(0, (total, entry) => total + entry.quantity);

/// „3× · Sammlung, Binder“
String ownedShort(List<OwnedEntry> entries) {
  final folders = {for (final entry in entries) entry.folderName}.join(', ');
  return '${ownedTotal(entries)}× · $folders';
}

/// Grüne Zeile unter einem Suchtreffer bzw. im Scan-Ergebnis.
class OwnedLine extends StatelessWidget {
  const OwnedLine({required this.entries, super.key});

  final List<OwnedEntry> entries;

  @override
  Widget build(BuildContext context) => Text(
    '✓ In deiner Sammlung: ${ownedShort(entries)}',
    maxLines: 2,
    overflow: TextOverflow.ellipsis,
    style: TextStyle(color: AppColors.gain, fontSize: 12, fontWeight: FontWeight.w600),
  );
}

/// Kartenseite: Bestand je Ordner und Fassung – mit dem Wert, mit dem die Position in der
/// Sammlung zählt. Slabs zählen mit dem Preis ihrer Note, nicht mit dem Rohpreis oben.
class OwnedPanel extends ConsumerWidget {
  const OwnedPanel({required this.cardId, this.onFetchSlabPrice, this.onEdit, super.key});

  final String cardId;

  /// Zeile antippen: diese Position bearbeiten, verschieben, entfernen …
  final void Function(OwnedEntry entry)? onEdit;

  /// „eBay-Verkäufe holen“ für einen Slab ohne Preis (Firma und Note, z. B. „PSA 10“).
  final void Function(String grading)? onFetchSlabPrice;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(ownedProvider(cardId)).value?[cardId] ?? const <OwnedEntry>[];
    if (entries.isEmpty) return const SizedBox.shrink();
    final missing = entries.where((e) => e.isSlab && e.unitValue == null).toList();
    return Container(
      key: const Key('owned-panel'),
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.gain.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.gain.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '✓ In deiner Sammlung: ${ownedTotal(entries)}×',
            style: TextStyle(color: AppColors.gain, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          for (final entry in entries)
            InkWell(
              key: Key('owned-edit-${entry.folderId}-${entry.version}'),
              borderRadius: BorderRadius.circular(8),
              onTap: onEdit == null || entry.itemIds.isEmpty ? null : () => onEdit!(entry),
              child: Padding(
                padding: const EdgeInsets.only(top: 6, bottom: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      entry.isSlab ? Icons.workspace_premium_outlined : Icons.folder_outlined,
                      size: 18,
                      color: AppColors.textMuted,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            [entry.folderName, ?entry.version].join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            entry.unitValue == null
                                ? (entry.isSlab
                                      ? 'Noch kein Preis für ${entry.version} – wird gesucht'
                                      : 'Kein Preis bekannt')
                                : _valueLabel(entry),
                            key: Key('owned-value-${entry.folderId}-${entry.version}'),
                            style: TextStyle(
                              fontSize: 12,
                              color: entry.unitValue == null
                                  ? AppColors.warning
                                  : AppColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          '${entry.quantity}×',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        if (entry.unitValue case final value?)
                          Text(money(value), style: const TextStyle(fontWeight: FontWeight.w700)),
                      ],
                    ),
                    if (onEdit != null)
                      Padding(
                        padding: EdgeInsets.only(left: 4, top: 2),
                        child: Icon(Icons.chevron_right, color: AppColors.textMuted),
                      ),
                  ],
                ),
              ),
            ),
          if (onEdit != null)
            Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'Zeile antippen zum Bearbeiten, Verschieben oder Entfernen.',
                style: TextStyle(color: AppColors.textMuted, fontSize: 11),
              ),
            ),
          if (missing.isNotEmpty && onFetchSlabPrice != null)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                key: const Key('owned-fetch-slab'),
                onPressed: () => onFetchSlabPrice!(missing.first.version!),
                icon: const Icon(Icons.sell_outlined, size: 18),
                label: Text('Preis für ${missing.first.version} aus eBay-Verkäufen holen'),
              ),
            ),
          if (missing.isNotEmpty)
            TextButton.icon(
              key: const Key('owned-reload'),
              onPressed: () => ref.invalidate(ownedProvider),
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Neu laden'),
            ),
        ],
      ),
    );
  }

  /// Klartext statt Rechenweg: „Wert in der Sammlung · Cardmarket, Zustand NM“. Bei Slabs die
  /// Grundlage der Note („PriceCharting PSA 10 (US-Preis umgerechnet)“).
  static String _valueLabel(OwnedEntry entry) {
    final condition = 'Zustand ${entry.condition ?? 'NM'}';
    final source = switch (entry.valueKind) {
      'manual' => 'dein Eigenpreis',
      _ when entry.isSlab => entry.valueBasis ?? entry.valueSource ?? 'Beleg',
      'estimated' => 'Schätzung aus Cardmarket, $condition',
      _ => 'Cardmarket, $condition',
    };
    return 'Wert in der Sammlung · $source';
  }
}

/// Zuletzt gewählter Ordner zum Hinzufügen (`null` = erster Ordner). Gilt app-weit, bis die
/// App geschlossen wird – wer viele Karten in denselben Ordner scannt, wählt ihn einmal.
class FolderChoice extends Notifier<String?> {
  @override
  String? build() => null;

  // ignore: use_setters_to_change_properties – Riverpod-Notifier
  void select(String? folderId) => state = folderId;
}

final folderChoiceProvider = NotifierProvider<FolderChoice, String?>(FolderChoice.new);

/// Gültiger Zielordner: gewählter, sonst der erste (z. B. nach dem Löschen des gewählten).
String? effectiveFolderId(String? chosen, List<Folder> folders) {
  if (folders.isEmpty) return null;
  return folders.any((folder) => folder.id == chosen) ? chosen : folders.first.id;
}

/// „Ordner: Binder ▾“ – nur sichtbar, wenn es mehr als einen Ordner gibt.
class FolderPicker extends ConsumerWidget {
  const FolderPicker({this.value, this.onChanged, super.key});

  /// Eigener Wert (Formular); ohne: die app-weite Wahl ([folderChoiceProvider]).
  final String? value;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final folders = ref.watch(foldersProvider).value ?? const <Folder>[];
    if (folders.length < 2) return const SizedBox.shrink();
    final current = effectiveFolderId(value ?? ref.watch(folderChoiceProvider), folders);
    final name = folders.firstWhere((folder) => folder.id == current).name;
    return PopupMenuButton<String>(
      key: const Key('folder-picker'),
      tooltip: 'Ordner wählen',
      initialValue: current,
      onSelected: (id) {
        ref.read(folderChoiceProvider.notifier).select(id);
        onChanged?.call(id);
      },
      itemBuilder: (_) => [
        for (final folder in folders)
          PopupMenuItem(
            key: Key('folder-option-${folder.id}'),
            value: folder.id,
            child: Text(folder.name),
          ),
      ],
      child: Chip(
        avatar: const Icon(Icons.folder_outlined, size: 18),
        label: Text('Ordner: $name ▾'),
      ),
    );
  }
}
