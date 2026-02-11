"""add simulation run season tables

Revision ID: f85ae70375e2
Revises: c4d5e6f7a8b9
Create Date: 2026-02-10 22:16:37.166853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f85ae70375e2"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("run_mode", sa.String(length=16), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("condition_name", sa.String(length=120), nullable=True),
        sa.Column("hypothesis_id", sa.String(length=120), nullable=True),
        sa.Column("season_id", sa.String(length=64), nullable=True),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("parent_run_id", sa.String(length=64), nullable=True),
        sa.Column("transfer_policy_version", sa.String(length=64), nullable=True),
        sa.Column("carryover_agent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fresh_agent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("protocol_deviation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deviation_reason", sa.Text(), nullable=True),
        sa.Column("start_reason", sa.Text(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("run_mode IN ('test', 'real')", name="ck_simulation_runs_run_mode"),
        sa.CheckConstraint(
            "(season_id IS NULL) OR (season_number IS NOT NULL AND season_number >= 1)",
            name="ck_simulation_runs_season_number_when_season_id",
        ),
        sa.CheckConstraint(
            "carryover_agent_count >= 0",
            name="ck_simulation_runs_carryover_agent_count_nonnegative",
        ),
        sa.CheckConstraint(
            "fresh_agent_count >= 0",
            name="ck_simulation_runs_fresh_agent_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(["parent_run_id"], ["simulation_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_simulation_runs_run_id"),
    )
    op.create_index("idx_simulation_runs_season_id", "simulation_runs", ["season_id"], unique=False)
    op.create_index("idx_simulation_runs_season_number", "simulation_runs", ["season_number"], unique=False)

    op.create_table(
        "season_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("snapshot_type <> ''", name="ck_season_snapshots_snapshot_type_nonempty"),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_season_snapshots_run_id", "season_snapshots", ["run_id"], unique=False)
    op.create_index(
        "idx_season_snapshots_run_id_snapshot_type",
        "season_snapshots",
        ["run_id", "snapshot_type"],
        unique=False,
    )

    op.create_table(
        "agent_lineage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.String(length=64), nullable=False),
        sa.Column("parent_agent_number", sa.Integer(), nullable=True),
        sa.Column("child_agent_number", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "parent_agent_number IS NULL OR parent_agent_number >= 1",
            name="ck_agent_lineage_parent_agent_number_positive",
        ),
        sa.CheckConstraint(
            "child_agent_number >= 1",
            name="ck_agent_lineage_child_agent_number_positive",
        ),
        sa.CheckConstraint(
            "origin IN ('carryover', 'fresh')",
            name="ck_agent_lineage_origin",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "child_agent_number", name="uq_agent_lineage_season_child"),
    )
    op.create_index(
        "idx_agent_lineage_season_id_parent_agent_number",
        "agent_lineage",
        ["season_id", "parent_agent_number"],
        unique=False,
    )
    op.create_index(
        "idx_agent_lineage_season_id_child_agent_number",
        "agent_lineage",
        ["season_id", "child_agent_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_agent_lineage_season_id_child_agent_number",
        table_name="agent_lineage",
    )
    op.drop_index(
        "idx_agent_lineage_season_id_parent_agent_number",
        table_name="agent_lineage",
    )
    op.drop_table("agent_lineage")

    op.drop_index("idx_season_snapshots_run_id_snapshot_type", table_name="season_snapshots")
    op.drop_index("idx_season_snapshots_run_id", table_name="season_snapshots")
    op.drop_table("season_snapshots")

    op.drop_index("idx_simulation_runs_season_number", table_name="simulation_runs")
    op.drop_index("idx_simulation_runs_season_id", table_name="simulation_runs")
    op.drop_table("simulation_runs")
