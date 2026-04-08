"""add social post drafts table

Revision ID: 4e8f7a6b5c4d
Revises: 3b7f1c2d9e4a
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4e8f7a6b5c4d"
down_revision: Union[str, None] = "3b7f1c2d9e4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_post_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="x"),
        sa.Column("draft_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_review"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=255), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("run_mode", sa.String(length=16), nullable=True),
        sa.Column("source_service", sa.String(length=64), nullable=True),
        sa.Column("source_event_type", sa.String(length=64), nullable=True),
        sa.Column("source_record_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("posted_url", sa.String(length=500), nullable=True),
        sa.Column("external_post_id", sa.String(length=128), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("platform IN ('x')", name="valid_social_post_draft_platform"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'posted', 'dismissed')",
            name="valid_social_post_draft_status",
        ),
        sa.CheckConstraint(
            "(run_mode IS NULL) OR (run_mode IN ('test', 'real'))",
            name="valid_social_post_draft_run_mode",
        ),
        sa.CheckConstraint("priority >= 1 AND priority <= 10", name="valid_social_post_draft_priority"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_social_post_drafts_run_id", "social_post_drafts", ["run_id"], unique=False)
    op.create_index("idx_social_post_drafts_dedupe_key", "social_post_drafts", ["dedupe_key"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_social_post_drafts_dedupe_key", table_name="social_post_drafts")
    op.drop_index("idx_social_post_drafts_run_id", table_name="social_post_drafts")
    op.drop_table("social_post_drafts")
