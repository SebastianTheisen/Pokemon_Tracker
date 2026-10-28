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
Nachdruck unterschieden    0,20    Stempel der 30th Celebration im Foto (:mod:`twins`)
Set der Binderseite        0,15    übrige Karten der Seite sicher aus demselben Set
Setgröße widerspricht      − 0,30  ``001/032`` gelesen, Set hat 102 Karten (nie sicher)
=========================  ======  ===============================================

**Sicherer Treffer** (die App zeigt dann „Erkannt als …“), wenn

* der Bildabgleich ≥ 50 Inlier liefert **oder** Nummer + Setgröße/Setcode + Name/Setcode
  übereinstimmen, **und**
* der Abstand zur besten *anderen* Karte mindestens 0,15 beträgt, **und**
* die gelesene Setgröße dem Set nicht widerspricht. Beispiel Classic Collection (2023):
  gleiche Grafik wie das Grundset 1996 – der Bildabgleich allein fände die alte Karte.

Dieselbe Karte in einer anderen Sprache zählt nicht als Konkurrenz.

Gleiches Motiv mit gleicher Nummer in mehreren Sets (Nachdrucke) und kein klarer
Unterschied im Bild: nie sicher. Ebenso, wenn eine Karte aus einem anderen Set im Bildabgleich
fast gleich gut abschneidet (gleiche Grafik, z. B. Grundset 1996 und Classic Collection 2023)
und kein Text (Nummer + Setgröße/Setcode) den Treffer belegt.

Sonst zeigt die App „Falsche Karte? Selbst suchen“ mit der Kandidatenliste.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
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
TWIN_POINTS = 0.20
# Bildabgleich gilt nur als Beleg, wenn die beste andere Karte deutlich weniger Inlier hat.
SAME_ARTWORK_RATIO = 0.7
# Gleicher Name in einem anderen Set: schon diese Inlier (und Anteil) machen das Bild fraglich –
# ein schwaches Katalogbild der richtigen Fassung (TCGplayer, klein) verliert sonst gegen ein
# scharfes der falschen (Classic-Binder 28.10.: Bisasam). Andere Grafiken liegen meist < 20.
SAME_NAME_MIN_INLIERS = 25
SAME_NAME_RATIO = 0.3
CONFLICT_PENALTY = 0.30
# So viele Ziffern dürfen zwischen gelesener und offizieller Setgröße abweichen, ohne dass
# es als Widerspruch gilt (OCR: „167“ statt „187“).
_TOTAL_DIGIT_TOLERANCE = 1
PAGE_SET_POINTS = 0.15
_MIN_CONTAINED_RATIO = 0.6
_VARIANT_SUFFIX = re.compile(r"\s*\((?:Parallel|Reprint)\)$")


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
    twin_points: float = 0.0
    twin_undecided: bool = False
    page_set_points: float = 0.0
    # Gelesene Setgröße passt nicht zum Set der Karte (z. B. Nachdruck mit gleicher Grafik).
    total_conflict: bool = False
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
        score -= CONFLICT_PENALTY if self.total_conflict else 0.0
        return score

    @property
    def image_score(self) -> float:
        return IMAGE_POINTS * min(self.inliers or 0, IMAGE_FULL_INLIERS) / IMAGE_FULL_INLIERS

    @property
    def score(self) -> float:
        return self.text_score + self.image_score + self.twin_points + self.page_set_points

    @property
    def confidence(self) -> float:
        return round(max(0.0, min(1.0, self.score)), 3)

    @property
    def strong_evidence(self) -> bool:
        """Reicht das für einen sicheren Treffer (ohne Blick auf die Konkurrenz)?"""
        if self.total_conflict:
            return False
        if (self.inliers or 0) >= CONFIDENT_INLIERS:
            return True
        return self.number_match and (
            (self.total_match and self.name_score >= MIN_NAME_SIMILARITY) or self.set_code_match
        )


def digit_distance(first: int, second: int) -> int:
    """Abweichende Ziffern zweier Zahlen (gleich lang aufgefüllt): 167 ↔ 187 → 1."""
    a, b = str(first), str(second)
    width = max(len(a), len(b))
    return sum(x != y for x, y in zip(a.zfill(width), b.zfill(width), strict=True))


def total_conflict(text: TextFeatures, card: Card) -> int | None:
    """Gelesene Setgröße, die dem Set der Karte widerspricht – oder ``None``.

    Widerspruch nur, wenn *keine* gelesene Setgröße passt (auch nicht mit einer falsch
    gelesenen Ziffer) und die Nummer selbst nicht übereinstimmt."""
    # Ohne offizielle Zahl (Sets von PriceCharting, z. B. Grundset 1996) die Kartenzahl im
    # Katalog – sonst widerspräche „001/032“ dem Grundset nie.
    official = card.card_set.card_count_official or card.card_set.card_count_total
    if not official:
        return None
    # Gleiche Nummer hebt den Widerspruch auf – nur nicht bei Sets ohne offizielle Zahl:
    # PriceCharting nummeriert japanische Vintage-Karten nach Pokédex (Bisasam = „1“), das
    # passt zufällig zu „001/032“.
    if card.card_set.card_count_official and any(
        hit.number == card.number_norm for hit in text.numbers
    ):
        return None
    # Nur vollständig gelesene Setgrößen zählen: „001/032“ hat drei Stellen wie „102“;
    # „212/38“ (abgeschnitten, eigentlich 217/187) widerspricht nichts.
    totals = [
        hit.total
        for hit in text.numbers
        if hit.total is not None and len(_printed_total(hit.raw)) >= len(str(official))
    ]
    if not totals or any(
        digit_distance(total, official) <= _TOTAL_DIGIT_TOLERANCE for total in totals
    ):
        return None
    return totals[0]


def _printed_total(raw: str) -> str:
    """Ziffern hinter dem Schrägstrich, wie gedruckt („001/032“ → „032“)."""
    _, _, after = raw.partition("/")
    return "".join(char for char in after if char.isdigit())


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
        if hit.source == "onepiece":
            # „OP01-001“ nennt Set und Nummer zugleich – zählt wie Nummer + Setcode.
            candidate.set_code_match = True
            reasons.append(f"Kartennummer {card.number} passt")
            break
        if hit.total is not None and card_set.card_count_official == hit.total:
            candidate.total_match = True
            reasons.append(f"Nummer {hit.raw} passt (Set mit {hit.total} Karten)")
            break
    if candidate.number_match and not candidate.total_match and not candidate.set_code_match:
        reasons.append(f"Nummer {card.number} passt")
    if (read_total := total_conflict(text, card)) is not None:
        candidate.total_conflict = True
        reasons.append(
            f"Gelesene Setgröße /{read_total:03d} passt nicht "
            f"(Set hat {card_set.card_count_official or card_set.card_count_total} Karten)"
            " – bitte prüfen"
        )
    set_code = card_set.external_id.casefold()
    if set_code in text.set_codes or set_code.replace("-", "") in text.set_codes:
        candidate.set_code_match = True
        reasons.append(f"Setcode {card_set.external_id}")
    # „Roronoa Zoro (Parallel)“: Der Zusatz steht nicht auf der Karte – die Fassung entscheidet
    # der Bildabgleich.
    candidate.name_score = name_similarity(text.names, _VARIANT_SUFFIX.sub("", card.name))
    if candidate.name_score >= MIN_NAME_SIMILARITY:
        reasons.append(f"Name ähnlich „{card.name}“ ({candidate.name_score:.0%})")
    candidate.language_penalty = language_penalty(card.language, text.language, language_hint)
    if candidate.language_penalty >= STRONG_LANGUAGE_PENALTY:
        expected = language_hint or text.language.primary
        reasons.append(f"Sprache {card.language} statt {expected}")
    candidate.reasons = reasons
    return candidate


def apply_page_set(candidates: Sequence[Candidate], set_ids: Collection[object]) -> None:
    """Binderseite: Karten aus den Sets, aus denen die sicher erkannten Nachbarn stammen,
    bekommen :data:`PAGE_SET_POINTS`. Zählt nicht als starker Beleg – sicher wird es erst mit
    Nummer oder Bildabgleich."""
    for candidate in candidates:
        if candidate.card.set_id in set_ids:
            candidate.page_set_points = PAGE_SET_POINTS
            candidate.reasons.append("Gleiches Set wie die übrigen Karten der Seite")


def add_image_reasons(candidate: Candidate) -> None:
    if candidate.catalog_inliers:
        candidate.reasons.append(f"Bildabgleich Katalog: {candidate.catalog_inliers}")
    if candidate.reference_inliers:
        candidate.reasons.append(f"Eigenes Referenzbild: {candidate.reference_inliers}")


def twin_group(ranked: Sequence[Candidate], limit: int) -> list[Candidate]:
    """Der beste Kandidat und Karten gleichen Namens, gleicher Nummer und Sprache aus anderen
    Sets – mögliche Nachdrucke (ob die Grafik gleich ist, prüft :mod:`app.scanner.twins`)."""
    if not ranked:
        return []
    best = ranked[0].card
    key = (best.language, best.number_norm, compact_key(best.name))
    group = [ranked[0]] + [
        candidate
        for candidate in ranked[1:limit]
        if candidate.card.set_id != best.set_id
        and (candidate.card.language, candidate.card.number_norm, compact_key(candidate.card.name))
        == key
    ]
    return group if len(group) > 1 else []


def apply_twins(twins: Sequence[Candidate], winner: Candidate | None) -> None:
    """Ergebnis des Nachdruck-Vergleichs übernehmen.

    Klarer Unterschied: Nachdrucke tragen die Nummer des Originals („43/146“), und die Grafik
    ist dieselbe – Setgröße und Bildabgleich zählen daher für alle gleich, der Gewinner
    bekommt :data:`TWIN_POINTS`. Kein klarer Unterschied: Reihenfolge bleibt, aber unsicher.
    """
    if winner is None:
        for twin in twins:
            twin.twin_undecided = True
            twin.reasons.append("Gleiches Motiv in mehreren Sets – bitte prüfen")
        return
    total = any(twin.total_match for twin in twins)
    inliers = max((twin.catalog_inliers or 0 for twin in twins), default=0)
    for twin in twins:
        twin.total_match = twin.total_match or (total and twin.number_match)
        twin.catalog_inliers = max(twin.catalog_inliers or 0, inliers) or None
    winner.twin_points = TWIN_POINTS
    winner.reasons.append("Druck per Bildvergleich bestimmt (z. B. Jubiläums-Stempel)")


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
    if best.twin_undecided or not best.strong_evidence or best.score < MIN_CONFIDENT_SCORE:
        return False
    competitor = next((c for c in ranked[1:] if c.identity != best.identity), None)
    if competitor is not None and same_artwork(best, competitor):
        return False
    if any(same_name_artwork(best, other) for other in ranked[1:]):
        return False
    return competitor is None or best.score - competitor.score >= CONFIDENT_MARGIN


def text_proves(candidate: Candidate) -> bool:
    """Nummer + Setgröße bzw. Setcode gelesen und passend (unabhängig vom Bild)."""
    return candidate.number_match and (candidate.total_match or candidate.set_code_match)


def same_name_artwork(best: Candidate, other: Candidate) -> bool:
    """Gleiche Karte (Name) aus einem anderen Set schneidet im Bild nennenswert ab und kein
    Text belegt den Treffer – vermutlich dieselbe Grafik nachgedruckt."""
    if (
        text_proves(best)
        or best.card.set_id == other.card.set_id
        or other.identity == best.identity
    ):
        return False
    if name_base(compact_key(best.card.name)) != name_base(compact_key(other.card.name)):
        return False
    other_inliers = other.inliers or 0
    return other_inliers >= max(SAME_NAME_MIN_INLIERS, SAME_NAME_RATIO * (best.inliers or 0))


def same_artwork(best: Candidate, other: Candidate) -> bool:
    """Andere Karte mit fast gleich gutem Bildabgleich und kein Textbeleg: Die Grafik allein
    entscheidet nicht (Nachdrucke derselben Grafik in anderen Sets)."""
    if text_proves(best) or best.card.set_id == other.card.set_id:
        return False
    best_inliers, other_inliers = best.inliers or 0, other.inliers or 0
    return other_inliers >= CONFIDENT_INLIERS and other_inliers >= SAME_ARTWORK_RATIO * best_inliers
