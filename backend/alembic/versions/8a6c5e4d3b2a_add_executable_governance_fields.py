"""add executable governance fields

Revision ID: 8a6c5e4d3b2a
Revises: 7d4e9c2b1a6f
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a6c5e4d3b2a"
down_revision: Union[str, None] = "7d4e9c2b1a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("governance_class", sa.String(length=30), nullable=True))
    op.add_column("proposals", sa.Column("runtime_effect", sa.JSON(), nullable=True))
    op.add_column("laws", sa.Column("law_class", sa.String(length=30), nullable=True))
    op.add_column("laws", sa.Column("runtime_effect", sa.JSON(), nullable=True))

    op.drop_constraint("valid_proposal_type", "proposals", type_="check")
    op.create_check_constraint(
        "valid_proposal_type",
        "proposals",
        "proposal_type IN ('law', 'allocation', 'rule', 'infrastructure', 'constitutional', 'other', 'resolution', 'standing_law', 'amendment', 'emergency_action')",
    )
    op.create_check_constraint(
        "valid_governance_class",
        "proposals",
        "(governance_class IS NULL) OR governance_class IN ('resolution', 'standing_law', 'allocation', 'amendment', 'emergency_action', 'advisory_law')",
    )
    op.create_check_constraint(
        "valid_law_class",
        "laws",
        "(law_class IS NULL) OR law_class IN ('standing_law', 'advisory_law', 'amendment', 'emergency_action')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_law_class", "laws", type_="check")
    op.drop_constraint("valid_governance_class", "proposals", type_="check")
    op.drop_constraint("valid_proposal_type", "proposals", type_="check")
    op.create_check_constraint(
        "valid_proposal_type",
        "proposals",
        "proposal_type IN ('law', 'allocation', 'rule', 'infrastructure', 'constitutional', 'other')",
    )
    op.drop_column("laws", "runtime_effect")
    op.drop_column("laws", "law_class")
    op.drop_column("proposals", "runtime_effect")
    op.drop_column("proposals", "governance_class")
