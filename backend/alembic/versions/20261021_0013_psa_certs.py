"""Gemerkte PSA-Zertifikate (Daten der offiziellen PSA-API)

Revision ID: 0013_psa_certs
Revises: 0012_card_details
Create Date: 2026-10-21 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_psa_certs"
down_revision: str | Sequence[str] | None = "0012_card_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "psa_certs",
        sa.Column("cert", sa.String(length=12), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cert", name=op.f("pk_psa_certs")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("psa_certs")
