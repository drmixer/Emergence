"""Add enforcement mechanics (Phase 3: Teeth)

Revision ID: add_enforcement_mechanics
Revises: add_death_mechanics
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_enforcement_mechanics'
down_revision: Union[str, None] = '903ef91d7d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enforcement tracking fields to agents
    op.add_column('agents', sa.Column('sanctioned_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agents', sa.Column('exiled', sa.Boolean(), nullable=False, server_default='false'))
    
    # Create enforcements table
    op.create_table(
        'enforcements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('initiator_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('target_agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('enforcement_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('law_id', sa.Integer(), sa.ForeignKey('laws.id'), nullable=False),
        sa.Column('violation_description', sa.Text(), nullable=False),
        sa.Column('sanction_cycles', sa.Integer(), nullable=True),
        sa.Column('seizure_resource', sa.String(20), nullable=True),
        sa.Column('seizure_amount', sa.DECIMAL(15, 2), nullable=True),
        sa.Column('support_votes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('oppose_votes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('votes_required', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('voting_closes_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("enforcement_type IN ('sanction', 'seizure', 'exile')", name='valid_enforcement_type'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'executed', 'contested')", name='valid_enforcement_status'),
    )
    
    # Create enforcement_votes table
    op.create_table(
        'enforcement_votes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('enforcement_id', sa.Integer(), sa.ForeignKey('enforcements.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('vote', sa.String(10), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("vote IN ('support', 'oppose')", name='valid_enforcement_vote'),
    )
    
    # Update transaction types constraint to include seizure
    # Note: This may fail if the constraint already includes these types
    # In that case, skip this step
    try:
        op.drop_constraint('valid_tx_type', 'transactions', type_='check')
        op.create_check_constraint(
            'valid_tx_type',
            'transactions',
            "transaction_type IN ('work_production', 'trade', 'allocation', 'consumption', 'building', 'awakening', 'initial_distribution', 'survival_consumption', 'dormant_survival', 'action_cost', 'seizure')"
        )
    except:
        pass  # Constraint may already be updated


def downgrade() -> None:
    # Drop enforcement tables
    op.drop_table('enforcement_votes')
    op.drop_table('enforcements')
    
    # Remove agent enforcement fields
    op.drop_column('agents', 'exiled')
    op.drop_column('agents', 'sanctioned_until')
