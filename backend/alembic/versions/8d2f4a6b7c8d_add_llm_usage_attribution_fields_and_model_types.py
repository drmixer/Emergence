"""add_llm_usage_attribution_fields_and_model_types

Revision ID: 8d2f4a6b7c8d
Revises: 6b1c2d3e4f5a
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d2f4a6b7c8d"
down_revision: Union[str, None] = "6b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VALID_MODEL_CHECK = (
    "model_type IN ("
    "'claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash', "
    "'or_gpt_oss_120b', 'or_qwen3_235b_a22b_2507', 'or_deepseek_v3_2', 'or_deepseek_chat_v3_1', "
    "'or_gpt_oss_20b', 'or_qwen3_32b', 'or_gpt_oss_20b_free', 'or_qwen3_4b_free', "
    "'gr_llama_3_1_8b_instant'"
    ")"
)

LEGACY_VALID_MODEL_CHECK = (
    "model_type IN ('claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash')"
)


def upgrade() -> None:
    op.add_column("llm_usage", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("llm_usage", sa.Column("agent_id", sa.Integer(), nullable=True))
    op.add_column("llm_usage", sa.Column("checkpoint_number", sa.Integer(), nullable=True))
    op.add_column("llm_usage", sa.Column("resolved_model_name", sa.String(length=255), nullable=True))
    op.add_column("llm_usage", sa.Column("latency_ms", sa.Integer(), nullable=True))

    op.execute("UPDATE llm_usage SET resolved_model_name = model_name WHERE resolved_model_name IS NULL")

    op.create_index("idx_llm_usage_run_id", "llm_usage", ["run_id"])
    op.create_index("idx_llm_usage_agent_checkpoint", "llm_usage", ["agent_id", "checkpoint_number"])
    op.create_index("idx_llm_usage_resolved_model", "llm_usage", ["resolved_model_name"])

    op.drop_constraint("valid_model", "agents", type_="check")
    op.create_check_constraint("valid_model", "agents", VALID_MODEL_CHECK)


def downgrade() -> None:
    op.drop_constraint("valid_model", "agents", type_="check")
    op.create_check_constraint("valid_model", "agents", LEGACY_VALID_MODEL_CHECK)

    op.drop_index("idx_llm_usage_resolved_model", table_name="llm_usage")
    op.drop_index("idx_llm_usage_agent_checkpoint", table_name="llm_usage")
    op.drop_index("idx_llm_usage_run_id", table_name="llm_usage")

    op.drop_column("llm_usage", "latency_ms")
    op.drop_column("llm_usage", "resolved_model_name")
    op.drop_column("llm_usage", "checkpoint_number")
    op.drop_column("llm_usage", "agent_id")
    op.drop_column("llm_usage", "run_id")
