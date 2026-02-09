"""add_evidence_run_id_to_archive_articles

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-02-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("archive_articles", sa.Column("evidence_run_id", sa.String(length=64), nullable=True))
    op.create_index("idx_archive_articles_evidence_run_id", "archive_articles", ["evidence_run_id"])


def downgrade() -> None:
    op.drop_index("idx_archive_articles_evidence_run_id", table_name="archive_articles")
    op.drop_column("archive_articles", "evidence_run_id")

