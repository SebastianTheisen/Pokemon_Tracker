// Wiederverwendbare Bausteine: Ladeanzeige, Fehler, Kartenbild, Abschnittstitel.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api.dart';
import '../core/format.dart';
import '../core/theme.dart';
import '../models/models.dart';

/// Zeigt Laden/Fehler/Daten eines Providers einheitlich an.
class AsyncBody<T> extends StatelessWidget {
  const AsyncBody({required this.value, required this.builder, this.onRetry, super.key});

  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => value.when(
    data: builder,
    loading: () => const Center(child: CircularProgressIndicator()),
    error: (error, _) => ErrorView(message: '$error', onRetry: onRetry),
  );
}

class ErrorView extends StatelessWidget {
  const ErrorView({required this.message, this.onRetry, super.key});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: AppColors.loss, size: 40),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          if (onRetry != null) ...[
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onRetry, child: const Text('Erneut versuchen')),
          ],
        ],
      ),
    ),
  );
}

class EmptyView extends StatelessWidget {
  const EmptyView({required this.icon, required this.message, this.action, super.key});

  final IconData icon;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: AppColors.textMuted),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.textMuted),
          ),
          if (action != null) ...[const SizedBox(height: 16), action!],
        ],
      ),
    ),
  );
}

/// Kartenbild im Kartenformat (63:88) mit Platzhalter.
class CardImage extends StatelessWidget {
  const CardImage({required this.url, this.width = 56, super.key});

  final String? url;
  final double width;

  @override
  Widget build(BuildContext context) {
    final placeholder = Container(
      color: AppColors.surfaceHigh,
      alignment: Alignment.center,
      child: Icon(Icons.style, color: AppColors.textMuted, size: width / 2.5),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(width / 14),
      child: SizedBox(
        width: width,
        height: width * 88 / 63,
        child: url == null
            ? placeholder
            : Image.network(
                url!,
                fit: BoxFit.cover,
                // Web: Bilder fremder Server ohne CORS über ein <img>-Element laden.
                webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
                errorBuilder: (_, _, _) => placeholder,
              ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {this.trailing, super.key});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
    child: Row(
      children: [
        Expanded(
          child: Text(
            text,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        ?trailing,
      ],
    ),
  );
}

/// Kleines Etikett, z. B. Sprache „JA“ oder „Schätzung“.
class Tag extends StatelessWidget {
  const Tag(this.text, {this.color = AppColors.primary, super.key});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.18),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Text(
      text,
      style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
    ),
  );
}

/// Kartenzeile für Listen (Suche, Merkliste, Scan-Alternativen).
class CardTile extends StatelessWidget {
  const CardTile({required this.card, this.trailing, this.onTap, super.key});

  final CardInfo card;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => ListTile(
    onTap: onTap,
    leading: CardImage(url: card.image(), width: 40),
    title: Row(
      children: [
        Flexible(child: Text(card.displayName, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 6),
        Tag(languageTag(card.language)),
      ],
    ),
    subtitle: Text(
      [?card.originalName, card.subtitle].join(' · '),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(color: AppColors.textMuted),
    ),
    trailing: trailing,
  );
}

void showMessage(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

/// Führt eine Aktion aus und zeigt Fehler als Hinweis. Gibt `true` bei Erfolg zurück.
Future<bool> runAction(BuildContext context, Future<void> Function() action) async {
  try {
    await action();
    return true;
  } on ApiException catch (error) {
    if (context.mounted) showMessage(context, error.message);
    return false;
  }
}

/// Einfacher Eingabedialog. Gibt den (getrimmten) Text zurück oder `null` bei Abbruch.
Future<String?> showTextInput(
  BuildContext context, {
  required String title,
  String initial = '',
  String? label,
  String? helper,
  String confirm = 'OK',
  TextInputType? keyboardType,
}) => showDialog<String>(
  context: context,
  builder: (_) => _TextInputDialog(
    title: title,
    initial: initial,
    label: label,
    helper: helper,
    confirm: confirm,
    keyboardType: keyboardType,
  ),
);

class _TextInputDialog extends StatefulWidget {
  const _TextInputDialog({
    required this.title,
    required this.initial,
    required this.confirm,
    this.label,
    this.helper,
    this.keyboardType,
  });

  final String title;
  final String initial;
  final String confirm;
  final String? label;
  final String? helper;
  final TextInputType? keyboardType;

  @override
  State<_TextInputDialog> createState() => _TextInputDialogState();
}

class _TextInputDialogState extends State<_TextInputDialog> {
  late final _controller = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() => Navigator.of(context).pop(_controller.text.trim());

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.title),
    content: TextField(
      controller: _controller,
      autofocus: true,
      keyboardType: widget.keyboardType,
      onSubmitted: (_) => _submit(),
      decoration: InputDecoration(labelText: widget.label, helperText: widget.helper),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Abbrechen')),
      FilledButton(onPressed: _submit, child: Text(widget.confirm)),
    ],
  );
}
