// Gegradete Karte als „Slab“: Acryl-Hülle mit Etikett der Grading-Firma (Farben, Name,
// Note) – nachempfunden, ohne Logos. Gleiche Fläche wie ein Kartenbild (63:88), damit Raster
// und Listen nicht verrutschen; die schmalere Hülle sitzt mittig.
import 'package:flutter/material.dart';

import '../models/models.dart';
import 'common.dart';

/// Aussehen des Etiketts je Firma.
@immutable
class SlabStyle {
  const SlabStyle({
    required this.label,
    required this.background,
    required this.accent,
    required this.text,
    this.border,
  });

  /// Name auf dem Etikett („PSA“, „BECKETT“ …).
  final String label;
  final Color background;

  /// Firmenname und Rahmenfarbe (PSA rot, CGC blau, BGS-Gold …).
  final Color accent;
  final Color text;
  final Color? border;
}

const _psaRed = Color(0xFFC8102E);
const _gold = Color(0xFFD4AF37);

/// Etikett je Firma; Black Label (BGS 10 „BL“) und Pristine 10 bekommen Gold auf Schwarz.
SlabStyle slabStyle(String company, String? grade) {
  final blackLabel = (grade ?? '').toUpperCase().contains('BL');
  return switch (company.toUpperCase()) {
    'PSA' => const SlabStyle(
      label: 'PSA',
      background: Colors.white,
      accent: _psaRed,
      text: Color(0xFF111111),
      border: _psaRed,
    ),
    'BGS' when blackLabel => const SlabStyle(
      label: 'BECKETT',
      background: Color(0xFF111111),
      accent: _gold,
      text: _gold,
    ),
    'BGS' => SlabStyle(
      label: 'BECKETT',
      background: const Color(0xFFDDE1E6),
      accent: (double.tryParse(grade ?? '') ?? 0) >= 9.5 ? _gold : const Color(0xFF6B7480),
      text: const Color(0xFF111111),
    ),
    'CGC' => const SlabStyle(
      label: 'CGC',
      background: Colors.white,
      accent: Color(0xFF0B5FA5),
      text: Color(0xFF111111),
      border: Color(0xFF0B5FA5),
    ),
    'SGC' => const SlabStyle(
      label: 'SGC',
      background: Color(0xFF151515),
      accent: Colors.white,
      text: Colors.white,
    ),
    'TAG' => const SlabStyle(
      label: 'TAG',
      background: Color(0xFF1C1C1E),
      accent: Color(0xFF9BE15D),
      text: Colors.white,
    ),
    'ACE' => const SlabStyle(
      label: 'ACE',
      background: Colors.white,
      accent: Color(0xFF6A3FB5),
      text: Color(0xFF111111),
      border: Color(0xFF6A3FB5),
    ),
    final other => SlabStyle(
      label: other == 'OTHER' ? 'GRADED' : other,
      background: const Color(0xFFECEFF3),
      accent: const Color(0xFF4A5563),
      text: const Color(0xFF111111),
    ),
  };
}

/// Einstufung zur Note, wie sie auf den Etiketten steht („GEM MT“ bei PSA 10).
String gradeDescriptor(String company, String? grade) {
  final value = double.tryParse((grade ?? '').replaceAll(RegExp('[^0-9.]'), ''));
  if (value == null) return '';
  if ((grade ?? '').toUpperCase().contains('BL')) return 'BLACK LABEL';
  if (company.toUpperCase() == 'PSA') {
    return switch (value) {
      >= 10 => 'GEM MT',
      >= 9 => 'MINT',
      >= 8 => 'NM-MT',
      >= 7 => 'NM',
      >= 6 => 'EX-MT',
      >= 5 => 'EX',
      >= 4 => 'VG-EX',
      >= 3 => 'VG',
      >= 2 => 'GOOD',
      _ => 'PR',
    };
  }
  return switch (value) {
    >= 10 => 'PRISTINE',
    >= 9.5 => 'GEM MINT',
    >= 9 => 'MINT',
    >= 8 => 'NM-MT',
    >= 7 => 'NM',
    _ => '',
  };
}

/// Hülle eines Slabs (Breite : Höhe), z. B. PSA ca. 3,3 × 5,3 Zoll.
const slabRatio = 0.62;

class SlabFrame extends StatelessWidget {
  const SlabFrame({
    required this.company,
    required this.grade,
    required this.imageUrl,
    this.width = 104,
    super.key,
  });

  final String company;
  final String? grade;
  final String? imageUrl;

  /// Breite der Fläche (wie [CardImage]); die Höhe ergibt sich aus 63:88.
  final double width;

  @override
  Widget build(BuildContext context) {
    final height = width * 88 / 63;
    final slabWidth = (height * slabRatio).clamp(0.0, width);
    final style = slabStyle(company, grade);
    final compact = slabWidth < 64; // Listen-Vorschau: nur Farbstreifen mit Note
    final inset = slabWidth * 0.06;
    final labelHeight = height * (compact ? 0.2 : 0.19);
    final gradeText = (grade ?? '').replaceAll(RegExp(r'\s*BL$', caseSensitive: false), '');
    return SizedBox(
      key: Key('slab-$company'),
      width: width,
      height: height,
      child: Center(
        child: Container(
          width: slabWidth,
          height: height,
          padding: EdgeInsets.all(inset),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(slabWidth * 0.07),
            // Acryl: hell, leicht spiegelnd, mit dunkler Kante.
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFFF4F6F9), Color(0xFFC9D0D9), Color(0xFFEDEFF3)],
              stops: [0, 0.55, 1],
            ),
            border: Border.all(color: const Color(0xFF8A939E), width: compact ? 0.8 : 1.2),
            boxShadow: const [
              BoxShadow(color: Color(0x40000000), blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Label(
                style: style,
                grade: gradeText,
                descriptor: compact ? '' : gradeDescriptor(company, grade),
                height: labelHeight,
                compact: compact,
              ),
              SizedBox(height: inset),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF0E1116),
                    borderRadius: BorderRadius.circular(slabWidth * 0.03),
                  ),
                  padding: EdgeInsets.all(inset * 0.6),
                  child: FittedBox(
                    child: CardImage(url: imageUrl, width: slabWidth),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label({
    required this.style,
    required this.grade,
    required this.descriptor,
    required this.height,
    required this.compact,
  });

  final SlabStyle style;
  final String grade;
  final String descriptor;
  final double height;
  final bool compact;

  @override
  Widget build(BuildContext context) => Container(
    height: height,
    padding: EdgeInsets.symmetric(horizontal: height * 0.18),
    decoration: BoxDecoration(
      color: style.background,
      borderRadius: BorderRadius.circular(height * 0.12),
      border: style.border == null
          ? null
          : Border.all(color: style.border!, width: compact ? 1 : height * 0.06),
    ),
    child: Row(
      children: [
        if (!compact)
          Expanded(
            child: FittedBox(
              alignment: Alignment.centerLeft,
              fit: BoxFit.scaleDown,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    style.label,
                    style: TextStyle(
                      color: style.accent,
                      fontWeight: FontWeight.w900,
                      fontStyle: FontStyle.italic,
                      fontSize: height * 0.42,
                      height: 1,
                      letterSpacing: 0.5,
                    ),
                  ),
                  if (descriptor.isNotEmpty)
                    Text(
                      descriptor,
                      style: TextStyle(
                        color: style.text,
                        fontWeight: FontWeight.w700,
                        fontSize: height * 0.24,
                        height: 1.2,
                      ),
                    ),
                ],
              ),
            ),
          ),
        if (compact) const Spacer() else SizedBox(width: height * 0.15),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            grade,
            style: TextStyle(
              color: compact ? style.accent : style.text,
              fontWeight: FontWeight.w900,
              fontSize: height * (compact ? 0.7 : 0.62),
              height: 1,
            ),
          ),
        ),
        if (compact) const Spacer(),
      ],
    ),
  );
}

/// Bild einer Position: gegradete Karten als Slab, alles andere als normales Kartenbild.
Widget itemImage(CollectionItem item, {required double width}) {
  if (item.kind == 'graded' && item.gradingCompany != null) {
    return SlabFrame(
      company: item.gradingCompany!,
      grade: item.grade,
      imageUrl: item.image,
      width: width,
    );
  }
  return CardImage(url: item.image, width: width, contain: item.card == null);
}
