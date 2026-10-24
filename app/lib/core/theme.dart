// Navy-Theme mit Blau-/Violett-Akzenten (Plan 2.8) – dunkel und hell, folgt dem Handy oder
// der Wahl unter Einstellungen.
import 'package:flutter/material.dart';

/// Farbsatz für ein Erscheinungsbild.
@immutable
class _Palette {
  const _Palette({
    required this.background,
    required this.surface,
    required this.surfaceHigh,
    required this.outline,
    required this.textMuted,
    required this.gain,
    required this.loss,
    required this.warning,
  });

  final Color background;
  final Color surface;
  final Color surfaceHigh;
  final Color outline;
  final Color textMuted;
  final Color gain;
  final Color loss;
  final Color warning;
}

const _dark = _Palette(
  background: Color(0xFF0B1426),
  surface: Color(0xFF13203A),
  surfaceHigh: Color(0xFF1B2B4B),
  outline: Color(0xFF2A3B5E),
  textMuted: Color(0xFF93A3C4),
  gain: Color(0xFF22C55E),
  loss: Color(0xFFEF4444),
  warning: Color(0xFFF59E0B),
);

// Hell: dunklere Grün-/Rot-/Orangetöne für genug Kontrast auf Weiß.
const _light = _Palette(
  background: Color(0xFFF4F6FB),
  surface: Color(0xFFFFFFFF),
  surfaceHigh: Color(0xFFE6EBF5),
  outline: Color(0xFFD3DAE8),
  textMuted: Color(0xFF55627F),
  gain: Color(0xFF15803D),
  loss: Color(0xFFDC2626),
  warning: Color(0xFFB45309),
);

/// App-Farben. Die vom Erscheinungsbild abhängigen sind Getter auf den aktiven Farbsatz
/// ([use] setzt ihn, siehe `KartenkisteApp`).
abstract final class AppColors {
  static _Palette _palette = _dark;

  static Brightness get brightness =>
      identical(_palette, _light) ? Brightness.light : Brightness.dark;

  /// Gibt `true` zurück, wenn sich das Erscheinungsbild geändert hat.
  static bool use(Brightness brightness) {
    final next = brightness == Brightness.light ? _light : _dark;
    if (identical(next, _palette)) return false;
    _palette = next;
    return true;
  }

  static Color get background => _palette.background;
  static Color get surface => _palette.surface;
  static Color get surfaceHigh => _palette.surfaceHigh;
  static Color get outline => _palette.outline;
  static Color get textMuted => _palette.textMuted;
  static Color get gain => _palette.gain;
  static Color get loss => _palette.loss;
  static Color get warning => _palette.warning;

  static const primary = Color(0xFF4C7DFF);
  static const accent = Color(0xFF8B5CF6);

  static const scanGradient = LinearGradient(
    colors: [primary, accent],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}

ThemeData buildTheme(Brightness brightness) {
  AppColors.use(brightness);
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.primary, brightness: brightness)
      .copyWith(
        primary: AppColors.primary,
        secondary: AppColors.accent,
        surface: AppColors.surface,
        error: AppColors.loss,
      );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    // Schwebende Hinweise über der unteren Leiste statt auf ihr.
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.background,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: AppColors.outline),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: AppColors.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: AppColors.outline),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.surface,
      side: BorderSide(color: AppColors.outline),
    ),
    dividerTheme: DividerThemeData(color: AppColors.outline, space: 1),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      showDragHandle: true,
    ),
  );
}
