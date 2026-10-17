// Listen: die Merkliste (eine je Nutzer) mit aktuellem NM-Wert.
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
                  children: const [
                    SizedBox(height: 120),
                    EmptyView(
                      icon: Icons.favorite_border,
                      message:
                          'Deine Merkliste ist leer.\n'
                          'Auf einer Karte „Merkliste“ tippen, um sie hier zu sehen.',
                    ),
                  ],
                )
              : ListView.separated(
                  itemCount: list.length,
                  separatorBuilder: (_, _) => const Divider(indent: 72),
                  itemBuilder: (context, index) {
                    final entry = list[index];
                    final card = entry.card;
                    final value = Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(money(entry.nmValue)),
                        if (entry.nmValueKind == 'estimated')
                          const Text(
                            'Schätzung',
                            style: TextStyle(color: AppColors.warning, fontSize: 11),
                          ),
                      ],
                    );
                    return Dismissible(
                      key: ValueKey(entry.id),
                      direction: DismissDirection.endToStart,
                      background: Container(
                        color: AppColors.loss,
                        alignment: Alignment.centerRight,
                        padding: const EdgeInsets.only(right: 24),
                        child: const Icon(Icons.delete, color: Colors.white),
                      ),
                      onDismissed: (_) async {
                        await runAction(
                          context,
                          () => ref.read(apiProvider).removeFromWishlist(entry.id),
                        );
                        ref.invalidate(wishlistProvider);
                      },
                      child: card == null
                          ? ListTile(
                              leading: const Icon(Icons.inventory_2),
                              title: Text(entry.product?.name ?? '?'),
                              trailing: value,
                            )
                          : CardTile(
                              card: card,
                              trailing: value,
                              onTap: () => context.push('/card/${card.id}'),
                            ),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
