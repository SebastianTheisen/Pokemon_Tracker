"""Versiegelte Produkte: Cardmarket-Kategorie im Katalog, Verknüpfung je Produkt

Revision ID: 0011_sealed_prices
Revises: 0010_ebay_fetches
Create Date: 2026-10-21 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_sealed_prices"
down_revision: str | Sequence[str] | None = "0010_ebay_fetches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cm_products", sa.Column("id_category", sa.Integer(), nullable=True))
    op.add_column("cm_products", sa.Column("category_name", sa.String(length=60), nullable=True))
    op.add_column("products", sa.Column("cardmarket_product_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_products_cardmarket_product_id"),
        "products",
        ["cardmarket_product_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_products_cardmarket_product_id"), table_name="products")
    op.drop_column("products", "cardmarket_product_id")
    op.drop_column("cm_products", "category_name")
    op.drop_column("cm_products", "id_category")
