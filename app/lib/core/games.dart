// Spiele (Pokémon, One Piece) und der gemerkte Spielfilter „Alle · Pokémon · One Piece“.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'prefs.dart';

enum Game {
  pokemon('pokemon', 'Pokémon'),
  onepiece('onepiece', 'One Piece');

  const Game(this.id, this.label);

  /// Wert für die API (`?game=`).
  final String id;
  final String label;

  /// Sprachen, in denen es Karten gibt (Reihenfolge = Auswahl in der App).
  List<String> get languages => switch (this) {
    Game.pokemon => const ['de', 'en', 'ja', 'ko', 'zh-tw', 'zh-cn'],
    Game.onepiece => const ['en', 'ja'],
  };

  static Game? fromId(String? id) => Game.values.asNameMap()[id];
}

/// Aktiver Spielfilter (`null` = alle Spiele); wirkt auf Übersicht, Sammlung, Sets und Suche.
final gameFilterProvider = Provider<Game?>(
  (ref) => ref.watch(uiPrefsProvider.select((prefs) => Game.fromId(prefs.game))),
);

/// „Alle · Pokémon · One Piece“ – kompakt, für oben auf den Hauptseiten.
class GameSwitcher extends ConsumerWidget {
  const GameSwitcher({super.key, this.padding = const EdgeInsets.fromLTRB(16, 4, 16, 8)});

  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(gameFilterProvider);
    return Padding(
      padding: padding,
      child: SegmentedButton<Game?>(
        key: const Key('game-switcher'),
        showSelectedIcon: false,
        style: const ButtonStyle(visualDensity: VisualDensity.compact),
        segments: [
          const ButtonSegment(value: null, label: Text('Alle', key: Key('game-all'))),
          for (final game in Game.values)
            ButtonSegment(
              value: game,
              label: Text(game.label, key: Key('game-${game.id}'), maxLines: 1),
            ),
        ],
        selected: {selected},
        onSelectionChanged: (choice) =>
            ref.read(uiPrefsProvider.notifier).setGame(choice.firstOrNull),
      ),
    );
  }
}
