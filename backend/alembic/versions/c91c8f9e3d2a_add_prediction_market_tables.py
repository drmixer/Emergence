"""add_prediction_market_tables

Revision ID: c91c8f9e3d2a
Revises: 7c2a8f3b1d9e
Create Date: 2026-02-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c91c8f9e3d2a"
down_revision: Union[str, None] = "7c2a8f3b1d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("market_type", sa.String(length=30), nullable=False),
        sa.Column("related_proposal_id", sa.Integer(), sa.ForeignKey("proposals.id"), nullable=True),
        sa.Column("related_agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("total_yes_amount", sa.DECIMAL(15, 2), nullable=False, server_default="0"),
        sa.Column("total_no_amount", sa.DECIMAL(15, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "market_type IN ('proposal_pass', 'agent_dormant', 'resource_goal', 'law_count', 'custom')",
            name="valid_market_type",
        ),
        sa.CheckConstraint("status IN ('open', 'closed', 'resolved')", name="valid_market_status"),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('yes', 'no')",
            name="valid_market_outcome",
        ),
    )

    op.create_table(
        "prediction_bets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "market_id",
            sa.Integer(),
            sa.ForeignKey("prediction_markets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("prediction", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("payout", sa.DECIMAL(15, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("prediction IN ('yes', 'no')", name="valid_bet_prediction"),
        sa.CheckConstraint("amount > 0", name="positive_bet_amount"),
    )

    op.create_table(
        "user_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("balance", sa.DECIMAL(15, 2), nullable=False, server_default="100"),
        sa.Column("total_wagered", sa.DECIMAL(15, 2), nullable=False, server_default="0"),
        sa.Column("total_won", sa.DECIMAL(15, 2), nullable=False, server_default="0"),
        sa.Column("total_lost", sa.DECIMAL(15, 2), nullable=False, server_default="0"),
        sa.Column("bets_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bets_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bets_lost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("balance >= 0", name="non_negative_balance"),
    )

    op.create_index("idx_prediction_markets_status", "prediction_markets", ["status"])
    op.create_index("idx_prediction_markets_created", "prediction_markets", ["created_at"])
    op.create_index("idx_prediction_bets_market", "prediction_bets", ["market_id"])
    op.create_index("idx_prediction_bets_user", "prediction_bets", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_prediction_bets_user", table_name="prediction_bets")
    op.drop_index("idx_prediction_bets_market", table_name="prediction_bets")
    op.drop_index("idx_prediction_markets_created", table_name="prediction_markets")
    op.drop_index("idx_prediction_markets_status", table_name="prediction_markets")

    op.drop_table("user_points")
    op.drop_table("prediction_bets")
    op.drop_table("prediction_markets")

