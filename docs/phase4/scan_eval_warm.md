# Scanner-Evaluation

## Kennzahlen

- Fotos: 7 (davon 1 nicht im Katalog)
- **Top-1:** 5/6 (83 %)
- Top-5 (richtige Karte unter Treffer + Alternativen): 5/6 (83 %)
- Nicht im Katalog, richtig als unsicher erkannt: 1/1 (100 %)
- **Sicher, aber falsch:** 0
- Zeit pro Foto: Ø 2.71 s, max 4.57 s

## Abnahme (Plan Phase 4)

- Top-1 DE/EN: 1/1 (100 %) – Ziel ≥ 85 % ✅ (zu wenige Fotos für eine belastbare Aussage)
- Latenz ≤ 3 s: ❌ (max 4.57 s)

## Einzelergebnisse

| Datei | Soll | Ergebnis | Sicher | Rang | Confidence | Begründung | s |
|---|---|---|---|---|---|---|---|
| 01.jpg | ゼニガメ · 007 [ja] (-) | ✅ ゼニガメ · SV2a-007 [ja] | nein | – | 0.738 | Nummer 007 passt; Name ähnlich „ゼニガメ“ (100%); Bildabgleich Katalog: 22 | 4.57 |
| 02.jpg | Team Rockets Mewtu ex · 231/182 [de] (sv10-231) | ✅ Team Rockets Mewtu-ex · sv10-231 [de] | ja | 1 | 1.0 | Nummer DR231/182 passt (Set mit 182 Karten); Name ähnlich „Team Rockets Mewtu-ex“ (85%); Bildabgleich Katalog: 104 | 2.66 |
| 03.jpg | ルギアV · 110/098 [ja] (S12-110) | ✅ ルギアV · S12-110 [ja] | ja | 1 | 1.0 | Nummer 110/098 passt (Set mit 98 Karten); Setcode S12; Name ähnlich „ルギアV“ (100%); Bildabgleich Katalog: 277 | 1.49 |
| 04.jpg | ルギアV · 110/098 [ja] (S12-110) | ✅ ルギアV · S12-110 [ja] | ja | 1 | 1.0 | Nummer 110 passt; Name ähnlich „ルギアV“ (100%); Bildabgleich Katalog: 134 | 2.49 |
| 05.jpg | ブラッキーex · 217/187 [ja] (SV8a-217) | ✅ ブラッキーex · SV8a-217 [ja] | ja | 1 | 0.856 | Name ähnlich „ブラッキーex“ (95%); Bildabgleich Katalog: 131 | 2.12 |
| 06.jpg | ルギア · 142/103 [ja] | ✅ ルギア · M6a-142 [ja] | ja | 1 | 1.0 | Nummer 142/103 passt (Set mit 103 Karten); Setcode M6a; Name ähnlich „ルギア“ (100%) | 1.80 |
| 07.jpg | 鲤鱼王 · 165/103 [zh-cn] | ❌ 皮卡丘ex · SV8a-236 [zh-cn] | nein | – | 0.332 | Name ähnlich „皮卡丘ex“ (95%) | 3.85 |

## Erkannte Merkmale

- **01.jpg:** Nummern No.007 · Namen <PSA10> [Intro Pack] Squirtle, gtchaxonline.com, ゼニガメ, はたく, Old Back · Sprache ja · Slab PSA 10
- **02.jpg:** Nummern DR231/182 · Namen Team Rockets MewtuX, Löschball, Sparpower, trwtn2Rxttam30, mchr zu. · Sprache de, en
- **03.jpg:** Nummern 110/098 · Namen ルギアV, エアロダイブ, かぜよみ · Sprache ja
- **04.jpg:** Nummern #110 · Namen LUGIA V, ルギアV, 2022 POKEMON JPN.SWSH, エアロダイブ, かぜよみ · Sprache ja · Slab PSA 10
- **05.jpg:** Nummern 212/38 · Namen ブラッキー, 才学キス, ムーンEラーシュ, オ二ギス, ムーソミラーシュ · Sprache ja
- **06.jpg:** Nummern 142/103 · Namen ルギア, スチームブラスト50, サイコキネシス, クリスタルタイプ, ポケボデ · Sprache ja
- **07.jpg:** Nummern 165/103 · Namen 跳跃高手, 皮卡丘, Mllos.Shing Konda · Sprache zh-cn, zh-tw
