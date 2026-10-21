"""Kartendetails aus TCGdex: Varianten, Illustrator, Zeitpunkt des Abgleichs

Revision ID: 0012_card_details
Revises: 0011_sealed_prices
Create Date: 2026-10-21 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_card_details"
down_revision: str | Sequence[str] | None = "0011_sealed_prices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cards", sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("cards", sa.Column("illustrator", sa.String(length=120), nullable=True))
    op.add_column(
        "cards", sa.Column("details_synced_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cards", "details_synced_at")
    op.drop_column("cards", "illustrator")
    op.drop_column("cards", "variants")
