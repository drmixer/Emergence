"""add mirror control run link to simulation run metadata

Revision ID: 3b7f1c2d9e4a
Revises: 9c4d1a8f5a21
Create Date: 2026-02-11 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3b7f1c2d9e4a"
down_revision: Union[str, None] = "9c4d1a8f5a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulation_runs",
        sa.Column("mirror_control_run_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_simulation_runs_mirror_control_run_id",
        "simulation_runs",
        "simulation_runs",
        ["mirror_control_run_id"],
        ["run_id"],
    )
    op.create_index(
        "idx_simulation_runs_mirror_control_run_id",
        "simulation_runs",
        ["mirror_control_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_simulation_runs_mirror_control_run_id", table_name="simulation_runs")
    op.drop_constraint(
        "fk_simulation_runs_mirror_control_run_id",
        "simulation_runs",
        type_="foreignkey",
    )
    op.drop_column("simulation_runs", "mirror_control_run_id")
