"""expand run report artifact types for summary and condition comparison

Revision ID: 9c4d1a8f5a21
Revises: 2a2fe6dffda5
Create Date: 2026-02-11 02:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c4d1a8f5a21"
down_revision: Union[str, None] = "2a2fe6dffda5"
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
        "artifact_type IN ('technical_report', 'approachable_report', 'planner_report', 'run_summary', 'condition_comparison')",
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
        "artifact_type IN ('technical_report', 'approachable_report', 'planner_report')",
    )
