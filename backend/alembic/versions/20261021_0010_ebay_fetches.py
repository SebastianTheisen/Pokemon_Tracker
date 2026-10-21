"""eBay.de-Abrufe über Apify (gemerkte Rohzeilen, Kosten)

Revision ID: 0010_ebay_fetches
Revises: 0009_cardmarket_catalog
Create Date: 2026-10-21 14:51:54.388071

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_ebay_fetches"
down_revision: str | Sequence[str] | None = "0009_cardmarket_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ebay_fetches",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("page_url", sa.String(length=500), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=5), nullable=True),
        sa.Column("requested_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["cards.id"],
            name=op.f("fk_ebay_fetches_card_id_cards"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_ebay_fetches_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ebay_fetches")),
    )
    op.create_index(
        "ix_ebay_fetches_lookup", "ebay_fetches", ["card_id", "query", "fetched_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ebay_fetches_lookup", table_name="ebay_fetches")
    op.drop_table("ebay_fetches")
