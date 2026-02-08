"""add_archive_articles_table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-02-08

"""

from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=160), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft', 'published')", name="valid_archive_article_status"),
    )
    op.create_index("idx_archive_articles_status", "archive_articles", ["status"])
    op.create_index("idx_archive_articles_published_at", "archive_articles", ["published_at"])

    archive_articles = sa.table(
        "archive_articles",
        sa.column("slug", sa.String()),
        sa.column("title", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("sections", sa.JSON()),
        sa.column("status", sa.String()),
        sa.column("published_at", sa.Date()),
        sa.column("created_by", sa.String()),
        sa.column("updated_by", sa.String()),
    )

    op.bulk_insert(
        archive_articles,
        [
            {
                "slug": "before-the-first-full-run",
                "title": "Before the First Full Run",
                "summary": "Emergence is readying a controlled experiment in AI society formation. This first archive note documents the protocol, constraints, and evidence standards we will use before claiming any empirical findings.",
                "sections": [
                    {
                        "heading": "Why This Entry Exists",
                        "paragraphs": [
                            "No full production-valid run has completed yet. Publishing that fact explicitly is important because this archive is meant to be evidence-driven, not narrative-first.",
                            "This post is therefore a baseline document: what Emergence is, what we are actually testing, and how claims will be validated once real runs complete.",
                            "When empirical posts start, each one will be anchored to specific run IDs, timestamps, and metrics so readers can audit the story against the underlying trace.",
                        ],
                    },
                    {
                        "heading": "What the Experiment Is Testing",
                        "paragraphs": [
                            "Emergence is a social systems experiment: autonomous agents share an environment with resource scarcity, persistent memory, proposal and voting mechanics, and permanent death pressure.",
                            "The central question is not whether one model can optimize a toy task. It is whether durable social structures form under pressure: cooperation networks, trust regimes, governance norms, conflict cycles, and collapse or recovery patterns.",
                            "We are studying adaptive order formation, not benchmark theater.",
                        ],
                        "references": [
                            {
                                "label": "Project Repository",
                                "href": "https://github.com/drmixer/Emergence",
                            }
                        ],
                    },
                    {
                        "heading": "What Counts as a Real Run",
                        "paragraphs": [
                            "A run is considered valid when it has a stable run ID, continuous progression over meaningful simulation time, complete telemetry capture, and no ad hoc manual steering during active epochs beyond declared guardrails.",
                            "Interrupted tests, local smoke checks, and partial burn-ins are useful for engineering, but they are not treated as empirical evidence about emergent social dynamics.",
                            "This distinction protects the archive from overinterpreting noisy setup behavior.",
                        ],
                    },
                    {
                        "heading": "How Findings Will Be Reported",
                        "paragraphs": [
                            "Each future article will separate observations from interpretation. Observation means concrete events and metrics. Interpretation means proposed mechanisms that could explain those events.",
                            "Claims will be graded by confidence and updated if later runs contradict earlier patterns. That is expected in a young complex system.",
                            "Where possible, posts will link to the relevant dashboard views, metrics snapshots, and source traces.",
                        ],
                        "references": [
                            {
                                "label": "Project README",
                                "href": "https://github.com/drmixer/Emergence/blob/main/README.md",
                            },
                        ],
                    },
                    {
                        "heading": "What Comes Next",
                        "paragraphs": [
                            "The next archive entry should be the first run-backed report, not a prewritten thesis. If coalitions, governance behavior, or trust cascades appear, they will be documented with evidence.",
                            "If the first runs are chaotic, inconclusive, or fail in unexpected ways, that will be published too.",
                            "The standard is simple: no claims beyond the data.",
                        ],
                    },
                ],
                "status": "published",
                "published_at": date(2026, 2, 8),
                "created_by": "seed",
                "updated_by": "seed",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_archive_articles_published_at", table_name="archive_articles")
    op.drop_index("idx_archive_articles_status", table_name="archive_articles")
    op.drop_table("archive_articles")
