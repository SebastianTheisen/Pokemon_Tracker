"""Bewertung von Katalog-Kandidaten eines Scans (Plan 5.6, Schritte 5 und 7).

Jeder Kandidat sammelt Punkte, jede Punktquelle wird als Begründung mitgeliefert:

=========================  ======  ===============================================
Merkmal                    Punkte  Beispiel
=========================  ======  ===============================================
Nummer passt               0,30    ``110`` gelesen, Karte hat ``110``
Setgröße passt             0,20    ``/098`` gelesen, Set hat offiziell 98 Karten
Setcode passt              0,25    ``S12`` (bzw. „512“) gelesen, Set-ID ``S12``
Name passt                 ≤ 0,35  „ルギアV“ ↔ „ルギアV“ (unscharf, Logos wie „ex“ egal)
Bildabgleich               ≤ 0,60  RANSAC-Inlier; volle Punkte ab 150
Sprache passt nicht        − 0,05 … 0,30
=========================  ======  ===============================================

**Sicherer Treffer** (die App zeigt dann „Erkannt als …“), wenn

* der Bildabgleich ≥ 50 Inlier liefert **oder** Nummer + Setgröße/Setcode + Name/Setcode
  übereinstimmen, **und**
* der Abstand zur besten *anderen* Karte mindestens 0,15 beträgt. Dieselbe Karte in einer
  anderen Sprache zählt nicht als Konkurrenz.

Sonst zeigt die App „Falsche Karte? Selbst suchen“ mit der Kandidatenliste.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.models import Card
from app.scanner.matching import CONFIDENT_INLIERS
from app.scanner.text import LanguageGuess, NameCandidate, TextFeatures, compact_key, name_base

NUMBER_POINTS = 0.30
TOTAL_POINTS = 0.20
SET_CODE_POINTS = 0.25
NAME_POINTS = 0.35
IMAGE_POINTS = 0.60
IMAGE_FULL_INLIERS = 150
CONFIDENT_MARGIN = 0.15
MIN_CONFIDENT_SCORE = 0.6
MIN_NAME_SIMILARITY = 0.6
STRONG_LANGUAGE_PENALTY = 0.25
HINT_LANGUAGE_PENALTY = 0.30
WEAK_LANGUAGE_PENALTY = 0.05
_MIN_CONTAINED_RATIO = 0.6


def name_similarity(names: Sequence[NameCandidate], card_name: str) -> float:
    """Wie gut passt der beste Namenskandidat zum Kartennamen (0..1)?"""
    card_key = compact_key(card_name)
    card_base = name_base(card_key)
    best = 0.0
    for candidate in names:
        if candidate.key == card_key:
            return 1.0
        if candidate.base == card_base:
            score = 0.95  # nur der Logo-Zusatz fehlt („ルギア“ ↔ „ルギアV“)
        elif card_base in candidate.key and len(card_base) >= _MIN_CONTAINED_RATIO * len(
            candidate.key
        ):
            score = 0.85  # OCR hängt etwas an („TeamRocketsMewtuX“)
        elif candidate.base in card_base and len(candidate.base) >= _MIN_CONTAINED_RATIO * len(
            card_base
        ):
            score = 0.6 + 0.3 * len(candidate.base) / len(card_base)  # abgeschnitten
        else:
            ratio = SequenceMatcher(None, candidate.base, card_base).ratio()
            score = 0.9 * ratio if ratio >= MIN_NAME_SIMILARITY else 0.0
        best = max(best, score)
    return best


def language_penalty(card_language: str, guess: LanguageGuess, hint: str | None) -> float:
    """Abzug, wenn die Kartensprache nicht zur erkannten (oder gewählten) Sprache passt."""
    if hint is not None:
        return 0.0 if card_language == hint else HINT_LANGUAGE_PENALTY
    if not guess.languages or card_language == guess.languages[0]:
        return 0.0
    if card_language in guess.languages:  # Deutsch/Englisch bzw. Kurz-/Langzeichen unsicher
        return WEAK_LANGUAGE_PENALTY
    return STRONG_LANGUAGE_PENALTY


@dataclass
class Candidate:
    """Eine Katalogkarte mit ihren Punkten."""

    card: Card
    number_match: bool = False
    total_match: bool = False
    set_code_match: bool = False
    name_score: float = 0.0
    language_penalty: float = 0.0
    catalog_inliers: int | None = None
    reference_inliers: int | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def identity(self) -> str:
        """Gleiche Karte über Sprachen hinweg (TCGdex-ID), eigene Karten über ihre ID."""
        return self.card.external_id or str(self.card.id)

    @property
    def inliers(self) -> int | None:
        values = [v for v in (self.catalog_inliers, self.reference_inliers) if v is not None]
        return max(values) if values else None

    @property
    def text_score(self) -> float:
        score = NAME_POINTS * self.name_score - self.language_penalty
        score += NUMBER_POINTS if self.number_match else 0.0
        score += TOTAL_POINTS if self.total_match else 0.0
        score += SET_CODE_POINTS if self.set_code_match else 0.0
        return score

    @property
    def image_score(self) -> float:
        return IMAGE_POINTS * min(self.inliers or 0, IMAGE_FULL_INLIERS) / IMAGE_FULL_INLIERS

    @property
    def score(self) -> float:
        return self.text_score + self.image_score

    @property
    def confidence(self) -> float:
        return round(max(0.0, min(1.0, self.score)), 3)

    @property
    def strong_evidence(self) -> bool:
        """Reicht das für einen sicheren Treffer (ohne Blick auf die Konkurrenz)?"""
        if (self.inliers or 0) >= CONFIDENT_INLIERS:
            return True
        return self.number_match and (
            (self.total_match and self.name_score >= MIN_NAME_SIMILARITY) or self.set_code_match
        )


def score_text(
    candidate: Candidate, text: TextFeatures, *, language_hint: str | None = None
) -> Candidate:
    """Vergibt die Text-Punkte und schreibt die Begründungen."""
    card = candidate.card
    card_set = card.card_set
    reasons: list[str] = []
    for hit in text.numbers:
        if hit.number != card.number_norm:
            continue
        candidate.number_match = True
        if hit.total is not None and card_set.card_count_official == hit.total:
            candidate.total_match = True
            reasons.append(f"Nummer {hit.raw} passt (Set mit {hit.total} Karten)")
            break
    if candidate.number_match and not candidate.total_match:
        reasons.append(f"Nummer {card.number} passt")
    set_code = card_set.external_id.casefold()
    if set_code in text.set_codes or set_code.replace("-", "") in text.set_codes:
        candidate.set_code_match = True
        reasons.append(f"Setcode {card_set.external_id}")
    candidate.name_score = name_similarity(text.names, card.name)
    if candidate.name_score >= MIN_NAME_SIMILARITY:
        reasons.append(f"Name ähnlich „{card.name}“ ({candidate.name_score:.0%})")
    candidate.language_penalty = language_penalty(card.language, text.language, language_hint)
    if candidate.language_penalty >= STRONG_LANGUAGE_PENALTY:
        expected = language_hint or text.language.primary
        reasons.append(f"Sprache {card.language} statt {expected}")
    candidate.reasons = reasons
    return candidate


def add_image_reasons(candidate: Candidate) -> None:
    if candidate.catalog_inliers:
        candidate.reasons.append(f"Bildabgleich Katalog: {candidate.catalog_inliers}")
    if candidate.reference_inliers:
        candidate.reasons.append(f"Eigenes Referenzbild: {candidate.reference_inliers}")


def rank(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Beste zuerst; bei Gleichstand neuere Sets vor älteren."""
    return sorted(
        candidates,
        key=lambda c: (
            -c.score,
            -(c.card.card_set.release_date.toordinal() if c.card.card_set.release_date else 0),
            c.card.language,
        ),
    )


def is_confident(ranked: Sequence[Candidate]) -> bool:
    """Sicherer Treffer? Siehe Modul-Doku."""
    if not ranked:
        return False
    best = ranked[0]
    if not best.strong_evidence or best.score < MIN_CONFIDENT_SCORE:
        return False
    competitor = next((c for c in ranked[1:] if c.identity != best.identity), None)
    return competitor is None or best.score - competitor.score >= CONFIDENT_MARGIN
