"""add_agent_checkpoint_intent_fields

Revision ID: 4a9d3e6f7b8c
Revises: 1f2e3d4c5b6a
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a9d3e6f7b8c"
down_revision: Union[str, None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("current_intent", sa.JSON(), nullable=True))
    op.add_column("agents", sa.Column("intent_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("next_checkpoint_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "next_checkpoint_at")
    op.drop_column("agents", "last_checkpoint_at")
    op.drop_column("agents", "intent_expires_at")
    op.drop_column("agents", "current_intent")

