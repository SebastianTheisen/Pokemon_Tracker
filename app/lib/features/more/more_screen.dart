// Mehr: Profil und Gruppen – Sammlung, Freunde, Hilfe, Konto, Admin.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/download/download.dart';
import '../../core/format.dart';
import '../../core/prefs.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../alerts/alerts_screen.dart';
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
    final isAdmin = user?.isAdmin ?? false;
    final alerts = ref.watch(alertsProvider).value ?? const <PriceAlert>[];
    final activeAlerts = alerts.where((a) => a.active).length;
    final firedAlerts = alerts.where((a) => !a.active && a.triggeredAt != null).length;
    final openReports = isAdmin
        ? (ref.watch(adminReportsProvider).value ?? const <MissingReport>[])
              .where((r) => !r.done)
              .length
        : 0;
    return Scaffold(
      appBar: AppBar(title: const Text('Mehr')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        children: [
          if (user != null) _ProfileCard(user: user, onEdit: () => _editName(context, ref, user)),
          _Group(
            title: 'Sammlung',
            children: [
              _Entry(
                key: const Key('more-sets'),
                icon: Icons.layers_outlined,
                title: 'Sets & Fortschritt',
                subtitle: 'Was fehlt dir? Auch als Master-Set mit Reverse Holo',
                onTap: () => context.push('/sets'),
              ),
              _Entry(
                key: const Key('more-alerts'),
                icon: Icons.notifications_outlined,
                title: 'Preisalarme',
                subtitle: activeAlerts == 0 && firedAlerts == 0
                    ? 'Mitteilung, wenn eine Karte deinen Zielpreis erreicht'
                    : [
                        if (activeAlerts > 0) '$activeAlerts aktiv',
                        if (firedAlerts > 0) '$firedAlerts ausgelöst',
                      ].join(' · '),
                badge: firedAlerts,
                onTap: () => context.push('/alerts'),
              ),
              _Entry(
                key: const Key('more-export'),
                icon: Icons.download_outlined,
                title: 'Sammlung exportieren',
                subtitle: 'Als CSV-Datei, z. B. für Excel',
                onTap: () => _export(context, ref),
              ),
            ],
          ),
          _Group(
            title: 'Freunde',
            children: [
              _Entry(
                key: const Key('more-friends'),
                icon: Icons.people_outline,
                title: 'Freunde',
                subtitle: 'Sammlungen ansehen, die Freunde freigegeben haben',
                onTap: () => context.push('/friends'),
              ),
              _Entry(
                key: const Key('more-trade'),
                icon: Icons.swap_horiz,
                title: 'Tausch-Rechner',
                subtitle: 'Ist ein Tausch fair? Wert von Geben und Bekommen',
                onTap: () => context.push('/trade'),
              ),
            ],
          ),
          _Group(
            title: 'Hilfe',
            children: [
              _Entry(
                key: const Key('more-help'),
                icon: Icons.help_outline,
                title: 'So funktioniert’s',
                subtitle: 'Kurzanleitung zu allen Funktionen',
                onTap: () => context.push('/help'),
              ),
              _Entry(
                key: const Key('more-report'),
                icon: Icons.flag_outlined,
                title: 'Etwas fehlt oder ist falsch?',
                subtitle: 'Karte, Produkt oder Daten an den Admin melden',
                onTap: () => showReportDialog(context, ref),
              ),
            ],
          ),
          _Group(
            title: 'Konto',
            children: [
              _Entry(
                icon: Icons.tune,
                title: 'Einstellungen',
                subtitle: 'Design hell/dunkel, Zustands- und Sprachfaktoren, Standardsprache',
                onTap: () => context.push('/settings'),
              ),
              _Entry(
                icon: Icons.lock_outline,
                title: 'Passwort ändern',
                onTap: () => _changePassword(context, ref),
              ),
              _Entry(
                icon: Icons.devices,
                title: 'Angemeldete Geräte',
                subtitle: 'Wo du angemeldet bist – einzeln abmelden',
                onTap: () => context.push('/sessions'),
              ),
              _Entry(
                icon: Icons.logout,
                color: AppColors.loss,
                title: 'Abmelden',
                onTap: () => ref.read(sessionProvider.notifier).logout(),
              ),
            ],
          ),
          if (isAdmin)
            _Group(
              title: 'Admin',
              children: [
                _Entry(
                  key: const Key('more-admin-reports'),
                  icon: Icons.inbox_outlined,
                  title: 'Meldungen',
                  subtitle: openReports == 0 ? 'Keine offenen Meldungen' : '$openReports offen',
                  badge: openReports,
                  onTap: () => context.push('/admin/reports'),
                ),
                _Entry(
                  icon: Icons.manage_accounts_outlined,
                  title: 'Nutzer',
                  subtitle: 'Rollen, sperren, Passwort-Reset-Code',
                  onTap: () => context.push('/admin/users'),
                ),
                _Entry(
                  icon: Icons.mail_outline,
                  title: 'Einladungen',
                  subtitle: 'Einladungscode für neue Freunde',
                  onTap: () => context.push('/admin/invites'),
                ),
              ],
            ),
          Padding(
            padding: EdgeInsets.fromLTRB(4, 16, 4, 0),
            child: Text(
              '$appName · privat, nur für Freunde.\n'
              'Hinweis: Admins können Sammlungen lesend einsehen; jeder Zugriff wird protokolliert.\n'
              'Kartenbilder und -namen gehören den Rechteinhabern (The Pokémon Company). '
              'Preise: Cardmarket, PriceCharting, TCGdex.',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _export(BuildContext context, WidgetRef ref) async {
    String? csv;
    final ok = await runAction(context, () async => csv = await ref.read(apiProvider).exportCsv());
    if (!ok || !context.mounted) return;
    final stamp = DateTime.now().toIso8601String().substring(0, 10);
    final saved = saveTextFile('kartenkiste-$stamp.csv', csv!, mime: 'text/csv;charset=utf-8');
    showMessage(
      context,
      saved
          ? 'Export erstellt (kartenkiste-$stamp.csv).'
          : 'Export ist nur in der Web-App möglich.',
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
      // Design ist eine Geräte-Einstellung – auch ohne Verbindung zum Server wählbar.
      body: ListView(
        children: [
          const SectionTitle('Design'),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SegmentedButton<ThemeMode>(
              key: const Key('theme-mode'),
              segments: const [
                ButtonSegment(
                  value: ThemeMode.system,
                  icon: Icon(Icons.brightness_auto),
                  label: Text('Wie Handy'),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  icon: Icon(Icons.light_mode_outlined),
                  label: Text('Hell'),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  icon: Icon(Icons.dark_mode_outlined),
                  label: Text('Dunkel'),
                ),
              ],
              selected: {ref.watch(uiPrefsProvider.select((prefs) => prefs.themeMode))},
              onSelectionChanged: (mode) =>
                  ref.read(uiPrefsProvider.notifier).setThemeMode(mode.first),
            ),
          ),
          ...settings.when(
            loading: () => const [
              Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              ),
            ],
            error: (error, _) => [
              ErrorView(message: '$error', onRetry: () => ref.invalidate(userSettingsProvider)),
            ],
            data: (data) => [
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
              Padding(
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
              Padding(
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
        ],
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

class _ProfileCard extends StatelessWidget {
  const _ProfileCard({required this.user, required this.onEdit});

  final User user;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      leading: CircleAvatar(
        radius: 24,
        backgroundColor: AppColors.accent,
        child: Text(
          user.displayName.isEmpty ? '?' : user.displayName[0].toUpperCase(),
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
      ),
      title: Row(
        children: [
          Flexible(
            child: Text(
              user.displayName,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
            ),
          ),
          if (user.isAdmin) ...[
            const SizedBox(width: 8),
            const Tag('Admin', color: AppColors.accent),
          ],
        ],
      ),
      subtitle: Text(user.email),
      trailing: IconButton(
        tooltip: 'Anzeigenamen ändern',
        onPressed: onEdit,
        icon: const Icon(Icons.edit_outlined),
      ),
    ),
  );
}

/// Gruppe mit Überschrift – Einträge in einer Karte, durch Linien getrennt.
class _Group extends StatelessWidget {
  const _Group({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 6),
        child: Text(
          title.toUpperCase(),
          style: TextStyle(
            color: AppColors.textMuted,
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        ),
      ),
      Card(
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            for (var i = 0; i < children.length; i++) ...[
              if (i > 0) const Divider(height: 1, indent: 56),
              children[i],
            ],
          ],
        ),
      ),
    ],
  );
}

class _Entry extends StatelessWidget {
  const _Entry({
    required this.icon,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.badge = 0,
    this.color,
    super.key,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;

  /// Zahl im roten Punkt (z. B. ausgelöste Alarme); 0 = keiner.
  final int badge;
  final Color? color;

  @override
  Widget build(BuildContext context) => ListTile(
    onTap: onTap,
    leading: Badge(
      isLabelVisible: badge > 0,
      label: Text('$badge'),
      child: Icon(icon, color: color ?? AppColors.primary),
    ),
    title: Text(
      title,
      style: TextStyle(color: color, fontWeight: FontWeight.w600),
    ),
    subtitle: subtitle == null
        ? null
        : Text(subtitle!, style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
    trailing: Icon(Icons.chevron_right, color: AppColors.textMuted),
  );
}
