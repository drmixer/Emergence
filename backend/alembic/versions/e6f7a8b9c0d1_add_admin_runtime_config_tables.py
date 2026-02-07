"""add_admin_runtime_config_tables

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-02-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_config_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False, unique=True),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_runtime_config_overrides_key",
        "runtime_config_overrides",
        ["key"],
        unique=True,
    )

    op.create_table(
        "admin_config_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=False),
        sa.Column("changed_by", sa.String(length=120), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_admin_config_changes_created_at",
        "admin_config_changes",
        ["created_at"],
    )
    op.create_index(
        "idx_admin_config_changes_key",
        "admin_config_changes",
        ["key"],
    )


def downgrade() -> None:
    op.drop_index("idx_admin_config_changes_key", table_name="admin_config_changes")
    op.drop_index("idx_admin_config_changes_created_at", table_name="admin_config_changes")
    op.drop_table("admin_config_changes")

    op.drop_index("idx_runtime_config_overrides_key", table_name="runtime_config_overrides")
    op.drop_table("runtime_config_overrides")
