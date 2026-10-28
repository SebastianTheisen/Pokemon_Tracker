"""Englische Namen japanischer One-Piece-Karten und -Sets (``name_en``)

Die offiziellen Listen (EN/JP) nutzen dieselben Kartennummern; die App zeigt den englischen
Namen wie die deutsche Übersetzung bei Pokémon, die Suche findet japanische Karten auch über
ihn. Befüllt wird beim Import (``fill_english_names``) und hier einmal für den Bestand.

Revision ID: 0023_onepiece_english_names
Revises: 0022_games
Create Date: 2026-10-28 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_onepiece_english_names"
down_revision: str | Sequence[str] | None = "0022_games"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stand der Abfrage aus app.services.onepiece_catalog bei Erstellung der Migration.
CARD_NAMES = r"""
UPDATE cards AS ja
SET name_en = en.base || coalesce(substring(ja.name from '( \((Parallel|Reprint)\))$'), '')
FROM card_sets AS ja_set,
     (SELECT DISTINCT ON (regexp_replace(c.external_id, '_[pr][0-9]+$', ''))
             regexp_replace(c.external_id, '_[pr][0-9]+$', '') AS code,
             regexp_replace(c.name, ' \((Parallel|Reprint)\)$', '') AS base
      FROM cards AS c JOIN card_sets AS s ON s.id = c.set_id
      WHERE s.game = 'onepiece' AND c.language = 'en' AND c.external_id IS NOT NULL
      ORDER BY regexp_replace(c.external_id, '_[pr][0-9]+$', ''), c.external_id) AS en
WHERE ja_set.id = ja.set_id AND ja_set.game = 'onepiece' AND ja.language <> 'en'
  AND regexp_replace(ja.external_id, '_[pr][0-9]+$', '') = en.code
"""
SET_NAMES = """
UPDATE card_sets AS ja SET name_en = en.name
FROM card_sets AS en
WHERE ja.game = 'onepiece' AND en.game = 'onepiece' AND ja.language <> 'en'
  AND en.language = 'en' AND en.external_id = ja.external_id
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cards", sa.Column("name_en", sa.String(200), nullable=True))
    op.add_column("card_sets", sa.Column("name_en", sa.String(200), nullable=True))
    op.create_index(
        "ix_cards_name_en_trgm",
        "cards",
        [sa.literal_column("lower(name_en) gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.execute(CARD_NAMES)
    op.execute(SET_NAMES)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cards_name_en_trgm", table_name="cards", postgresql_using="gin")
    op.drop_column("card_sets", "name_en")
    op.drop_column("cards", "name_en")
