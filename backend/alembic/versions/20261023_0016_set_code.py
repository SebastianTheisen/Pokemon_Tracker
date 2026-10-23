"""Offizielles Setkürzel (z. B. „PFL“) für die Suche „PFL077“

Revision ID: 0016_set_code
Revises: 0015_pricecharting_details
Create Date: 2026-10-23 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_set_code"
down_revision: str | Sequence[str] | None = "0015_pricecharting_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("card_sets", sa.Column("code", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("card_sets", "code")
