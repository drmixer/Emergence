"""add_prediction_resolution_receipts

Revision ID: 5f6a7b8c9d0e
Revises: 3f2d4a6b8c90
Create Date: 2026-05-25

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5f6a7b8c9d0e"
down_revision: Union[str, None] = "3f2d4a6b8c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prediction_markets", sa.Column("resolution_summary", sa.Text(), nullable=True)
    )
    op.add_column(
        "prediction_markets",
        sa.Column("resolution_event_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prediction_markets", "resolution_event_id")
    op.drop_column("prediction_markets", "resolution_summary")
