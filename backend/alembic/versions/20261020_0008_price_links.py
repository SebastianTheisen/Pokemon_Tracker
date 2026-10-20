"""Korrigierte Cardmarket-Seiten je Karte, zuletzt geöffnete Karte zum Preisholen

Revision ID: 0008_price_links
Revises: 0007_language_factors
Create Date: 2026-10-20 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_price_links"
down_revision: str | Sequence[str] | None = "0007_language_factors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "card_price_links",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("cardmarket_url", sa.String(length=500), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name=op.f("fk_card_price_links_card_id_cards"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_card_price_links_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("card_id", name=op.f("pk_card_price_links")),
    )
    op.add_column("user_settings", sa.Column("price_target_card_id", sa.Uuid(), nullable=True))
    op.add_column(
        "user_settings", sa.Column("price_target_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_user_settings_price_target_card_id_cards"),
        "user_settings",
        "cards",
        ["price_target_card_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_user_settings_price_target_card_id_cards"), "user_settings", type_="foreignkey"
    )
    op.drop_column("user_settings", "price_target_at")
    op.drop_column("user_settings", "price_target_card_id")
    op.drop_table("card_price_links")
