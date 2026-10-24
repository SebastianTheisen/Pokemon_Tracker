// Anmelden, Registrieren (nur mit Einladungscode) und Passwort zurücksetzen (Code vom Admin).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/config.dart';
import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../widgets/common.dart';

const minPasswordLength = 10;

String? requiredField(String? value) =>
    (value == null || value.trim().isEmpty) ? 'Bitte ausfüllen' : null;

String? emailField(String? value) {
  final text = value?.trim() ?? '';
  if (text.isEmpty) return 'Bitte ausfüllen';
  return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(text) ? null : 'Keine gültige E-Mail';
}

String? passwordField(String? value) =>
    (value ?? '').length < minPasswordLength ? 'Mindestens $minPasswordLength Zeichen' : null;

/// Gemeinsamer Rahmen der Anmeldeseiten.
class _AuthFrame extends StatelessWidget {
  const _AuthFrame({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.inventory_2_rounded, size: 56, color: AppColors.accent),
                const SizedBox(height: 8),
                Text(
                  appName,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.textMuted),
                ),
                const SizedBox(height: 28),
                ...children,
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class _SubmitButton extends StatelessWidget {
  const _SubmitButton({required this.label, required this.busy, required this.onPressed});

  final String label;
  final bool busy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => FilledButton(
    onPressed: busy ? null : onPressed,
    child: busy
        ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
        : Text(label),
  );
}

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(sessionProvider.notifier).login(_email.text, _password.text);
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => _AuthFrame(
    title: 'Deine Sammlung, immer dabei',
    children: [
      Form(
        key: _form,
        child: AutofillGroup(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                key: const Key('login-email'),
                controller: _email,
                decoration: const InputDecoration(labelText: 'E-Mail'),
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                validator: emailField,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('login-password'),
                controller: _password,
                decoration: const InputDecoration(labelText: 'Passwort'),
                obscureText: true,
                autofillHints: const [AutofillHints.password],
                validator: requiredField,
                onFieldSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 20),
              _SubmitButton(label: 'Anmelden', busy: _busy, onPressed: _submit),
            ],
          ),
        ),
      ),
      const SizedBox(height: 16),
      TextButton(
        onPressed: () => context.push('/register'),
        child: const Text('Neu hier? Mit Einladungscode registrieren'),
      ),
      TextButton(
        onPressed: () => context.push('/reset'),
        child: const Text('Passwort vergessen? Code vom Admin einlösen'),
      ),
    ],
  );
}

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _code = TextEditingController();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    for (final controller in [_code, _name, _email, _password]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref
          .read(sessionProvider.notifier)
          .register(
            inviteCode: _code.text,
            email: _email.text,
            password: _password.text,
            displayName: _name.text,
          );
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => _AuthFrame(
    title: 'Registrieren – nur mit Einladungscode',
    children: [
      Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              controller: _code,
              decoration: const InputDecoration(labelText: 'Einladungscode'),
              textCapitalization: TextCapitalization.characters,
              validator: requiredField,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Anzeigename'),
              validator: requiredField,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _email,
              decoration: const InputDecoration(labelText: 'E-Mail'),
              keyboardType: TextInputType.emailAddress,
              validator: emailField,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _password,
              decoration: const InputDecoration(
                labelText: 'Passwort',
                helperText: 'Mindestens $minPasswordLength Zeichen',
              ),
              obscureText: true,
              validator: passwordField,
            ),
            const SizedBox(height: 12),
            TextFormField(
              decoration: const InputDecoration(labelText: 'Passwort wiederholen'),
              obscureText: true,
              validator: (value) =>
                  value == _password.text ? null : 'Passwörter stimmen nicht überein',
            ),
            const SizedBox(height: 20),
            _SubmitButton(label: 'Konto anlegen', busy: _busy, onPressed: _submit),
          ],
        ),
      ),
      const SizedBox(height: 12),
      TextButton(onPressed: () => context.pop(), child: const Text('Zurück zur Anmeldung')),
    ],
  );
}

class ResetPasswordScreen extends ConsumerStatefulWidget {
  const ResetPasswordScreen({super.key});

  @override
  ConsumerState<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends ConsumerState<ResetPasswordScreen> {
  final _form = GlobalKey<FormState>();
  final _code = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _code.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(apiProvider).resetPassword(_code.text.trim(), _password.text);
      if (!mounted) return;
      showMessage(context, 'Passwort geändert – bitte neu anmelden.');
      context.pop();
    } on ApiException catch (error) {
      if (mounted) showMessage(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => _AuthFrame(
    title: 'Passwort zurücksetzen mit dem Code vom Admin',
    children: [
      Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              controller: _code,
              decoration: const InputDecoration(labelText: 'Code vom Admin'),
              textCapitalization: TextCapitalization.characters,
              validator: requiredField,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _password,
              decoration: const InputDecoration(labelText: 'Neues Passwort'),
              obscureText: true,
              validator: passwordField,
            ),
            const SizedBox(height: 20),
            _SubmitButton(label: 'Passwort setzen', busy: _busy, onPressed: _submit),
          ],
        ),
      ),
      const SizedBox(height: 12),
      TextButton(onPressed: () => context.pop(), child: const Text('Zurück zur Anmeldung')),
    ],
  );
}
