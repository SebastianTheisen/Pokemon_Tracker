"""Showcase-Ordner und Tausche

Revision ID: 0019_showcase_trades
Revises: 0018_price_alerts
Create Date: 2026-10-24 14:13:46.745393

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019_showcase_trades"
down_revision: str | Sequence[str] | None = "0018_price_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trades",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("partner", sa.String(length=80), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("give_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("get_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_trades_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
    )
    op.create_index(op.f("ix_trades_user_id"), "trades", ["user_id"], unique=False)
    op.add_column(
        "folders",
        sa.Column("shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("folders", "shared")
    op.drop_index(op.f("ix_trades_user_id"), table_name="trades")
    op.drop_table("trades")
