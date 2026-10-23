import 'package:flutter_test/flutter_test.dart';
import 'package:kartenkiste/models/models.dart';

void main() {
  test('Bildadressen je Quelle: klein für Listen, groß für Details', () {
    const tcgdex = 'https://assets.tcgdex.net/de/swsh/swsh7/215';
    expect(cardImageUrl(tcgdex), '$tcgdex/low.webp');
    expect(cardImageUrl(tcgdex, high: true), '$tcgdex/high.webp');

    const ptcg = 'https://images.pokemontcg.io/swsh45sv/SV068_hires.png';
    expect(cardImageUrl(ptcg), 'https://images.pokemontcg.io/swsh45sv/SV068.png');
    expect(cardImageUrl(ptcg, high: true), ptcg);

    const scrydex = 'https://images.scrydex.com/pokemon/me2pt5-1/large';
    expect(cardImageUrl(scrydex), 'https://images.scrydex.com/pokemon/me2pt5-1/small');

    const japan =
        'https://www.pokemon-card.com/assets/images/card_images/large/M6a/050613_P_TAMATAMA.jpg';
    expect(cardImageUrl(japan), japan);
    expect(cardImageUrl(null), isNull);
  });

  test('Set-Namen: übersetzt anzeigen, Original dazu', () {
    final japanese = SetSummary.fromJson({
      'id': '1',
      'external_id': 'S12',
      'language': 'ja',
      'name': 'パラダイムトリガー',
      'translated_name': 'Paradigm Trigger',
    });
    expect(japanese.displayName, 'Paradigm Trigger');
    expect(japanese.originalName, 'パラダイムトリガー');

    final german = SetSummary.fromJson({
      'id': '2',
      'external_id': 'sv03',
      'language': 'de',
      'name': 'Obsidian Flammen',
    });
    expect(german.displayName, 'Obsidian Flammen');
    expect(german.originalName, isNull);
  });
}
