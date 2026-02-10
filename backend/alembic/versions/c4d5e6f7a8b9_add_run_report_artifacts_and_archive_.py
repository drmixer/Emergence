"""add_run_report_artifacts_and_archive_article_metadata

Revision ID: c4d5e6f7a8b9
Revises: b9d26c07c3b7
Create Date: 2026-02-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b9d26c07c3b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "archive_articles",
        sa.Column(
            "content_type",
            sa.String(length=32),
            nullable=False,
            server_default="approachable_article",
        ),
    )
    op.add_column(
        "archive_articles",
        sa.Column(
            "status_label",
            sa.String(length=20),
            nullable=False,
            server_default="observational",
        ),
    )
    op.add_column(
        "archive_articles",
        sa.Column(
            "evidence_completeness",
            sa.String(length=20),
            nullable=False,
            server_default="partial",
        ),
    )
    op.add_column(
        "archive_articles",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "archive_articles",
        sa.Column(
            "linked_record_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )

    op.create_check_constraint(
        "valid_archive_article_content_type",
        "archive_articles",
        "content_type IN ('technical_report', 'approachable_article')",
    )
    op.create_check_constraint(
        "valid_archive_article_status_label",
        "archive_articles",
        "status_label IN ('observational', 'replicated')",
    )
    op.create_check_constraint(
        "valid_archive_article_evidence_completeness",
        "archive_articles",
        "evidence_completeness IN ('full', 'partial')",
    )

    op.create_index(
        "idx_archive_articles_content_type",
        "archive_articles",
        ["content_type"],
        unique=False,
    )
    op.create_index(
        "idx_archive_articles_status_label",
        "archive_articles",
        ["status_label"],
        unique=False,
    )

    op.create_table(
        "run_report_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("artifact_format", sa.String(length=16), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("template_version", sa.String(length=64), nullable=True),
        sa.Column("generator_version", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "artifact_type IN ('technical_report', 'approachable_report', 'planner_report')",
            name="valid_run_report_artifact_type",
        ),
        sa.CheckConstraint(
            "artifact_format IN ('json', 'markdown')",
            name="valid_run_report_artifact_format",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="valid_run_report_artifact_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "artifact_type",
            "artifact_format",
            name="uq_run_report_artifacts_key",
        ),
    )
    op.create_index(
        "idx_run_report_artifacts_run_id",
        "run_report_artifacts",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "idx_run_report_artifacts_status",
        "run_report_artifacts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_run_report_artifacts_type",
        "run_report_artifacts",
        ["artifact_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_run_report_artifacts_type", table_name="run_report_artifacts")
    op.drop_index("idx_run_report_artifacts_status", table_name="run_report_artifacts")
    op.drop_index("idx_run_report_artifacts_run_id", table_name="run_report_artifacts")
    op.drop_table("run_report_artifacts")

    op.drop_index("idx_archive_articles_status_label", table_name="archive_articles")
    op.drop_index("idx_archive_articles_content_type", table_name="archive_articles")
    op.drop_constraint(
        "valid_archive_article_evidence_completeness",
        "archive_articles",
        type_="check",
    )
    op.drop_constraint(
        "valid_archive_article_status_label",
        "archive_articles",
        type_="check",
    )
    op.drop_constraint(
        "valid_archive_article_content_type",
        "archive_articles",
        type_="check",
    )

    op.drop_column("archive_articles", "linked_record_ids")
    op.drop_column("archive_articles", "tags")
    op.drop_column("archive_articles", "evidence_completeness")
    op.drop_column("archive_articles", "status_label")
    op.drop_column("archive_articles", "content_type")
