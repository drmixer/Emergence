"""add_missing_constraints_and_indexes

Revision ID: 7c2a8f3b1d9e
Revises: add_enforcement_mechanics
Create Date: 2026-02-03

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c2a8f3b1d9e"
down_revision: Union[str, None] = "add_enforcement_mechanics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Uniqueness constraints
    try:
        op.create_unique_constraint(
            "uq_agent_inventory_agent_resource",
            "agent_inventory",
            ["agent_id", "resource_type"],
        )
    except Exception:
        pass

    try:
        op.create_unique_constraint(
            "uq_votes_proposal_agent",
            "votes",
            ["proposal_id", "agent_id"],
        )
    except Exception:
        pass

    # Helpful indexes
    for name, table, cols in [
        ("idx_agents_status", "agents", ["status"]),
        ("idx_agents_tier", "agents", ["tier"]),
        ("idx_messages_created", "messages", ["created_at"]),
        ("idx_events_created", "events", ["created_at"]),
    ]:
        try:
            op.create_index(name, table, cols)
        except Exception:
            pass


def downgrade() -> None:
    for name, table in [
        ("idx_events_created", "events"),
        ("idx_messages_created", "messages"),
        ("idx_agents_tier", "agents"),
        ("idx_agents_status", "agents"),
    ]:
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass

    for name, table in [
        ("uq_votes_proposal_agent", "votes"),
        ("uq_agent_inventory_agent_resource", "agent_inventory"),
    ]:
        try:
            op.drop_constraint(name, table, type_="unique")
        except Exception:
            pass

