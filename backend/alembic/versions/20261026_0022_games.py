"""Zweites Spiel (One Piece): Spalte ``game`` an Sets, Cardmarket-Tabellen und Wertkurve

Bestand ist komplett Pokémon. Die Wertkurve bekommt eine Spiel-Dimension (``all`` = ganze
Sammlung); der bisherige Verlauf gilt für ``all`` und – weil es bis jetzt nur Pokémon gab –
auch für ``pokemon``.

Revision ID: 0022_games
Revises: 0021_weekly_summary
Create Date: 2026-10-26 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_games"
down_revision: str | Sequence[str] | None = "0021_weekly_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME_TABLES = ("card_sets", "cm_products", "cm_prices", "cm_expansions", "cm_imports")


def _game_column(default: str) -> sa.Column[str]:
    return sa.Column("game", sa.String(16), server_default=sa.text(f"'{default}'"), nullable=False)


def upgrade() -> None:
    """Upgrade schema."""
    for table in GAME_TABLES:
        op.add_column(table, _game_column("pokemon"))
    op.create_index(op.f("ix_card_sets_game"), "card_sets", ["game"])
    op.create_index(op.f("ix_cm_products_game"), "cm_products", ["game"])

    op.add_column("portfolio_snapshots", _game_column("all"))
    op.drop_constraint(op.f("pk_portfolio_snapshots"), "portfolio_snapshots", type_="primary")
    op.create_primary_key(
        op.f("pk_portfolio_snapshots"), "portfolio_snapshots", ["user_id", "day", "game"]
    )
    op.execute(
        """
        INSERT INTO portfolio_snapshots (
            user_id, day, game, total_value, raw_value, graded_value, sealed_value,
            estimated_value, item_count, position_count
        )
        SELECT user_id, day, 'pokemon', total_value, raw_value, graded_value, sealed_value,
               estimated_value, item_count, position_count
        FROM portfolio_snapshots
        WHERE game = 'all'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM portfolio_snapshots WHERE game <> 'all'")
    op.drop_constraint(op.f("pk_portfolio_snapshots"), "portfolio_snapshots", type_="primary")
    op.create_primary_key(op.f("pk_portfolio_snapshots"), "portfolio_snapshots", ["user_id", "day"])
    op.drop_column("portfolio_snapshots", "game")
    op.drop_index(op.f("ix_cm_products_game"), table_name="cm_products")
    op.drop_index(op.f("ix_card_sets_game"), table_name="card_sets")
    for table in GAME_TABLES:
        op.drop_column(table, "game")
