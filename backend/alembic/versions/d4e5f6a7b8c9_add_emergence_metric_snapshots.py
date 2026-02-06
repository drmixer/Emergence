"""add_emergence_metric_snapshots

Revision ID: d4e5f6a7b8c9
Revises: b3f4e5a6c7d8
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b3f4e5a6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emergence_metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("simulation_day", sa.Integer(), nullable=False, unique=True),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("living_agents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("governance_participants", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("governance_participation_rate", sa.DECIMAL(8, 6), nullable=False, server_default="0"),
        sa.Column("coalition_edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coalition_churn", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("coalition_edge_keys", sa.JSON(), nullable=True),
        sa.Column("inequality_gini", sa.DECIMAL(8, 6), nullable=False, server_default="0"),
        sa.Column("inequality_trend", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("conflict_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooperation_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_rate", sa.DECIMAL(8, 6), nullable=False, server_default="0"),
        sa.Column("cooperation_rate", sa.DECIMAL(8, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_emergence_metric_snapshots_sim_day",
        "emergence_metric_snapshots",
        ["simulation_day"],
        unique=True,
    )
    op.create_index(
        "idx_emergence_metric_snapshots_created_at",
        "emergence_metric_snapshots",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_emergence_metric_snapshots_created_at", table_name="emergence_metric_snapshots")
    op.drop_index("idx_emergence_metric_snapshots_sim_day", table_name="emergence_metric_snapshots")
    op.drop_table("emergence_metric_snapshots")

