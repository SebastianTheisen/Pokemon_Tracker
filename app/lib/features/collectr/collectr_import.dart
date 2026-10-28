// Collectr-Showcase übernehmen: Vorschau der Karten aus dem Lesezeichen, Zuordnung prüfen,
// in einen Ordner übernehmen.
//
// Das Lesezeichen „An Kartenkiste senden“ liest auf app.getcollectr.com die Kacheln des
// gewählten Portfolios und öffnet /#/collectr-import?d=<Daten> (Base64url-JSON: Portfolio
// `p`, Seitenadresse `u`, Kacheln `r` als Textzeilen). Der Server ordnet zu; gespeichert wird
// erst nach Bestätigung. Ein zweiter Durchlauf legt nichts doppelt an.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../collection/item_sheet.dart' show foldersProvider, gradingCompanies;
import '../dashboard/dashboard_screen.dart' show invalidateCollection;
import '../search/search_screen.dart';

/// Portfolio-Name ohne mitgelesene Bedienelemente
/// („Trainer OrdnerSort by:Best MatchFilters“ → „Trainer Ordner“).
String cleanPortfolio(String text) =>
    text.replaceFirst(RegExp(r'\s*(Sort by|Filters|Sortieren).*$', dotAll: true), '').trim();

/// Inhalt des Lesezeichens für Collectr.
class CollectrPayload {
  const CollectrPayload({required this.rows, this.portfolio});

  final String? portfolio;
  final List<List<String>> rows;

  static CollectrPayload? decode(String? data) {
    if (data == null || data.isEmpty) return null;
    try {
      final json = jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(data))));
      if (json is! Map<String, Object?> || json['r'] is! List) return null;
      final portfolio = json['p'] is String ? cleanPortfolio(json['p']! as String) : '';
      return CollectrPayload(
        portfolio: portfolio.isEmpty ? null : portfolio,
        rows: [
          for (final row in json['r']! as List)
            if (row is List) [for (final line in row) '$line'],
        ],
      );
    } on FormatException {
      return null;
    }
  }
}

/// Auswahl je Kachel: übernehmen? welche Karte? Slab-Angaben.
class _Choice {
  _Choice({required this.card, required this.selected});

  CardInfo? card;
  bool selected;
  String? company;
  String? grade;
}

class CollectrImportScreen extends ConsumerStatefulWidget {
  const CollectrImportScreen({required this.data, super.key});

  final String? data;

  @override
  ConsumerState<CollectrImportScreen> createState() => _CollectrImportScreenState();
}

class _CollectrImportScreenState extends ConsumerState<CollectrImportScreen> {
  late final CollectrPayload? _payload = CollectrPayload.decode(widget.data);
  late final _folder = TextEditingController(text: _payload?.portfolio ?? 'Collectr');
  CollectrPreview? _preview;
  final _choices = <int, _Choice>{};
  String? _error;
  bool _saving = false;
  CollectrCommitResult? _result;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _folder.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final payload = _payload;
    if (payload == null) return;
    try {
      final preview = await ref
          .read(apiProvider)
          .collectrPreview(rows: payload.rows, portfolio: payload.portfolio);
      if (!mounted) return;
      setState(() {
        _preview = preview;
        for (final row in preview.rows) {
          _choices[row.index] = _Choice(
            card: row.matches.firstOrNull,
            selected: row.status == 'matched',
          );
        }
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  List<CollectrRow> _rows(String status) =>
      _preview?.rows.where((row) => row.status == status).toList() ?? const [];

  bool _ready(CollectrRow row) {
    final choice = _choices[row.index]!;
    return choice.card != null && (!row.graded || choice.grade != null);
  }

  Iterable<CollectrRow> get _toImport => (_preview?.rows ?? const <CollectrRow>[]).where(
    (row) => _choices[row.index]!.selected && _ready(row),
  );

  /// Kacheln, die der Server nicht als Karte lesen konnte (keine Kartennummer).
  List<String> get _unreadTiles {
    final read = {for (final row in _preview?.rows ?? const <CollectrRow>[]) row.index};
    return [
      for (final (index, lines) in (_payload?.rows ?? const <List<String>>[]).indexed)
        if (!read.contains(index)) lines.isEmpty ? '(leere Kachel)' : lines.first,
    ];
  }

  /// Alles, was beim Übernehmen *nicht* mitkommt – nichts soll still verloren gehen.
  List<String> _leftOut() => [
    for (final row in _preview?.rows ?? const <CollectrRow>[])
      if (!(_choices[row.index]!.selected && _ready(row)))
        '${row.quantity}× ${row.name} · ${row.setName} · ${row.number ?? '–'} '
            '(${_choices[row.index]!.card == null
                ? 'keine Karte gewählt'
                : row.graded && _choices[row.index]!.grade == null
                ? 'Note fehlt'
                : 'abgewählt'})',
    for (final name in _unreadTiles) '$name (ohne Kartennummer)',
  ];

  List<String> _notImported = const [];

  int get _missingGrades => (_preview?.rows ?? const <CollectrRow>[])
      .where(
        (row) => row.graded && _choices[row.index]!.selected && _choices[row.index]!.grade == null,
      )
      .length;

  void _gradeAll(String company, String grade) => setState(() {
    for (final row in _preview!.rows.where((row) => row.graded)) {
      _choices[row.index]!
        ..company = company
        ..grade = grade;
    }
  });

  Future<void> _pick(CollectrRow row) async {
    final card = await showModalBottomSheet<CardInfo>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => SizedBox(
        height: MediaQuery.sizeOf(sheetContext).height * 0.85,
        child: _PickSheet(row: row),
      ),
    );
    if (card != null) {
      setState(() {
        _choices[row.index]!
          ..card = card
          ..selected = true;
      });
    }
  }

  Future<void> _editGrade(CollectrRow row) async {
    final choice = _choices[row.index]!;
    final picked = await showDialog<(String, String)>(
      context: context,
      builder: (_) => _GradeDialog(
        title: row.name,
        company: choice.company ?? 'PSA',
        grade: choice.grade ?? '10',
      ),
    );
    if (picked != null && mounted) {
      setState(() {
        choice
          ..company = picked.$1
          ..grade = picked.$2
          ..selected = true;
      });
    }
  }

  Future<void> _commit() async {
    final rows = _toImport.toList();
    final folderName = _folder.text.trim();
    if (rows.isEmpty || folderName.isEmpty) return;
    setState(() => _saving = true);
    try {
      final result = await ref
          .read(apiProvider)
          .collectrCommit(
            folderName: folderName,
            items: [
              for (final row in rows)
                {
                  'card_id': _choices[row.index]!.card!.id,
                  'quantity': row.quantity,
                  'variant': row.variant,
                  if (!row.graded) 'condition': row.condition ?? 'NM',
                  if (row.graded) 'grading_company': _choices[row.index]!.company ?? 'PSA',
                  if (row.graded) 'grade': _choices[row.index]!.grade,
                },
            ],
          );
      if (!mounted) return;
      invalidateCollection(ref);
      ref.invalidate(foldersProvider);
      setState(() {
        _notImported = _leftOut();
        _result = result;
      });
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final payload = _payload;
    final preview = _preview;
    final result = _result;
    return Scaffold(
      appBar: AppBar(title: const Text('Collectr übernehmen')),
      body: payload == null
          ? const EmptyView(
              icon: Icons.link_off,
              message:
                  'Keine Daten vom Lesezeichen. Bitte das Collectr-Showcase öffnen und das '
                  'Lesezeichen „An Kartenkiste senden“ antippen.',
            )
          : _error != null
          ? EmptyView(icon: Icons.error_outline, message: _error!)
          : preview == null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 12),
                  Text('Ordne ${payload.rows.length} Karten zu …'),
                ],
              ),
            )
          : result != null
          ? _Done(result: result, leftOut: _notImported)
          : _buildPreview(preview),
      bottomNavigationBar: preview == null || result != null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: FilledButton.icon(
                  key: const Key('collectr-commit'),
                  onPressed: _saving || _toImport.isEmpty ? null : _commit,
                  icon: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.library_add),
                  label: Text('${_toImport.length} Karten übernehmen'),
                ),
              ),
            ),
    );
  }

  Widget _buildPreview(CollectrPreview preview) {
    final matched = _rows('matched');
    final check = _rows('check');
    final missing = _rows('missing');
    final graded = preview.rows.where((row) => row.graded).length;
    final unread = _unreadTiles;
    final pieces = preview.rows.fold<int>(0, (sum, row) => sum + row.quantity);
    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: TextField(
            key: const Key('collectr-folder'),
            controller: _folder,
            decoration: const InputDecoration(
              labelText: 'In Ordner',
              helperText: 'Gibt es den Ordner noch nicht, wird er angelegt.',
            ),
            onChanged: (_) => setState(() {}),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text(
            'Gelesen: ${_payload?.rows.length ?? 0} Kacheln · $pieces Stück – bitte mit der '
            'Anzahl in Collectr vergleichen.',
            key: const Key('collectr-total'),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
          child: Text(
            '${matched.length} zugeordnet · ${check.length} bitte prüfen · '
            '${missing.length} nicht gefunden',
            style: TextStyle(color: AppColors.textMuted),
          ),
        ),
        if (graded > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      '$graded gegradete Karten – Firma und Note stehen bei Collectr nur im '
                      'Bild.${_missingGrades > 0 ? ' Bei $_missingGrades fehlt die Note noch.' : ''}',
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton(
                      key: const Key('collectr-grade-all'),
                      onPressed: () => _gradeAll('PSA', '10'),
                      child: const Text('Alle auf PSA 10 setzen'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        if (unread.isNotEmpty) ...[
          SectionTitle('Ohne Kartennummer (${unread.length})'),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'Diese Kacheln konnte Kartenkiste nicht lesen. Bitte von Hand hinzufügen – sie '
              'stehen nach dem Übernehmen noch einmal in der Liste.',
            ),
          ),
          for (final name in unread)
            ListTile(leading: const Icon(Icons.help_outline), title: Text(name)),
        ],
        if (check.isNotEmpty) ...[
          SectionTitle('Bitte prüfen (${check.length})'),
          for (final row in check) _tile(row),
        ],
        if (missing.isNotEmpty) ...[
          SectionTitle('Nicht gefunden (${missing.length})'),
          for (final row in missing) _tile(row),
        ],
        if (matched.isNotEmpty) ...[
          SectionTitle('Zugeordnet (${matched.length})'),
          for (final row in matched) _tile(row),
        ],
      ],
    );
  }

  Widget _tile(CollectrRow row) {
    final choice = _choices[row.index]!;
    final card = choice.card;
    final details = [
      row.setName,
      ?row.number,
      if (row.japanese) 'JP',
      if (row.graded)
        choice.grade == null ? 'Note fehlt' : '${choice.company ?? 'PSA'} ${choice.grade}'
      else
        ?row.condition,
      if (row.variant == 'reverse') 'Reverse',
      '${row.quantity}×',
    ].join(' · ');
    return ListTile(
      key: Key('collectr-row-${row.index}'),
      leading: CardImage(url: card?.image(), width: 40),
      title: Text(row.name),
      subtitle: Text(
        card == null
            ? '$details\nKeine Karte gewählt – antippen zum Suchen'
            : '$details\n→ ${card.displayName} · ${card.subtitle}',
        style: TextStyle(color: AppColors.textMuted),
      ),
      isThreeLine: true,
      trailing: Checkbox(
        value: choice.selected && _ready(row),
        onChanged: card == null
            ? null
            : (value) {
                if (row.graded && choice.grade == null && value == true) {
                  _editGrade(row);
                  return;
                }
                setState(() => choice.selected = value ?? false);
              },
      ),
      onTap: row.graded && card != null ? () => _editGrade(row) : () => _pick(row),
      onLongPress: () => _pick(row),
    );
  }
}

/// Firma und Note eines Slabs (gibt `(Firma, Note)` zurück, `null` bei Abbruch).
class _GradeDialog extends StatefulWidget {
  const _GradeDialog({required this.title, required this.company, required this.grade});

  final String title;
  final String company;
  final String grade;

  @override
  State<_GradeDialog> createState() => _GradeDialogState();
}

class _GradeDialogState extends State<_GradeDialog> {
  late String _company = widget.company;
  late final _grade = TextEditingController(text: widget.grade);

  @override
  void dispose() {
    _grade.dispose();
    super.dispose();
  }

  String get _value => _grade.text.trim().replaceAll(',', '.');

  bool get _valid => RegExp(r'^\d{1,2}(\.\d)?$').hasMatch(_value);

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.title),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _company,
          decoration: const InputDecoration(labelText: 'Firma'),
          items: [for (final c in gradingCompanies) DropdownMenuItem(value: c, child: Text(c))],
          onChanged: (value) => setState(() => _company = value ?? _company),
        ),
        TextField(
          key: const Key('collectr-grade'),
          controller: _grade,
          decoration: const InputDecoration(labelText: 'Note (z. B. 10, 9.5)'),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => setState(() {}),
        ),
      ],
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(
        onPressed: _valid ? () => Navigator.of(context).pop((_company, _value)) : null,
        child: const Text('OK'),
      ),
    ],
  );
}

/// Karte wählen: die Kandidaten des Servers, sonst selbst suchen.
class _PickSheet extends StatelessWidget {
  const _PickSheet({required this.row});

  final CollectrRow row;

  @override
  Widget build(BuildContext context) {
    if (row.matches.isEmpty) {
      return CardSearch(autofocus: true, onSelect: (card) => Navigator.of(context).pop(card));
    }
    return ListView(
      children: [
        SectionTitle('${row.name} · ${row.setName} · ${row.number ?? ''}'),
        for (final card in row.matches)
          ListTile(
            leading: CardImage(url: card.image(), width: 40),
            title: Text(card.displayName),
            subtitle: Text('${card.subtitle} · ${card.language.toUpperCase()}'),
            onTap: () => Navigator.of(context).pop(card),
          ),
        ListTile(
          leading: const Icon(Icons.search),
          title: const Text('Selbst suchen'),
          onTap: () async {
            final navigator = Navigator.of(context);
            final card = await showModalBottomSheet<CardInfo>(
              context: context,
              isScrollControlled: true,
              useSafeArea: true,
              builder: (sheetContext) => SizedBox(
                height: MediaQuery.sizeOf(sheetContext).height * 0.85,
                child: CardSearch(
                  autofocus: true,
                  onSelect: (card) => Navigator.of(sheetContext).pop(card),
                ),
              ),
            );
            if (card != null) navigator.pop(card);
          },
        ),
      ],
    );
  }
}

class _Done extends StatelessWidget {
  const _Done({required this.result, required this.leftOut});

  final CollectrCommitResult result;

  /// Kacheln, die nicht übernommen wurden (zum Nachtragen).
  final List<String> leftOut;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(16),
    children: [
      Icon(Icons.check_circle, size: 56, color: AppColors.gain),
      const SizedBox(height: 12),
      Text(
        '${result.added} Karten in „${result.folder.name}“ übernommen.'
        '${result.skipped > 0 ? ' ${result.skipped} lagen dort schon und wurden übersprungen.' : ''}',
        textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 16),
      ),
      const SizedBox(height: 8),
      Text(
        leftOut.isEmpty
            ? 'Alle gelesenen Karten sind übernommen.'
            : 'Nicht übernommen (${leftOut.length}) – bitte von Hand nachtragen oder den '
                  'Ordner erneut importieren (schon übernommene Karten werden übersprungen):',
        key: const Key('collectr-leftout'),
        textAlign: TextAlign.center,
        style: TextStyle(color: leftOut.isEmpty ? AppColors.gain : AppColors.warning),
      ),
      for (final entry in leftOut)
        ListTile(dense: true, leading: const Icon(Icons.remove_circle_outline), title: Text(entry)),
      const SizedBox(height: 16),
      const Text(
        'Für den nächsten Ordner: in Collectr oben das Portfolio wechseln und das Lesezeichen '
        'erneut antippen.',
        textAlign: TextAlign.center,
      ),
      const SizedBox(height: 12),
      FilledButton(onPressed: () => context.go('/collection'), child: const Text('Zur Sammlung')),
    ],
  );
}
