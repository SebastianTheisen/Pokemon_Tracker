// Preisalarme: Liste, Benachrichtigungen auf diesem Gerät, Blatt zum Anlegen/Ändern.
//
// Geprüft wird nach der täglichen Preisrunde (12:30 Uhr). Ein Alarm meldet sich einmal und
// ist dann „ausgelöst“, bis man ihn wieder scharf stellt.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/push/push_bridge.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

final alertsProvider = FutureProvider.autoDispose<List<PriceAlert>>(
  (ref) => ref.watch(apiProvider).alerts(),
);

/// Stand der Benachrichtigungen: Gerät (Browser) + Server.
typedef PushState = ({PushStatus status, bool subscribed, PushConfig config});

final pushStateProvider = FutureProvider.autoDispose<PushState>((ref) async {
  final bridge = ref.watch(pushBridgeProvider);
  final config = await ref.watch(apiProvider).pushConfig();
  final status = await bridge.status();
  final endpoint = status == PushStatus.granted ? await bridge.endpoint() : null;
  return (status: status, subscribed: endpoint != null, config: config);
});

/// Benachrichtigungen auf diesem Gerät einschalten (Erlaubnis + Anmeldung beim Server).
Future<bool> enablePush(BuildContext context, WidgetRef ref) async {
  final api = ref.read(apiProvider);
  final bridge = ref.read(pushBridgeProvider);
  try {
    final config = await api.pushConfig();
    final key = config.publicKey;
    if (key == null) {
      if (context.mounted) showMessage(context, 'Push ist auf dem Server noch nicht eingerichtet.');
      return false;
    }
    final subscription = await bridge.subscribe(key);
    if (!context.mounted) return false;
    final ok = await runAction(context, () => api.pushSubscribe(subscription));
    ref.invalidate(pushStateProvider);
    if (ok && context.mounted) showMessage(context, 'Benachrichtigungen sind an.');
    return ok;
  } on PushException catch (error) {
    if (context.mounted) showMessage(context, error.message);
    ref.invalidate(pushStateProvider);
    return false;
  } on ApiException catch (error) {
    if (context.mounted) showMessage(context, error.message);
    return false;
  }
}

class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(alertsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Preisalarme')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref
            ..invalidate(alertsProvider)
            ..invalidate(pushStateProvider);
          await ref.read(alertsProvider.future);
        },
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            const _PushCard(),
            const SizedBox(height: 16),
            AsyncBody(
              value: alerts,
              onRetry: () => ref.invalidate(alertsProvider),
              builder: (list) => list.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.only(top: 24),
                      child: EmptyView(
                        icon: Icons.notifications_none,
                        message:
                            'Noch keine Preisalarme.\nAuf einer Karte oder bei Versiegeltem '
                            '„Preisalarm“ antippen und einen Zielpreis wählen.',
                      ),
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final alert in list) _AlertTile(alert: alert),
                        const Padding(
                          padding: EdgeInsets.only(top: 12),
                          child: Text(
                            'Geprüft wird täglich nach der Preisrunde (12:30 Uhr). Ein Alarm '
                            'meldet sich einmal – danach „Wieder scharf“ antippen.',
                            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// „Benachrichtigungen auf diesem Gerät“: Status, Einschalten, Probe, Ausschalten.
class _PushCard extends ConsumerStatefulWidget {
  const _PushCard();

  @override
  ConsumerState<_PushCard> createState() => _PushCardState();
}

class _PushCardState extends ConsumerState<_PushCard> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    await action();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _test() => _run(() async {
    var sent = 0;
    final ok = await runAction(context, () async => sent = await ref.read(apiProvider).pushTest());
    if (ok && mounted) {
      showMessage(
        context,
        sent > 0 ? 'Probe gesendet – kommt gleich an.' : 'Kein Gerät hat die Probe angenommen.',
      );
    }
  });

  Future<void> _disable() => _run(() async {
    final endpoint = await ref.read(pushBridgeProvider).unsubscribe();
    if (endpoint != null && mounted) {
      await runAction(context, () => ref.read(apiProvider).pushUnsubscribe(endpoint));
    }
    ref.invalidate(pushStateProvider);
  });

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(pushStateProvider);
    return Card(
      key: const Key('push-card'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: state.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => Text('$error'),
          data: (data) {
            final (icon, color, text) = switch (data) {
              (config: PushConfig(publicKey: null), status: _, subscribed: _) => (
                Icons.cloud_off,
                AppColors.textMuted,
                'Auf dem Server noch nicht eingerichtet (Admin: deploy/phase7_push.sh).',
              ),
              (status: PushStatus.install, config: _, subscribed: _) => (
                Icons.add_to_home_screen,
                AppColors.warning,
                'Am iPhone gibt es Benachrichtigungen nur in der App vom Home-Bildschirm: '
                    'in Safari Teilen → „Zum Home-Bildschirm“, dann Kartenkiste über das Symbol '
                    'öffnen.',
              ),
              (status: PushStatus.unsupported, config: _, subscribed: _) => (
                Icons.block,
                AppColors.textMuted,
                'Dieser Browser kann keine Benachrichtigungen.',
              ),
              (status: PushStatus.denied, config: _, subscribed: _) => (
                Icons.notifications_off,
                AppColors.loss,
                'Blockiert. In den Einstellungen des Handys bei Kartenkiste Mitteilungen '
                    'erlauben.',
              ),
              (subscribed: true, status: _, config: _) => (
                Icons.notifications_active,
                AppColors.gain,
                'An – Preisalarme kommen als Mitteilung aufs Handy.',
              ),
              _ => (
                Icons.notifications_none,
                AppColors.textMuted,
                'Aus. Einschalten, damit Preisalarme als Mitteilung ankommen.',
              ),
            };
            final canEnable =
                data.config.publicKey != null &&
                !data.subscribed &&
                (data.status == PushStatus.notAsked || data.status == PushStatus.granted);
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, color: color),
                    const SizedBox(width: 10),
                    const Expanded(
                      child: Text(
                        'Benachrichtigungen auf diesem Gerät',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(text, key: const Key('push-status')),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    if (canEnable)
                      FilledButton.icon(
                        key: const Key('push-enable'),
                        onPressed: _busy ? null : () => _run(() => enablePush(context, ref)),
                        icon: const Icon(Icons.notifications_active),
                        label: const Text('Einschalten'),
                      ),
                    if (data.subscribed) ...[
                      OutlinedButton.icon(
                        key: const Key('push-test'),
                        onPressed: _busy ? null : _test,
                        icon: const Icon(Icons.send),
                        label: const Text('Probe senden'),
                      ),
                      TextButton(
                        key: const Key('push-disable'),
                        onPressed: _busy ? null : _disable,
                        child: const Text('Ausschalten'),
                      ),
                    ],
                  ],
                ),
                if (data.subscribed)
                  SwitchListTile(
                    key: const Key('push-weekly'),
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Wochenrückblick'),
                    subtitle: const Text('Sonntags: Wert deiner Sammlung und Top-Gewinner'),
                    value: data.config.weeklySummary,
                    onChanged: _busy
                        ? null
                        : (enabled) => _run(() async {
                            await runAction(
                              context,
                              () => ref.read(apiProvider).setWeeklySummary(enabled: enabled),
                            );
                            ref.invalidate(pushStateProvider);
                          }),
                  ),
                if (data.config.devices > 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      '${data.config.devices} ${data.config.devices == 1 ? 'Gerät' : 'Geräte'} '
                      'angemeldet',
                      style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _AlertTile extends ConsumerWidget {
  const _AlertTile({required this.alert});

  final PriceAlert alert;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.read(apiProvider);
    final card = alert.card;
    final reached = alert.triggeredAt != null;
    return Card(
      key: Key('alert-${alert.id}'),
      child: ListTile(
        onTap: card == null ? null : () => context.push('/card/${card.id}'),
        leading: CardImage(
          url: card?.image() ?? alert.product?.imageUrl,
          width: 40,
          contain: card == null,
        ),
        title: Text(alert.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              [
                '${alert.above ? '▲ ab' : '▼ bis'} ${money(alert.target)}',
                'jetzt ${money(alert.currentValue)}',
                ?alert.detail,
              ].join(' · '),
            ),
            if (reached)
              Text(
                'Ausgelöst ${date(alert.triggeredAt)} bei ${money(alert.triggeredValue)}',
                style: const TextStyle(color: AppColors.gain, fontWeight: FontWeight.w600),
              )
            else if (!alert.active)
              const Text('Pausiert', style: TextStyle(color: AppColors.textMuted)),
          ],
        ),
        trailing: PopupMenuButton<String>(
          key: Key('alert-menu-${alert.id}'),
          onSelected: (action) async {
            final done = switch (action) {
              'rearm' => runAction(context, () => api.updateAlert(alert.id, active: true)),
              'pause' => runAction(context, () => api.updateAlert(alert.id, active: false)),
              'delete' => runAction(context, () => api.deleteAlert(alert.id)),
              _ => showAlertSheet(context, ref, alert: alert).then((saved) => saved != null),
            };
            if (await done) ref.invalidate(alertsProvider);
          },
          itemBuilder: (_) => [
            const PopupMenuItem(value: 'edit', child: Text('Zielpreis ändern')),
            if (!alert.active)
              const PopupMenuItem(value: 'rearm', child: Text('Wieder scharf'))
            else
              const PopupMenuItem(value: 'pause', child: Text('Pausieren')),
            const PopupMenuItem(value: 'delete', child: Text('Löschen')),
          ],
        ),
      ),
    );
  }
}

/// Blatt „Preisalarm“ – neu für [card]/[product] oder Ändern von [alert].
/// [prices] (Karte) bzw. [currentValue] (Produkt) zeigen den aktuellen Wert.
Future<PriceAlert?> showAlertSheet(
  BuildContext context,
  WidgetRef ref, {
  CardInfo? card,
  Product? product,
  CardPrices? prices,
  String? currentValue,
  PriceAlert? alert,
}) async {
  final saved = await showModalBottomSheet<PriceAlert>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => _AlertForm(
      card: card,
      product: product,
      prices: prices,
      currentValue: currentValue,
      alert: alert,
    ),
  );
  if (saved == null || !context.mounted) return saved;
  ref.invalidate(alertsProvider);
  // Ohne Benachrichtigungen sieht man ausgelöste Alarme nur in der Liste – darauf hinweisen.
  final bridge = ref.read(pushBridgeProvider);
  final subscribed = await bridge.status() == PushStatus.granted && await bridge.endpoint() != null;
  if (!context.mounted) return saved;
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(
          [
            alert == null ? 'Preisalarm angelegt.' : 'Preisalarm geändert.',
            if (!subscribed) 'Mitteilungen sind noch aus.',
          ].join(' '),
        ),
        action: subscribed
            ? null
            : SnackBarAction(
                label: 'Einschalten',
                onPressed: () => GoRouter.of(context).push('/alerts'),
              ),
      ),
    );
  return saved;
}

class _AlertForm extends ConsumerStatefulWidget {
  const _AlertForm({this.card, this.product, this.prices, this.currentValue, this.alert});

  final CardInfo? card;
  final Product? product;
  final CardPrices? prices;
  final String? currentValue;
  final PriceAlert? alert;

  @override
  ConsumerState<_AlertForm> createState() => _AlertFormState();
}

class _AlertFormState extends ConsumerState<_AlertForm> {
  late String _direction = widget.alert?.direction ?? 'below';
  late String _variant = widget.alert?.variant ?? 'normal';
  late String _condition = widget.alert?.condition ?? 'NM';
  late final _target = TextEditingController(
    text: widget.alert?.target.replaceAll('.', ',') ?? _suggest(_direction),
  );
  bool _busy = false;

  bool get _isCard => (widget.alert?.card ?? widget.card) != null;

  String get _name =>
      widget.alert?.title ?? widget.card?.displayName ?? widget.product?.name ?? 'Unbekannt';

  /// Aktueller Wert für Variante + Zustand (Karte) bzw. vom Aufrufer (Produkt, Bearbeiten).
  String? get _current {
    final prices = widget.prices;
    if (prices != null) {
      return prices.conditions
          .where((c) => c.variant == _variant && c.condition == _condition)
          .firstOrNull
          ?.value;
    }
    return widget.alert?.currentValue ?? widget.currentValue;
  }

  /// Vorschlag: 10 % über bzw. unter dem aktuellen Wert.
  String _suggest(String direction) {
    final value = parseAmount(_current);
    if (value == null) return '';
    final target = value * (direction == 'above' ? 1.1 : 0.9);
    return target.toStringAsFixed(2).replaceAll('.', ',');
  }

  @override
  void dispose() {
    _target.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final target = normalizeAmount(_target.text);
    final parsed = target == null ? null : double.tryParse(target);
    if (parsed == null || parsed <= 0) {
      showMessage(context, 'Zielpreis bitte als Zahl über 0 eingeben, z. B. 49,90');
      return;
    }
    setState(() => _busy = true);
    final api = ref.read(apiProvider);
    PriceAlert? saved;
    final ok = await runAction(context, () async {
      final alert = widget.alert;
      saved = alert != null
          ? await api.updateAlert(alert.id, target: target, direction: _direction)
          : await api.createAlert(
              cardId: widget.card?.id,
              productId: widget.product?.id,
              direction: _direction,
              target: target!,
              variant: _variant,
              condition: _condition,
            );
    });
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.of(context).pop(saved);
  }

  @override
  Widget build(BuildContext context) {
    final hasReverse = widget.card?.variants?['reverse'] ?? false;
    final editing = widget.alert != null;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            const SectionTitle('Preisalarm'),
            Text(_name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            Text(
              'Aktuell: ${money(_current)}',
              key: const Key('alert-current'),
              style: const TextStyle(color: AppColors.textMuted),
            ),
            const SizedBox(height: 16),
            SegmentedButton<String>(
              key: const Key('alert-direction'),
              segments: const [
                ButtonSegment(
                  value: 'below',
                  icon: Icon(Icons.trending_down),
                  label: Text('Fällt auf'),
                ),
                ButtonSegment(
                  value: 'above',
                  icon: Icon(Icons.trending_up),
                  label: Text('Steigt auf'),
                ),
              ],
              selected: {_direction},
              onSelectionChanged: (value) => setState(() {
                final previous = _suggest(_direction);
                _direction = value.first;
                // Vorschlag nur ersetzen, wenn er nicht von Hand geändert wurde.
                if (_target.text == previous) _target.text = _suggest(_direction);
              }),
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('alert-target'),
              controller: _target,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Zielpreis', suffixText: '€'),
            ),
            if (_isCard && !editing) ...[
              const SizedBox(height: 16),
              const Text('Zustand'),
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  for (final condition in conditionLabels.keys)
                    ChoiceChip(
                      key: Key('alert-condition-$condition'),
                      label: Text(condition),
                      tooltip: conditionLabels[condition],
                      selected: _condition == condition,
                      onSelected: (_) => setState(() => _condition = condition),
                    ),
                ],
              ),
              if (hasReverse) ...[
                const SizedBox(height: 12),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'normal', label: Text('Normal')),
                    ButtonSegment(value: 'reverse', label: Text('Reverse Holo')),
                  ],
                  selected: {_variant},
                  onSelectionChanged: (value) => setState(() => _variant = value.first),
                ),
              ],
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              key: const Key('alert-save'),
              onPressed: _busy ? null : _save,
              icon: const Icon(Icons.notifications_active),
              label: Text(editing ? 'Speichern' : 'Alarm anlegen'),
            ),
          ],
        ),
      ),
    );
  }
}
