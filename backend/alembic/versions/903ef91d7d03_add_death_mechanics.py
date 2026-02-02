"""add_death_mechanics

Revision ID: 903ef91d7d03
Revises: 5569b9055e40
Create Date: 2026-02-02 01:56:11.055567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '903ef91d7d03'
down_revision: Union[str, None] = '5569b9055e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add starvation_cycles with server_default for existing rows
    op.add_column('agents', sa.Column('starvation_cycles', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('agents', sa.Column('died_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agents', sa.Column('death_cause', sa.String(length=100), nullable=True))
    
    # Update the status check constraint to allow 'dead' status
    op.drop_constraint('valid_status', 'agents', type_='check')
    op.create_check_constraint(
        'valid_status',
        'agents',
        "status IN ('active', 'dormant', 'dead')"
    )


def downgrade() -> None:
    # Restore old status constraint
    op.drop_constraint('valid_status', 'agents', type_='check')
    op.create_check_constraint(
        'valid_status',
        'agents',
        "status IN ('active', 'dormant')"
    )
    
    # Drop the new columns
    op.drop_column('agents', 'death_cause')
    op.drop_column('agents', 'died_at')
    op.drop_column('agents', 'starvation_cycles')

