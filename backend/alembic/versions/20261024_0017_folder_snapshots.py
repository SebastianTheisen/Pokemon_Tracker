"""Tageswerte je Ordner (Wertkurve je Portfolio)

Revision ID: 0017_folder_snapshots
Revises: 0016_set_code
Create Date: 2026-10-24 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_folder_snapshots"
down_revision: str | Sequence[str] | None = "0016_set_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "folder_snapshots",
        sa.Column("folder_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("total_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estimated_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("invested", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["folders.id"],
            name=op.f("fk_folder_snapshots_folder_id_folders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("folder_id", "day", name=op.f("pk_folder_snapshots")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("folder_snapshots")
