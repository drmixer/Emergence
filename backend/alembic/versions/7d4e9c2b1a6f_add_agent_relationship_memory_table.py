"""add agent relationship memory table

Revision ID: 7d4e9c2b1a6f
Revises: 4e8f7a6b5c4d
Create Date: 2026-04-17 03:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d4e9c2b1a6f"
down_revision: Union[str, None] = "4e8f7a6b5c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_relationship_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("other_agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aid_requests_made_to_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aid_requests_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aid_refusals_made_to_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aid_refusals_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aid_given_to_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aid_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accusations_made_against_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accusations_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_contests_made_against_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_contests_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_supports_for_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_supports_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_oppositions_against_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposal_oppositions_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trade_sent_to_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trade_received_from_other_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_positive_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_negative_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("agent_id <> other_agent_id", name="ck_agent_relationship_memory_not_self"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "other_agent_id", name="uq_agent_relationship_memory_pair"),
    )
    op.create_index(
        "idx_agent_relationship_memory_agent_last_interaction",
        "agent_relationship_memory",
        ["agent_id", "last_interaction_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_agent_relationship_memory_agent_last_interaction",
        table_name="agent_relationship_memory",
    )
    op.drop_table("agent_relationship_memory")
