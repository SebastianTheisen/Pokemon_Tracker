// Erst-Start-Anleitung: drei kurze Seiten (Scannen, Sammlung, Merkliste und Alarme).
// Erscheint einmal pro Gerät; unter Mehr → So funktioniert’s erneut aufrufbar.
import 'package:flutter/material.dart';

import '../../core/theme.dart';

typedef _Page = ({IconData icon, String title, String text});

const List<_Page> _pages = [
  (
    icon: Icons.document_scanner,
    title: 'Karte scannen',
    text:
        'Tippe unten auf den runden Knopf und fotografiere eine Karte. Du siehst sofort den '
        'Preis – ein Tipp legt sie in deine Sammlung, auf Wunsch gleich mit Kaufpreis.',
  ),
  (
    icon: Icons.collections_bookmark,
    title: 'Deine Sammlung',
    text:
        'Wert, Gewinn seit dem Kauf und Ordner auf einen Blick. Karte antippen: Preis, '
        'Verlauf und deine Exemplare – dort auch bearbeiten, verschieben oder tauschen.',
  ),
  (
    icon: Icons.notifications_active,
    title: 'Merkliste und Alarme',
    text:
        'Merke dir Karten, die dir noch fehlen. Mit der Glocke auf der Kartenseite setzt du '
        'einen Preisalarm – dein Handy meldet sich, wenn der Preis dein Ziel erreicht.',
  ),
];

/// Vollbild-Anleitung; schließt sich mit „Los geht’s“ oder „Überspringen“.
Future<void> showOnboarding(BuildContext context) => Navigator.of(
  context,
).push(MaterialPageRoute<void>(fullscreenDialog: true, builder: (_) => const OnboardingScreen()));

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _last => _page == _pages.length - 1;

  void _next() => _last
      ? Navigator.of(context).pop()
      : _controller.nextPage(duration: const Duration(milliseconds: 250), curve: Curves.easeOut);

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Column(
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              key: const Key('onboarding-skip'),
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Überspringen'),
            ),
          ),
          Expanded(
            child: PageView(
              controller: _controller,
              onPageChanged: (page) => setState(() => _page = page),
              children: [for (final page in _pages) _PageBody(page: page)],
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (var index = 0; index < _pages.length; index++)
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  margin: const EdgeInsets.all(4),
                  width: index == _page ? 20 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: index == _page ? AppColors.primary : AppColors.outline,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton(
                key: const Key('onboarding-next'),
                onPressed: _next,
                child: Text(_last ? 'Los geht’s' : 'Weiter'),
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

class _PageBody extends StatelessWidget {
  const _PageBody({required this.page});

  final _Page page;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 32),
    child: Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 120,
          height: 120,
          decoration: const BoxDecoration(gradient: AppColors.scanGradient, shape: BoxShape.circle),
          child: Icon(page.icon, size: 56, color: Colors.white),
        ),
        const SizedBox(height: 32),
        Text(
          page.title,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        Text(
          page.text,
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 16, height: 1.4, color: AppColors.textMuted),
        ),
      ],
    ),
  );
}
