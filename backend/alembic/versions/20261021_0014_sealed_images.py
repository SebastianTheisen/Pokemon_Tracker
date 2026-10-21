"""Bilder für versiegelte Produkte (TCGplayer-Katalog über tcgcsv.com)

Revision ID: 0014_sealed_images
Revises: 0013_psa_certs
Create Date: 2026-10-21 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_sealed_images"
down_revision: str | Sequence[str] | None = "0013_psa_certs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cm_imports", sa.Column("sealed_images", sa.Integer(), nullable=True))
    op.add_column("cm_products", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("cm_products", sa.Column("tcgplayer_product_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cm_products", "tcgplayer_product_id")
    op.drop_column("cm_products", "image_url")
    op.drop_column("cm_imports", "sealed_images")
