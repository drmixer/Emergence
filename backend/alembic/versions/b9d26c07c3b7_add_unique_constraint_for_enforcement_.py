"""add unique constraint for enforcement votes

Revision ID: b9d26c07c3b7
Revises: 7842b6f364dc
Create Date: 2026-02-10 04:05:39.615585

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b9d26c07c3b7'
down_revision: Union[str, None] = '7842b6f364dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the earliest vote row per (enforcement_id, agent_id) before enforcing uniqueness.
    op.execute(
        """
        DELETE FROM enforcement_votes ev
        USING enforcement_votes dup
        WHERE ev.id > dup.id
          AND ev.enforcement_id = dup.enforcement_id
          AND ev.agent_id = dup.agent_id
        """
    )

    op.create_unique_constraint(
        "uq_enforcement_votes_enforcement_agent",
        "enforcement_votes",
        ["enforcement_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_enforcement_votes_enforcement_agent",
        "enforcement_votes",
        type_="unique",
    )
