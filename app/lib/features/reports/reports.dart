// „Das fehlt“: fehlende Karten/Produkte oder falsche Daten an die Admins melden.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

const reportKinds = {
  'card': 'Karte fehlt',
  'sealed': 'Produkt fehlt',
  'wrong': 'Daten falsch',
  'other': 'Sonstiges',
};

/// Dialog „Melden“; [kind] und [text] vorbelegt (z. B. die Suchanfrage), [context] für Admins.
Future<void> showReportDialog(
  BuildContext context,
  WidgetRef ref, {
  String kind = 'card',
  String text = '',
  String? reportContext,
}) async {
  final answer = await showDialog<({String kind, String text})>(
    context: context,
    builder: (_) => _ReportDialog(kind: kind, text: text),
  );
  if (answer == null || !context.mounted) return;
  final ok = await runAction(
    context,
    () => ref
        .read(apiProvider)
        .createReport(kind: answer.kind, text: answer.text, context: reportContext),
  );
  if (ok && context.mounted) {
    ref.invalidate(myReportsProvider);
    showMessage(context, 'Danke! Die Meldung ist beim Admin angekommen.');
  }
}

class _ReportDialog extends StatefulWidget {
  const _ReportDialog({required this.kind, required this.text});

  final String kind;
  final String text;

  @override
  State<_ReportDialog> createState() => _ReportDialogState();
}

class _ReportDialogState extends State<_ReportDialog> {
  late String _kind = widget.kind;
  late final _text = TextEditingController(text: widget.text);

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Melden'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              for (final MapEntry(:key, :value) in reportKinds.entries)
                ChoiceChip(
                  key: Key('report-kind-$key'),
                  label: Text(value),
                  selected: _kind == key,
                  onSelected: (_) => setState(() => _kind = key),
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('report-text'),
            controller: _text,
            maxLength: 500,
            maxLines: 4,
            minLines: 2,
            decoration: const InputDecoration(
              labelText: 'Was fehlt bzw. stimmt nicht?',
              hintText: 'z. B. „Mega Evolution Top-Trainer-Box japanisch“',
            ),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(
        key: const Key('report-send'),
        onPressed: () {
          final text = _text.text.trim();
          if (text.length < 3) {
            showMessage(context, 'Bitte kurz beschreiben (mindestens 3 Zeichen).');
            return;
          }
          Navigator.of(context).pop((kind: _kind, text: text));
        },
        child: const Text('Senden'),
      ),
    ],
  );
}

final myReportsProvider = FutureProvider.autoDispose<List<MissingReport>>(
  (ref) => ref.watch(apiProvider).myReports(),
);

final adminReportsProvider = FutureProvider.autoDispose<List<MissingReport>>(
  (ref) => ref.watch(apiProvider).adminReports(),
);

/// Admin: alle Meldungen, offene zuerst; Haken = erledigt.
class AdminReportsScreen extends ConsumerWidget {
  const AdminReportsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reports = ref.watch(adminReportsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Meldungen')),
      body: AsyncBody(
        value: reports,
        onRetry: () => ref.invalidate(adminReportsProvider),
        builder: (list) => list.isEmpty
            ? const EmptyView(icon: Icons.inbox_outlined, message: 'Keine Meldungen.')
            : ListView(
                children: [
                  for (final report in list)
                    CheckboxListTile(
                      key: Key('report-${report.id}'),
                      value: report.done,
                      onChanged: (done) async {
                        if (await runAction(
                          context,
                          () => ref.read(apiProvider).setReportDone(report.id, done: done ?? false),
                        )) {
                          ref.invalidate(adminReportsProvider);
                        }
                      },
                      title: Text(
                        report.text,
                        style: TextStyle(
                          decoration: report.done ? TextDecoration.lineThrough : null,
                          color: report.done ? AppColors.textMuted : null,
                        ),
                      ),
                      subtitle: Text(
                        [
                          reportKinds[report.kind] ?? report.kind,
                          report.reporter,
                          dateTime(report.createdAt),
                          if (report.context case final context?) '„$context“',
                        ].join(' · '),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
