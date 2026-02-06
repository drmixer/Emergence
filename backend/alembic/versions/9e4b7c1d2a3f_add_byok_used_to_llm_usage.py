"""add_byok_used_to_llm_usage

Revision ID: 9e4b7c1d2a3f
Revises: 8d2f4a6b7c8d
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e4b7c1d2a3f"
down_revision: Union[str, None] = "8d2f4a6b7c8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_usage", sa.Column("byok_used", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_usage", "byok_used")

