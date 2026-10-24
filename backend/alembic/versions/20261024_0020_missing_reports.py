"""Meldungen Das fehlt

Revision ID: 0020_missing_reports
Revises: 0019_showcase_trades
Create Date: 2026-10-24 17:31:47.946875

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_missing_reports"
down_revision: str | Sequence[str] | None = "0019_showcase_trades"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "missing_reports",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "card", "sealed", "wrong", "other", name="reportkind", native_enum=False, length=12
            ),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("context", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_missing_reports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_missing_reports")),
    )
    op.create_index(
        op.f("ix_missing_reports_user_id"), "missing_reports", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_missing_reports_user_id"), table_name="missing_reports")
    op.drop_table("missing_reports")
