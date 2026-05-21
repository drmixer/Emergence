"""add viewer brief report artifact

Revision ID: 3f2d4a6b8c90
Revises: 8a6c5e4d3b2a
Create Date: 2026-05-20 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3f2d4a6b8c90"
down_revision: Union[str, None] = "8a6c5e4d3b2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "valid_run_report_artifact_type",
        "run_report_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "valid_run_report_artifact_type",
        "run_report_artifacts",
        "artifact_type IN ('technical_report', 'approachable_report', 'viewer_brief', 'planner_report', 'run_summary', 'condition_comparison')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "valid_run_report_artifact_type",
        "run_report_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "valid_run_report_artifact_type",
        "run_report_artifacts",
        "artifact_type IN ('technical_report', 'approachable_report', 'planner_report', 'run_summary', 'condition_comparison')",
    )
