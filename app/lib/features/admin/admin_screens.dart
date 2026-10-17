// Admin: Nutzer (sperren, Rolle, Passwort-Reset-Code, Sammlung lesend einsehen)
// und Einladungen (erzeugen, Code teilen, widerrufen).
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';
import '../collection/collection_screen.dart';

final adminUsersProvider = FutureProvider.autoDispose<List<User>>(
  (ref) => ref.watch(apiProvider).adminUsers(),
);

final invitesProvider = FutureProvider.autoDispose<List<Invite>>(
  (ref) => ref.watch(apiProvider).invites(),
);

final adminCollectionProvider = FutureProvider.autoDispose
    .family<(CollectionSummary, ItemPage), String>((ref, userId) async {
      final api = ref.watch(apiProvider);
      return (await api.adminUserSummary(userId), await api.adminUserItems(userId));
    });

/// Zeigt einen Code groß an, mit Kopieren-Knopf.
Future<void> showCode(BuildContext context, String title, String code, String hint) =>
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(
              code,
              key: const Key('shown-code'),
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 1.5),
            ),
            const SizedBox(height: 8),
            Text(hint, style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
          ],
        ),
        actions: [
          TextButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: code));
              if (dialogContext.mounted) showMessage(dialogContext, 'Kopiert.');
            },
            icon: const Icon(Icons.copy),
            label: const Text('Kopieren'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Fertig'),
          ),
        ],
      ),
    );

class AdminUsersScreen extends ConsumerWidget {
  const AdminUsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final users = ref.watch(adminUsersProvider);
    final me = ref.watch(sessionProvider).value;
    return Scaffold(
      appBar: AppBar(title: const Text('Nutzer')),
      body: AsyncBody(
        value: users,
        onRetry: () => ref.invalidate(adminUsersProvider),
        builder: (list) => ListView.separated(
          itemCount: list.length,
          separatorBuilder: (_, _) => const Divider(),
          itemBuilder: (context, index) {
            final user = list[index];
            final isMe = user.id == me?.id;
            return ListTile(
              title: Row(
                children: [
                  Flexible(child: Text(user.displayName, overflow: TextOverflow.ellipsis)),
                  const SizedBox(width: 6),
                  if (user.isAdmin) const Tag('Admin', color: AppColors.accent),
                  if (!user.isActive) const Tag('gesperrt', color: AppColors.loss),
                ],
              ),
              subtitle: Text(
                '${user.email}\nzuletzt aktiv: ${dateTime(user.lastLoginAt)}',
                style: const TextStyle(color: AppColors.textMuted),
              ),
              isThreeLine: true,
              onTap: () => context.push(
                Uri(
                  path: '/admin/users/${user.id}',
                  queryParameters: {'name': user.displayName},
                ).toString(),
              ),
              trailing: PopupMenuButton<String>(
                onSelected: (action) => _act(context, ref, user, action),
                itemBuilder: (_) => [
                  const PopupMenuItem(value: 'collection', child: Text('Sammlung ansehen')),
                  if (!isMe) ...[
                    PopupMenuItem(
                      value: 'active',
                      child: Text(user.isActive ? 'Sperren' : 'Entsperren'),
                    ),
                    PopupMenuItem(
                      value: 'role',
                      child: Text(user.isAdmin ? 'Admin-Rechte entziehen' : 'Zum Admin machen'),
                    ),
                  ],
                  const PopupMenuItem(value: 'reset', child: Text('Passwort-Reset-Code')),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Future<void> _act(BuildContext context, WidgetRef ref, User user, String action) async {
    final api = ref.read(apiProvider);
    switch (action) {
      case 'collection':
        await context.push(
          Uri(
            path: '/admin/users/${user.id}',
            queryParameters: {'name': user.displayName},
          ).toString(),
        );
      case 'active':
        await runAction(context, () => api.adminUpdateUser(user.id, isActive: !user.isActive));
        ref.invalidate(adminUsersProvider);
      case 'role':
        await runAction(
          context,
          () => api.adminUpdateUser(user.id, role: user.isAdmin ? 'user' : 'admin'),
        );
        ref.invalidate(adminUsersProvider);
      case 'reset':
        ResetCode? code;
        final ok = await runAction(context, () async => code = await api.adminResetCode(user.id));
        if (ok && context.mounted) {
          await showCode(
            context,
            'Reset-Code für ${user.displayName}',
            code!.code,
            'Gültig bis ${dateTime(code!.expiresAt)}. Der Nutzer löst ihn unter '
                '„Passwort vergessen?“ ein.',
          );
        }
    }
  }
}

class AdminInvitesScreen extends ConsumerWidget {
  const AdminInvitesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invites = ref.watch(invitesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Einladungen')),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('create-invite'),
        onPressed: () => _create(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Einladung'),
      ),
      body: AsyncBody(
        value: invites,
        onRetry: () => ref.invalidate(invitesProvider),
        builder: (list) => list.isEmpty
            ? const EmptyView(icon: Icons.mail_outline, message: 'Noch keine Einladungen.')
            : ListView.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const Divider(),
                itemBuilder: (context, index) {
                  final invite = list[index];
                  return ListTile(
                    title: Text(invite.note ?? 'Ohne Notiz'),
                    subtitle: Text(
                      'erstellt ${date(invite.createdAt)} · gültig bis ${date(invite.expiresAt)}',
                      style: const TextStyle(color: AppColors.textMuted),
                    ),
                    trailing: invite.status == 'open'
                        ? TextButton(
                            onPressed: () async {
                              await runAction(
                                context,
                                () => ref.read(apiProvider).revokeInvite(invite.id),
                              );
                              ref.invalidate(invitesProvider);
                            },
                            child: const Text('Widerrufen'),
                          )
                        : Tag(invite.statusLabel, color: AppColors.textMuted),
                  );
                },
              ),
      ),
    );
  }

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final text = await showTextInput(
      context,
      title: 'Neue Einladung',
      label: 'Notiz, z. B. „für Max“',
      confirm: 'Erzeugen',
    );
    if (text == null || !context.mounted) return;
    Invite? invite;
    final ok = await runAction(
      context,
      () async =>
          invite = await ref.read(apiProvider).createInvite(note: text.isEmpty ? null : text),
    );
    ref.invalidate(invitesProvider);
    if (ok && context.mounted && invite?.code != null) {
      await showCode(
        context,
        'Einladungscode',
        invite!.code!,
        'Nur jetzt sichtbar. Gültig bis ${date(invite!.expiresAt)}, einmal verwendbar.',
      );
    }
  }
}

class AdminUserCollectionScreen extends ConsumerWidget {
  const AdminUserCollectionScreen({required this.userId, required this.name, super.key});

  final String userId;
  final String name;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(adminCollectionProvider(userId));
    return Scaffold(
      appBar: AppBar(title: Text('Sammlung von $name')),
      body: AsyncBody(
        value: data,
        onRetry: () => ref.invalidate(adminCollectionProvider(userId)),
        builder: (value) {
          final (summary, page) = value;
          return ListView(
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Text(
                  'Nur lesend. Der Zugriff wird im Audit-Log protokolliert.',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                ),
              ),
              ListTile(
                title: Text(
                  money(summary.totalValue),
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                subtitle: Text(
                  '${summary.positions} Positionen · ${summary.items} Stück · ${summary.sets} Sets',
                ),
              ),
              const Divider(),
              for (final item in page.items) ReadOnlyItemTile(item: item),
              if (page.items.isEmpty)
                const EmptyView(icon: Icons.inbox_outlined, message: 'Sammlung ist leer.'),
            ],
          );
        },
      ),
    );
  }
}
