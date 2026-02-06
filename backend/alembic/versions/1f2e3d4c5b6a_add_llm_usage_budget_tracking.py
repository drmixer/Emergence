"""add_llm_usage_budget_tracking

Revision ID: 1f2e3d4c5b6a
Revises: c91c8f9e3d2a
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, None] = "c91c8f9e3d2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_key", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_type", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.DECIMAL(12, 6), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_llm_usage_day", "llm_usage", ["day_key"])
    op.create_index("idx_llm_usage_day_provider", "llm_usage", ["day_key", "provider"])
    op.create_index("idx_llm_usage_created", "llm_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_llm_usage_created", table_name="llm_usage")
    op.drop_index("idx_llm_usage_day_provider", table_name="llm_usage")
    op.drop_index("idx_llm_usage_day", table_name="llm_usage")
    op.drop_table("llm_usage")

