// „So funktioniert’s“: Kurzanleitung zu allen Funktionen – aufklappbar, ohne Fachbegriffe.
import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../onboarding/onboarding.dart';

typedef _Topic = ({IconData icon, String title, List<String> steps});

const List<_Topic> _topics = [
  (
    icon: Icons.style_outlined,
    title: 'Deine Karten bearbeiten',
    steps: [
      'Karte in der Sammlung antippen → Kartenseite mit Preis und Verlauf.',
      'Im grünen Kasten „In deiner Sammlung“ deine Zeile antippen: bearbeiten (Zustand, Slab, Kaufpreis, Ordner), zum Tausch geben, Preisalarm oder entfernen.',
      'Weitere Abschnitte (alle Zustände, Noten vergleichen, US-Markt, Quellen) klappst du per Tipp auf.',
    ],
  ),
  (
    icon: Icons.photo_camera_outlined,
    title: 'Karte scannen',
    steps: [
      'Runder Knopf unten in der Mitte → Foto machen. Karte flach hinlegen, gutes Licht.',
      'Die App erkennt Karte, Sprache und Set und zeigt den Preis. Stimmt etwas nicht: „Andere Karte?“.',
      'Über dem „Hinzufügen“-Knopf wählst du den Ordner. Danach kannst du den Kaufpreis eintragen.',
      'Slabs (PSA, BGS, CGC …) einfach scannen – Firma und Note werden vom Etikett gelesen.',
    ],
  ),
  (
    icon: Icons.search,
    title: 'Suchen und schnell hinzufügen',
    steps: [
      'Deutsch oder Englisch, mit Nummer („nachtara 215“) oder Setkürzel („PFL077“).',
      '„+“ neben einem Treffer: sofort 1× Near Mint in die Sammlung. Lange drücken: Reverse Holo, Details, Merkliste.',
      'Grün „✓ In deiner Sammlung“: so oft hast du die Karte schon – und in welchem Ordner.',
    ],
  ),
  (
    icon: Icons.euro,
    title: 'Preise verstehen',
    steps: [
      '„Beleg“: Preis direkt aus einer Quelle (Cardmarket, eBay). „Schätzung“: aus dem Near-Mint-Preis mit Zustandsfaktor berechnet.',
      'Ohne Cardmarket-Preis: US-Preis von PriceCharting, in Euro umgerechnet.',
      'Kartenseite → „Noten vergleichen“: Roh gegen PSA/BGS/CGC – mit Faktor („×4,2“).',
      'Eigene Faktoren für Zustände und Sprachen: Mehr → Einstellungen.',
    ],
  ),
  (
    icon: Icons.trending_up,
    title: 'Gewinn und Verlust',
    steps: [
      'Trag den Kaufpreis ein (nach dem Scan oder: Karte antippen → deine Zeile im grünen Kasten → Bearbeiten).',
      'Startseite und Sammlung zeigen dann „Investiert“ und „Gewinn“ in € und % – gesamt und je Ordner.',
      'Sortieren nach „Höchster Gewinn“ bzw. „Größter Verlust“; Filter „Kaufpreis fehlt noch“ zum Nachtragen.',
    ],
  ),
  (
    icon: Icons.folder_outlined,
    title: 'Ordner und Mehrfachauswahl',
    steps: [
      'Ordner anlegen: Sammlung → „⋮“ → Ordner verwalten. Jeder Ordner hat eigenen Wert, Gewinn und Kurve.',
      'Ordner wechseln: Schalter „Alle Ordner ▾“ unter der Suche.',
      'Lange auf eine Karte drücken (oder „⋮“ → Mehrere auswählen) → weitere antippen → verschieben, kopieren oder entfernen.',
      'Raster oder Liste: Symbol ganz links in der Schalterleiste.',
      'Personen-Symbol beim Ordner: für Freunde sichtbar (ohne Kaufpreise und Notizen).',
    ],
  ),
  (
    icon: Icons.notifications_outlined,
    title: 'Preisalarme',
    steps: [
      'Auf einer Karte oben die Glocke → „Fällt auf“ oder „Steigt auf“ und Zielpreis.',
      'Mitteilungen einschalten: Mehr → Preisalarme → „Einschalten“ (iPhone: App vom Home-Bildschirm öffnen).',
      'Geprüft wird täglich gegen 12:30 Uhr. Ein Alarm meldet sich einmal – dann „Wieder scharf“.',
    ],
  ),
  (
    icon: Icons.layers_outlined,
    title: 'Sets vervollständigen',
    steps: [
      'Set-Namen auf einer Karte antippen oder Mehr → Sets & Fortschritt.',
      '„Fehlt“ zeigt die fehlenden Karten; „Master“ zählt auch jede Reverse-Holo-Fassung.',
      '„Fehlende auf die Merkliste“ merkt alle auf einmal. Diagramm-Symbol: Set-Analyse mit Gewinnern und Verlierern.',
    ],
  ),
  (
    icon: Icons.swap_horiz,
    title: 'Freunde und Tausch',
    steps: [
      'Mehr → Freunde: Sammlungen, die andere freigegeben haben.',
      'Karte beim Freund antippen → „Zum Tausch“. Eigene Karte: Karte antippen → deine Zeile → „Zum Tausch geben“.',
      'Der Tausch-Rechner zeigt, wer wie viel Wert bekommt. Speichern merkt den Tausch (damals vs. heute).',
    ],
  ),
  (
    icon: Icons.inventory_2_outlined,
    title: 'Versiegeltes',
    steps: [
      'Sammlung → „+“ → Versiegeltes (oder Startseite → Versiegelt): Sets durchblättern oder suchen (auch deutsch, z. B. „Top-Trainer-Box“).',
      'Produkt antippen → Sprache, Anzahl, Kaufpreis und Ordner wählen.',
    ],
  ),
  (
    icon: Icons.flag_outlined,
    title: 'Etwas fehlt oder ist falsch?',
    steps: [
      'In der Suche ohne Treffer „Dem Admin melden“, auf der Kartenseite „Bild, Name oder Preis falsch?“ oder Mehr → Melden.',
    ],
  ),
];

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('So funktioniert’s')),
    body: ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: OutlinedButton.icon(
            key: const Key('help-onboarding'),
            onPressed: () => showOnboarding(context),
            icon: const Icon(Icons.play_circle_outline),
            label: const Text('Kurze Einführung ansehen'),
          ),
        ),
        for (final topic in _topics)
          Card(
            clipBehavior: Clip.antiAlias,
            child: ExpansionTile(
              key: Key('help-${topic.title}'),
              leading: Icon(topic.icon, color: AppColors.primary),
              title: Text(topic.title, style: const TextStyle(fontWeight: FontWeight.w600)),
              childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final (index, step) in topic.steps.indexed)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        CircleAvatar(
                          radius: 11,
                          backgroundColor: AppColors.primary.withValues(alpha: 0.2),
                          child: Text(
                            '${index + 1}',
                            style: const TextStyle(fontSize: 12, color: AppColors.primary),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(child: Text(step)),
                      ],
                    ),
                  ),
              ],
            ),
          ),
      ],
    ),
  );
}
