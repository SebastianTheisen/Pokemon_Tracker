"""Karten: gespeicherter Vergleichsschlüssel ``name_key`` mit Trigramm-Index (Scanner-Suche)

Die Namenssuche des Scanners verglich ``translate(lower(name), …)`` – ohne Index, also über
alle Karten bei jeder Anfrage (Binder-Scan auf dem Server: 10 von 28 Sekunden).

Revision ID: 0024_card_name_key
Revises: 0023_onepiece_english_names
Create Date: 2026-10-28 17:15:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_card_name_key"
down_revision: str | Sequence[str] | None = "0023_onepiece_english_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stand von app.models.catalog.NAME_KEY_SQL bei Erstellung der Migration.
NAME_KEY_SQL = (
    "translate(lower(name), 'ァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎ .,''’`\"-·・', "  # noqa: RUF001
    "'アイウエオツヤユヨワカケあいうえおつやゆよわ')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cards",
        sa.Column("name_key", sa.Text(), sa.Computed(NAME_KEY_SQL, persisted=True), nullable=True),
    )
    op.create_index(
        "ix_cards_name_key_trgm",
        "cards",
        [sa.literal_column("name_key gin_trgm_ops")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cards_name_key_trgm", table_name="cards", postgresql_using="gin")
    op.drop_column("cards", "name_key")
