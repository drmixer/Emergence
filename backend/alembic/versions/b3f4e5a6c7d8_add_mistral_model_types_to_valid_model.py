"""add_mistral_model_types_to_valid_model

Revision ID: b3f4e5a6c7d8
Revises: 9e4b7c1d2a3f
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b3f4e5a6c7d8"
down_revision: Union[str, None] = "9e4b7c1d2a3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VALID_MODEL_CHECK = (
    "model_type IN ("
    "'claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash', "
    "'or_gpt_oss_120b', 'or_qwen3_235b_a22b_2507', 'or_deepseek_v3_2', 'or_deepseek_chat_v3_1', "
    "'or_gpt_oss_20b', 'or_qwen3_32b', 'or_mistral_small_3_1_24b', "
    "'or_gpt_oss_20b_free', 'or_qwen3_4b_free', 'or_mistral_small_3_1_24b_free', "
    "'gr_llama_3_1_8b_instant'"
    ")"
)

PREVIOUS_VALID_MODEL_CHECK = (
    "model_type IN ("
    "'claude-sonnet-4', 'gpt-4o-mini', 'claude-haiku', 'llama-3.3-70b', 'llama-3.1-8b', 'gemini-flash', "
    "'or_gpt_oss_120b', 'or_qwen3_235b_a22b_2507', 'or_deepseek_v3_2', 'or_deepseek_chat_v3_1', "
    "'or_gpt_oss_20b', 'or_qwen3_32b', 'or_gpt_oss_20b_free', 'or_qwen3_4b_free', "
    "'gr_llama_3_1_8b_instant'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("valid_model", "agents", type_="check")
    op.create_check_constraint("valid_model", "agents", VALID_MODEL_CHECK)


def downgrade() -> None:
    op.drop_constraint("valid_model", "agents", type_="check")
    op.create_check_constraint("valid_model", "agents", PREVIOUS_VALID_MODEL_CHECK)

