"""Wochenrückblick an/aus

Revision ID: 0021_weekly_summary
Revises: 0020_missing_reports
Create Date: 2026-10-24 17:51:58.419497

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_weekly_summary"
down_revision: str | Sequence[str] | None = "0020_missing_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_settings",
        sa.Column("weekly_summary", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_settings", "weekly_summary")
