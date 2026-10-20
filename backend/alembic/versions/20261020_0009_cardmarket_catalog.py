"""Cardmarket-Katalog, Preisführer, Ausgabe je Set, Cardmarket-Produkt je Karte

Revision ID: 0009_cardmarket_catalog
Revises: 0008_price_links
Create Date: 2026-10-21 00:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_cardmarket_catalog"
down_revision: str | Sequence[str] | None = "0008_price_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cm_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("products", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("prices", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expansions", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sets_linked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("catalog_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("guide_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cm_imports")),
    )
    op.create_table(
        "cm_prices",
        sa.Column("id_product", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id_product", name=op.f("pk_cm_prices")),
    )
    op.create_table(
        "cm_products",
        sa.Column("id_product", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("id_expansion", sa.Integer(), nullable=False),
        sa.Column("id_metacard", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("date_added", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id_product", name=op.f("pk_cm_products")),
    )
    op.create_index(
        op.f("ix_cm_products_id_expansion"), "cm_products", ["id_expansion"], unique=False
    )
    op.create_index(
        op.f("ix_cm_products_id_metacard"), "cm_products", ["id_metacard"], unique=False
    )
    op.create_table(
        "cm_expansions",
        sa.Column("id_expansion", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("first_added", sa.Date(), nullable=True),
        sa.Column(
            "twin_ids", sa.ARRAY(sa.Integer()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("label_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["label_by_id"],
            ["users.id"],
            name=op.f("fk_cm_expansions_label_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id_expansion", name=op.f("pk_cm_expansions")),
    )
    op.add_column("card_sets", sa.Column("cardmarket_expansion_id", sa.Integer(), nullable=True))
    op.add_column(
        "card_sets", sa.Column("cardmarket_expansion_source", sa.String(length=16), nullable=True)
    )
    op.add_column("card_sets", sa.Column("cardmarket_expansion_by_id", sa.Uuid(), nullable=True))
    op.add_column(
        "card_sets",
        sa.Column("cardmarket_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_card_sets_cardmarket_expansion_by_id_users"),
        "card_sets",
        "users",
        ["cardmarket_expansion_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("cards", sa.Column("cardmarket_product_id", sa.Integer(), nullable=True))
    op.add_column("cards", sa.Column("cardmarket_product_override", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cards", "cardmarket_product_override")
    op.drop_column("cards", "cardmarket_product_id")
    op.drop_constraint(
        op.f("fk_card_sets_cardmarket_expansion_by_id_users"), "card_sets", type_="foreignkey"
    )
    op.drop_column("card_sets", "cardmarket_checked_at")
    op.drop_column("card_sets", "cardmarket_expansion_by_id")
    op.drop_column("card_sets", "cardmarket_expansion_source")
    op.drop_column("card_sets", "cardmarket_expansion_id")
    op.drop_table("cm_expansions")
    op.drop_index(op.f("ix_cm_products_id_metacard"), table_name="cm_products")
    op.drop_index(op.f("ix_cm_products_id_expansion"), table_name="cm_products")
    op.drop_table("cm_products")
    op.drop_table("cm_prices")
    op.drop_table("cm_imports")
