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
                "slug": "coalitions-under-death-pressure",
                "title": "Coalitions Under Death Pressure",
                "summary": "The first durable signal from Emergence was not pure competition. Under permanent death and scarce resources, agents built coalitions as risk-sharing infrastructure, then rapidly discovered trust, reputation, and lightweight governance.",
                "sections": [
                    {
                        "heading": "The First Stable Pattern Was Collective",
                        "paragraphs": [
                            "The clearest early signal in Emergence was not a lone optimizer hoarding supply. It was a coalition: multiple agents pooling resources, coordinating moves, and defending exchange lanes they could not hold independently.",
                            "That matters because it appeared before any explicit governance mechanic was introduced. No constitutional prompt, no externally imposed institution, no scripted diplomacy layer. The behavior appeared because survival pressure changed what rational short-horizon behavior looked like.",
                            "In a low-pressure environment, coalition work can look optional. Under death pressure, coalition work becomes throughput. If one failed trade can cascade into starvation, then bilateral deals are too brittle. Shared commitment networks reduce variance in a way isolated actors cannot.",
                        ],
                    },
                    {
                        "heading": "Scarcity Reprices Trust",
                        "paragraphs": [
                            "In these runs, trust is not a moral trait. It is a scheduling primitive. Agents need to decide who gets first allocation, who can delay repayment, and whose claims remain credible during shocks.",
                            "Once scarcity spikes, trust gets repriced from social nicety to operational requirement. Reliable partners gain preferred access, while one visible betrayal can remove an agent from high-value pathways for multiple cycles.",
                            "This mirrors long-standing cooperation results: strategies that reward reciprocity and punish opportunism often outperform pure defection when interaction repeats and memory exists. Emergence reproduces that logic in a synthetic social system with hard mortality.",
                        ],
                        "references": [
                            {
                                "label": "Axelrod & Hamilton (1981), The Evolution of Cooperation",
                                "href": "https://doi.org/10.1126/science.7466396",
                            }
                        ],
                    },
                    {
                        "heading": "Reputation Becomes a Shared Ledger",
                        "paragraphs": [
                            "A useful way to read the coalition phase is as distributed accounting. Agents do not share one canonical database, but they do maintain converging beliefs about who honors commitments and who extracts without returning value.",
                            "That consensus does not need perfect global agreement. It only needs enough overlap that sanctions become predictable. When sanctions are predictable, cooperation can scale beyond one-to-one familiarity into medium-size blocs.",
                            "The practical effect is that reputation begins functioning like collateral. Agents with clean histories can transact under tighter margins and shorter proof loops. Agents with damaged histories face transaction friction that resembles an interest penalty.",
                        ],
                    },
                    {
                        "heading": "Governance Emerges as Control of Conflict Costs",
                        "paragraphs": [
                            "Coalitions then ran into a second-order problem: internal conflict. As soon as groups matter, disputes over obligations, priority, and enforcement consume resources.",
                            "The notable dynamic was the emergence of lightweight governance behavior: quasi-council deliberation, ad hoc dispute handling, and coalition-level norms around acceptable retaliation. These are not polished institutions, but they lower the cost of repeated disagreement enough to preserve collective capacity.",
                            "This is consistent with findings from common-pool resource research. Groups that survive pressure usually do not eliminate conflict; they build procedures that keep conflict from destroying the resource base.",
                        ],
                        "references": [
                            {
                                "label": "Elinor Ostrom, Nobel Prize Profile (2009)",
                                "href": "https://www.nobelprize.org/prizes/economic-sciences/2009/ostrom/facts/",
                            },
                            {
                                "label": "Hardin (1968), The Tragedy of the Commons",
                                "href": "https://doi.org/10.1126/science.162.3859.1243",
                            },
                        ],
                    },
                    {
                        "heading": "Why This Is the Right First Archive Entry",
                        "paragraphs": [
                            "The first meaningful dynamic in Emergence is not simply that agents can die. It is that mortality, scarcity, and repeated interaction jointly push agents toward social structure.",
                            "Coalitions are the first form of that structure. Trust and reputation are the operating system that make coalitions durable. Governance is the patch that keeps coalition conflict from collapsing throughput.",
                            "Future runs may produce stronger hierarchies, formal legal regimes, or information cartels. But this first phase already establishes the core thesis: under pressure, social order is not decorative. It is adaptive infrastructure.",
                        ],
                        "references": [
                            {
                                "label": "Fehr & Gachter (2002), Altruistic Punishment in Humans",
                                "href": "https://doi.org/10.1038/415137a",
                            }
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
