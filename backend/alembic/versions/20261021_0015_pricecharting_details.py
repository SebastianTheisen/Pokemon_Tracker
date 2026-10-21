"""PriceCharting-Details je Karte (POP-Report, Verkaufszahlen, letzte Verkäufe, Verlauf)

Revision ID: 0015_pricecharting_details
Revises: 0014_sealed_images
Create Date: 2026-10-21 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_pricecharting_details"
down_revision: str | Sequence[str] | None = "0014_sealed_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pricecharting_details",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("product_url", sa.String(length=500), nullable=True),
        sa.Column("population", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sales_volume", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recent_sales", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("price_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("images", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["cards.id"],
            name=op.f("fk_pricecharting_details_card_id_cards"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("card_id", name=op.f("pk_pricecharting_details")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("pricecharting_details")
