// Mehr: Profil, Einstellungen (Zustandsfaktoren, Standardsprache), Sitzungen,
// Passwort, Admin-Bereich, Abmelden.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../reports/reports.dart';
import '../auth/auth_screens.dart';

final userSettingsProvider = FutureProvider.autoDispose<UserSettings>(
  (ref) => ref.watch(apiProvider).settings(),
);

final sessionsProvider = FutureProvider.autoDispose<List<SessionInfo>>(
  (ref) => ref.watch(apiProvider).sessions(),
);

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(sessionProvider).value;
    return Scaffold(
      appBar: AppBar(title: const Text('Mehr')),
      body: ListView(
        children: [
          if (user != null)
            ListTile(
              leading: CircleAvatar(
                backgroundColor: AppColors.accent,
                child: Text(user.displayName.isEmpty ? '?' : user.displayName[0].toUpperCase()),
              ),
              title: Text(user.displayName),
              subtitle: Text(user.email),
              trailing: user.isAdmin ? const Tag('Admin', color: AppColors.accent) : null,
              onTap: () => _editName(context, ref, user),
            ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.tune),
            title: const Text('Einstellungen'),
            subtitle: const Text('Zustandsfaktoren, Standardsprache'),
            onTap: () => context.push('/settings'),
          ),
          ListTile(
            key: const Key('more-friends'),
            leading: const Icon(Icons.people_outline),
            title: const Text('Freunde'),
            subtitle: const Text('Freigegebene Sammlungen ansehen'),
            onTap: () => context.push('/friends'),
          ),
          ListTile(
            key: const Key('more-trade'),
            leading: const Icon(Icons.swap_horiz),
            title: const Text('Tausch-Rechner'),
            subtitle: const Text('Wert von Geben und Bekommen vergleichen'),
            onTap: () => context.push('/trade'),
          ),
          ListTile(
            key: const Key('more-report'),
            leading: const Icon(Icons.flag_outlined),
            title: const Text('Etwas fehlt oder ist falsch?'),
            subtitle: const Text('Karte, Produkt oder Daten an den Admin melden'),
            onTap: () => showReportDialog(context, ref),
          ),
          ListTile(
            key: const Key('more-alerts'),
            leading: const Icon(Icons.notifications_outlined),
            title: const Text('Preisalarme'),
            subtitle: const Text('Zielpreise und Mitteilungen aufs Handy'),
            onTap: () => context.push('/alerts'),
          ),
          ListTile(
            leading: const Icon(Icons.layers_outlined),
            title: const Text('Sets in meiner Sammlung'),
            onTap: () => context.push('/sets'),
          ),
          ListTile(
            leading: const Icon(Icons.lock_outline),
            title: const Text('Passwort ändern'),
            onTap: () => _changePassword(context, ref),
          ),
          ListTile(
            leading: const Icon(Icons.devices),
            title: const Text('Angemeldete Geräte'),
            onTap: () => context.push('/sessions'),
          ),
          if (user?.isAdmin ?? false) ...[
            const SectionTitle('Admin'),
            ListTile(
              leading: const Icon(Icons.people_outline),
              title: const Text('Nutzer'),
              onTap: () => context.push('/admin/users'),
            ),
            ListTile(
              leading: const Icon(Icons.mail_outline),
              title: const Text('Einladungen'),
              onTap: () => context.push('/admin/invites'),
            ),
            ListTile(
              key: const Key('more-admin-reports'),
              leading: const Icon(Icons.inbox_outlined),
              title: const Text('Meldungen'),
              subtitle: const Text('Was Freunde vermissen oder als falsch melden'),
              onTap: () => context.push('/admin/reports'),
            ),
          ],
          const Divider(),
          ListTile(
            leading: const Icon(Icons.logout, color: AppColors.loss),
            title: const Text('Abmelden'),
            onTap: () => ref.read(sessionProvider.notifier).logout(),
          ),
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              '$appName · privat, nur für Freunde.\n'
              'Hinweis: Admins können Sammlungen lesend einsehen; jeder Zugriff wird protokolliert.\n'
              'Kartenbilder und -namen gehören den Rechteinhabern (The Pokémon Company). '
              'Preise: TCGdex (Cardmarket, TCGplayer).',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _editName(BuildContext context, WidgetRef ref, User user) async {
    final name = await showTextInput(
      context,
      title: 'Anzeigename',
      initial: user.displayName,
      confirm: 'Speichern',
    );
    if (name == null || name.isEmpty || !context.mounted) return;
    if (await runAction(context, () => ref.read(apiProvider).updateMe(name))) {
      await ref.read(sessionProvider.notifier).refreshUser();
    }
  }

  Future<void> _changePassword(BuildContext context, WidgetRef ref) async {
    final values = await showDialog<(String, String)>(
      context: context,
      builder: (_) => const _PasswordDialog(),
    );
    if (values == null || !context.mounted) return;
    final changed = await runAction(
      context,
      () => ref.read(apiProvider).changePassword(values.$1, values.$2),
    );
    if (changed && context.mounted) {
      // Der Server beendet dabei alle Sitzungen → neu anmelden.
      showMessage(context, 'Passwort geändert – bitte neu anmelden.');
      await ref.read(sessionProvider.notifier).logout();
    }
  }
}

class _PasswordDialog extends StatefulWidget {
  const _PasswordDialog();

  @override
  State<_PasswordDialog> createState() => _PasswordDialogState();
}

class _PasswordDialogState extends State<_PasswordDialog> {
  final _form = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Passwort ändern'),
    content: Form(
      key: _form,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextFormField(
            controller: _current,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Aktuelles Passwort'),
            validator: requiredField,
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _next,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Neues Passwort'),
            validator: passwordField,
          ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(
        onPressed: () {
          if (_form.currentState!.validate()) {
            Navigator.of(context).pop((_current.text, _next.text));
          }
        },
        child: const Text('Ändern'),
      ),
    ],
  );
}

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(userSettingsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Einstellungen')),
      body: AsyncBody(
        value: settings,
        onRetry: () => ref.invalidate(userSettingsProvider),
        builder: (data) => ListView(
          children: [
            const SectionTitle('Standardsprache für die Suche'),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: DropdownButtonFormField<String?>(
                isExpanded: true,
                initialValue: data.defaultLanguage,
                items: [
                  const DropdownMenuItem(child: Text('Alle Sprachen')),
                  for (final entry in languageLabels.entries)
                    DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                ],
                onChanged: (value) async {
                  if (value == null) return;
                  await runAction(
                    context,
                    () => ref.read(apiProvider).updateSettings(defaultLanguage: value),
                  );
                  ref.invalidate(userSettingsProvider);
                },
              ),
            ),
            SectionTitle(
              'Zustandsfaktoren',
              trailing: TextButton(
                onPressed: () async {
                  await runAction(
                    context,
                    () => ref.read(apiProvider).updateSettings(resetFactors: true),
                  );
                  ref.invalidate(userSettingsProvider);
                },
                child: const Text('Zurücksetzen'),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Geschätzter Preis = NM-Basis (Median aus Trend, Ø 7 und Ø 30 Tagen) × Faktor.',
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
            ),
            for (final condition in conditions)
              if (data.conditionFactors[condition] case final factor?)
                ListTile(
                  title: Text('$condition · ${conditionLabels[condition]}'),
                  subtitle: data.customFactors.contains(condition)
                      ? const Text('eigener Wert')
                      : null,
                  trailing: Text(
                    factor.toStringAsFixed(2).replaceAll('.', ','),
                    style: const TextStyle(fontSize: 16),
                  ),
                  onTap: () => _editFactor(context, ref, condition, factor),
                ),
            SectionTitle(
              'Sprachfaktoren',
              trailing: TextButton(
                onPressed: () async {
                  await runAction(
                    context,
                    () => ref.read(apiProvider).updateSettings(resetLanguageFactors: true),
                  );
                  ref.invalidate(userSettingsProvider);
                },
                child: const Text('Zurücksetzen'),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Cardmarket führt westliche Karten aller Sprachen als ein Produkt. Der Faktor '
                'passt die Schätzung an die Sprache der Karte an, z. B. 0,80 für deutsche '
                'Karten. Belegte Angebotspreise (Lesezeichen) bleiben unverändert.',
                style: TextStyle(color: AppColors.textMuted, fontSize: 12),
              ),
            ),
            for (final entry in languageLabels.entries)
              if (data.languageFactors[entry.key] case final factor?)
                ListTile(
                  title: Text(entry.value),
                  subtitle: data.customLanguageFactors.contains(entry.key)
                      ? const Text('eigener Wert')
                      : null,
                  trailing: Text(
                    factor.toStringAsFixed(2).replaceAll('.', ','),
                    style: const TextStyle(fontSize: 16),
                  ),
                  onTap: () => _editLanguageFactor(context, ref, entry.key, entry.value, factor),
                ),
            const SectionTitle('Cardmarket-Angebote übernehmen'),
            ListTile(
              leading: const Icon(Icons.bookmark_add_outlined),
              title: const Text('Lesezeichen einrichten'),
              subtitle: const Text('Echte Angebote nach Sprache und Zustand als Preis speichern'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/settings/bookmarklet'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _editFactor(
    BuildContext context,
    WidgetRef ref,
    String condition,
    double current,
  ) async {
    final value = await showTextInput(
      context,
      title: 'Faktor für $condition',
      initial: current.toStringAsFixed(2).replaceAll('.', ','),
      helper: 'größer als 0, höchstens 3',
      confirm: 'Speichern',
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
    );
    final factor = double.tryParse((value ?? '').replaceAll(',', '.'));
    if (factor == null || !context.mounted) return;
    await runAction(
      context,
      () => ref.read(apiProvider).updateSettings(factors: {condition: factor}),
    );
    ref.invalidate(userSettingsProvider);
  }
}

Future<void> _editLanguageFactor(
  BuildContext context,
  WidgetRef ref,
  String language,
  String label,
  double current,
) async {
  final value = await showTextInput(
    context,
    title: 'Faktor für $label',
    initial: current.toStringAsFixed(2).replaceAll('.', ','),
    helper: 'größer als 0, höchstens 3 (1,00 = Cardmarket-Preis unverändert)',
    confirm: 'Speichern',
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
  );
  final factor = double.tryParse((value ?? '').replaceAll(',', '.'));
  if (factor == null || !context.mounted) return;
  await runAction(
    context,
    () => ref.read(apiProvider).updateSettings(languageFactors: {language: factor}),
  );
  ref.invalidate(userSettingsProvider);
}

class SessionsScreen extends ConsumerWidget {
  const SessionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sessions = ref.watch(sessionsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Angemeldete Geräte')),
      body: AsyncBody(
        value: sessions,
        onRetry: () => ref.invalidate(sessionsProvider),
        builder: (list) => ListView(
          children: [
            for (final session in list)
              ListTile(
                leading: const Icon(Icons.devices),
                title: Text(session.userAgent ?? 'Unbekanntes Gerät', maxLines: 2),
                subtitle: Text('Seit ${dateTime(session.createdAt)}'),
                trailing: IconButton(
                  tooltip: 'Abmelden',
                  icon: const Icon(Icons.logout),
                  onPressed: () async {
                    await runAction(context, () => ref.read(apiProvider).endSession(session.id));
                    ref.invalidate(sessionsProvider);
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
