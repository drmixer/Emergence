"""add_kpi_events_and_daily_rollups

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-02-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day_key", sa.Date(), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("visitor_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(length=64), nullable=True),
        sa.Column("target", sa.String(length=64), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=255), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("event_name <> ''", name="ck_kpi_events_event_name_nonempty"),
        sa.CheckConstraint("visitor_id <> ''", name="ck_kpi_events_visitor_nonempty"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_kpi_events_day_key_event_name", "kpi_events", ["day_key", "event_name"], unique=False)
    op.create_index("idx_kpi_events_day_key_visitor", "kpi_events", ["day_key", "visitor_id"], unique=False)
    op.create_index("idx_kpi_events_run_id_day_key", "kpi_events", ["run_id", "day_key"], unique=False)

    op.create_table(
        "kpi_daily_rollups",
        sa.Column("day_key", sa.Date(), nullable=False),
        sa.Column("landing_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("landing_view_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("landing_run_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("landing_run_click_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_detail_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_detail_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_start_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_completions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_completion_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_actions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_action_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_click_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shared_link_opens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shared_link_open_visitors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("landing_to_run_ctr", sa.DECIMAL(precision=8, scale=6), nullable=False, server_default="0"),
        sa.Column("run_to_replay_start_rate", sa.DECIMAL(precision=8, scale=6), nullable=False, server_default="0"),
        sa.Column("replay_completion_rate", sa.DECIMAL(precision=8, scale=6), nullable=False, server_default="0"),
        sa.Column("share_action_rate", sa.DECIMAL(precision=8, scale=6), nullable=False, server_default="0"),
        sa.Column("shared_link_ctr", sa.DECIMAL(precision=8, scale=6), nullable=False, server_default="0"),
        sa.Column("d1_cohort_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d1_returning_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d1_retention_rate", sa.DECIMAL(precision=8, scale=6), nullable=True),
        sa.Column("d7_cohort_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d7_returning_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("d7_retention_rate", sa.DECIMAL(precision=8, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("day_key"),
    )


def downgrade() -> None:
    op.drop_table("kpi_daily_rollups")
    op.drop_index("idx_kpi_events_run_id_day_key", table_name="kpi_events")
    op.drop_index("idx_kpi_events_day_key_visitor", table_name="kpi_events")
    op.drop_index("idx_kpi_events_day_key_event_name", table_name="kpi_events")
    op.drop_table("kpi_events")
