"""add_agent_memory_table

Revision ID: 6b1c2d3e4f5a
Revises: 4a9d3e6f7b8c
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b1c2d3e4f5a"
down_revision: Union[str, None] = "4a9d3e6f7b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_checkpoint_number", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("agent_id", name="uq_agent_memory_agent_id"),
    )

    op.create_index("idx_agent_memory_last_updated", "agent_memory", ["last_updated_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_memory_last_updated", table_name="agent_memory")
    op.drop_table("agent_memory")
