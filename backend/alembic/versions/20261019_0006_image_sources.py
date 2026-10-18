"""Bildquellen: Herkunft des Bildes, offizielle Datenbanken, Prüfprotokoll

Revision ID: 0006_image_sources
Revises: 0005_image_language
Create Date: 2026-10-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_image_sources"
down_revision: str | Sequence[str] | None = "0005_image_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cards", sa.Column("image_source", sa.String(length=32), nullable=True))
    # Bisherige Ersatzbilder (Migration 0005) als solche kennzeichnen.
    op.execute("UPDATE cards SET image_source = 'fallback' WHERE image_language IS NOT NULL")
    op.create_table(
        "official_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("official_id", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("set_code", sa.String(length=32), nullable=True),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("card_id", sa.Uuid(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["cards.id"],
            name=op.f("fk_official_cards_card_id_cards"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_cards")),
        sa.UniqueConstraint("source", "official_id", name=op.f("uq_official_cards_source")),
    )
    op.create_index("ix_official_cards_card_id", "official_cards", ["card_id"], unique=False)
    op.create_table(
        "image_probes",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name=op.f("fk_image_probes_card_id_cards"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("card_id", "source", name=op.f("pk_image_probes")),
    )
    op.create_table(
        "image_import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image_import_runs")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("image_import_runs")
    op.drop_table("image_probes")
    op.drop_index("ix_official_cards_card_id", table_name="official_cards")
    op.drop_table("official_cards")
    op.drop_column("cards", "image_source")
