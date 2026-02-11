"""add simulation run epoch and class metadata

Revision ID: 2a2fe6dffda5
Revises: f85ae70375e2
Create Date: 2026-02-10 22:38:28.186323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2a2fe6dffda5"
down_revision: Union[str, None] = "f85ae70375e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulation_runs",
        sa.Column("epoch_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column(
            "run_class",
            sa.String(length=32),
            nullable=False,
            server_default="standard_72h",
        ),
    )
    op.create_index(
        "idx_simulation_runs_epoch_id",
        "simulation_runs",
        ["epoch_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_simulation_runs_run_class",
        "simulation_runs",
        "run_class IN ('standard_72h', 'deep_96h', 'special_exploratory')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_simulation_runs_run_class",
        "simulation_runs",
        type_="check",
    )
    op.drop_index("idx_simulation_runs_epoch_id", table_name="simulation_runs")
    op.drop_column("simulation_runs", "run_class")
    op.drop_column("simulation_runs", "epoch_id")
