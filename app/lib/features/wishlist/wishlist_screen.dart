// Merkliste (eine je Nutzer) – wie die Watchlist bei Collectr mit Bild, Preis und
// Veränderung der letzten Tage.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../models/models.dart';
import '../../widgets/common.dart';

final wishlistProvider = FutureProvider.autoDispose<List<WishlistEntry>>(
  (ref) => ref.watch(apiProvider).wishlist(),
);

class WishlistScreen extends ConsumerWidget {
  const WishlistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(wishlistProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Merkliste')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(wishlistProvider),
        child: AsyncBody(
          value: entries,
          onRetry: () => ref.invalidate(wishlistProvider),
          builder: (list) => list.isEmpty
              ? ListView(
                  children: [
                    const SizedBox(height: 120),
                    EmptyView(
                      icon: Icons.favorite_border,
                      message:
                          'Deine Merkliste ist leer.\n'
                          'Karten, die du noch suchst, merkst du dir auf der Kartenseite '
                          '(Knopf „Merkliste“) – hier siehst du dann Preis und Entwicklung.',
                      action: FilledButton.icon(
                        onPressed: () => context.go('/search'),
                        icon: const Icon(Icons.search),
                        label: const Text('Karte suchen'),
                      ),
                    ),
                  ],
                )
              : ListView.separated(
                  itemCount: list.length + 1,
                  separatorBuilder: (_, index) =>
                      index == 0 ? const SizedBox.shrink() : const Divider(indent: 72, height: 1),
                  itemBuilder: (context, index) =>
                      index == 0 ? _Header(entries: list) : _WishTile(entry: list[index - 1]),
                ),
        ),
      ),
    );
  }
}

/// „3 Karten · zusammen 412,30 €“ und der Hinweis zum Entfernen.
class _Header extends StatelessWidget {
  const _Header({required this.entries});

  final List<WishlistEntry> entries;

  @override
  Widget build(BuildContext context) {
    final total = entries.fold<double>(0, (sum, e) => sum + (parseAmount(e.nmValue) ?? 0));
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${entries.length} ${entries.length == 1 ? 'Eintrag' : 'Einträge'} · zusammen '
            '${money(total.toStringAsFixed(2))}',
            key: const Key('wishlist-total'),
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const Text(
            'Nach links wischen zum Entfernen · Preise: Near Mint bei Cardmarket',
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _WishTile extends ConsumerWidget {
  const _WishTile({required this.entry});

  final WishlistEntry entry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = entry.card;
    final tile = card == null
        ? ListTile(
            leading: CardImage(url: entry.product?.imageUrl, width: 40, contain: true),
            title: Text(entry.product?.name ?? '?', maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: const Text('Versiegelt', style: TextStyle(color: AppColors.textMuted)),
            trailing: _Price(entry: entry),
          )
        : CardTile(
            card: card,
            trailing: _Price(entry: entry),
            onTap: () => context.push('/card/${card.id}'),
          );
    return Dismissible(
      key: ValueKey(entry.id),
      direction: DismissDirection.endToStart,
      background: Container(
        color: AppColors.loss,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text('Entfernen', style: TextStyle(color: Colors.white)),
            SizedBox(width: 8),
            Icon(Icons.delete, color: Colors.white),
          ],
        ),
      ),
      onDismissed: (_) async {
        await runAction(context, () => ref.read(apiProvider).removeFromWishlist(entry.id));
        ref.invalidate(wishlistProvider);
      },
      child: tile,
    );
  }
}

/// Preis und – falls bekannt – Veränderung („+25,0 % in 7 Tagen“).
class _Price extends StatelessWidget {
  const _Price({required this.entry});

  final WishlistEntry entry;

  @override
  Widget build(BuildContext context) {
    final pct = parseAmount(entry.changePct);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          entry.nmValue == null ? 'noch kein Preis' : money(entry.nmValue),
          style: TextStyle(
            fontWeight: FontWeight.w700,
            color: entry.nmValue == null ? AppColors.textMuted : null,
            fontSize: entry.nmValue == null ? 12 : null,
          ),
        ),
        if (pct != null && pct != 0)
          Text(
            '${signedPercent(pct, isPercent: true)} in ${entry.changeDays} Tagen',
            key: Key('wish-change-${entry.id}'),
            style: TextStyle(color: pct > 0 ? AppColors.gain : AppColors.loss, fontSize: 12),
          )
        else if (entry.nmValueKind == 'estimated')
          const Text('Schätzung', style: TextStyle(color: AppColors.warning, fontSize: 11)),
      ],
    );
  }
}
