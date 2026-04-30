"""
Proposals API Router
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, case
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.database import get_db
from app.models.models import Proposal, Vote, Agent
from app.services.duplicate_waves import collect_duplicate_waves
from app.services.executable_governance import governance_payload_for_proposal
from app.services.live_run_scope import apply_live_run_window, get_live_run_window

router = APIRouter()


class AgentInfo(BaseModel):
    id: int
    agent_number: int
    display_name: Optional[str]
    tier: int
    personality_type: str


class VoteResponse(BaseModel):
    id: int
    vote: str
    reasoning: Optional[str]
    created_at: Optional[str]
    agent: AgentInfo


class ProposalResponse(BaseModel):
    id: int
    title: str
    description: str
    proposal_type: str
    governance_class: Optional[str] = None
    runtime_effect: dict[str, Any] = {}
    governance: dict[str, Any] = {}
    status: str
    created_at: Optional[str]
    voting_closes_at: Optional[str]
    resolved_at: Optional[str]
    author: AgentInfo
    votes_for: int
    votes_against: int
    votes_abstain: int


class ProposalDetailResponse(ProposalResponse):
    votes: List[VoteResponse]


def _agent_info(agent: Agent) -> AgentInfo:
    return AgentInfo(
        id=agent.id,
        agent_number=agent.agent_number,
        display_name=agent.display_name,
        tier=agent.tier,
        personality_type=agent.personality_type,
    )


@router.get("", response_model=List[ProposalResponse])
def list_proposals(
    status: Optional[str] = Query(None, description="active|passed|failed|expired"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
):
    """List proposals with optional status filter."""
    yes_count = func.sum(case((Vote.vote == "yes", 1), else_=0)).label("yes_count")
    no_count = func.sum(case((Vote.vote == "no", 1), else_=0)).label("no_count")
    abstain_count = func.sum(case((Vote.vote == "abstain", 1), else_=0)).label("abstain_count")

    counts_subq = (
        db.query(Vote.proposal_id.label("proposal_id"), yes_count, no_count, abstain_count)
        .group_by(Vote.proposal_id)
        .subquery()
    )

    query = (
        db.query(
            Proposal,
            func.coalesce(counts_subq.c.yes_count, 0),
            func.coalesce(counts_subq.c.no_count, 0),
            func.coalesce(counts_subq.c.abstain_count, 0),
        )
        .outerjoin(counts_subq, counts_subq.c.proposal_id == Proposal.id)
        .options(selectinload(Proposal.author))
        .order_by(desc(Proposal.created_at))
    )
    if scope != "all":
        query = apply_live_run_window(query, Proposal.created_at, get_live_run_window(db))
    if status:
        query = query.filter(Proposal.status == status)

    rows = query.offset(offset).limit(limit).all()

    results: list[ProposalResponse] = []
    for proposal, yes, no, abstain in rows:
        results.append(
            ProposalResponse(
                id=proposal.id,
                title=proposal.title,
                description=proposal.description,
                proposal_type=proposal.proposal_type,
                governance_class=governance_payload_for_proposal(proposal)["governance_class"],
                runtime_effect=(
                    proposal.runtime_effect if isinstance(proposal.runtime_effect, dict) else {}
                ),
                governance=governance_payload_for_proposal(proposal),
                status=proposal.status,
                created_at=proposal.created_at.isoformat() if proposal.created_at else None,
                voting_closes_at=proposal.voting_closes_at.isoformat()
                if proposal.voting_closes_at
                else None,
                resolved_at=proposal.resolved_at.isoformat() if proposal.resolved_at else None,
                author=_agent_info(proposal.author),
                votes_for=int(yes or 0),
                votes_against=int(no or 0),
                votes_abstain=int(abstain or 0),
            )
        )

    return results


@router.get("/duplicate-waves")
def list_proposal_duplicate_waves(
    limit: int = Query(8, ge=1, le=50),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Cluster repeated proposal waves for viewer diagnostics."""
    run_window = get_live_run_window(db) if scope != "all" else None
    return collect_duplicate_waves(
        db,
        run_window=run_window,
        sources=("proposal",),
        min_cluster_size=2,
        limit=limit,
    )


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
def get_proposal(proposal_id: int, db: Session = Depends(get_db)):
    """Get a proposal with vote details and counts."""
    proposal = (
        db.query(Proposal)
        .options(joinedload(Proposal.author))
        .filter(Proposal.id == proposal_id)
        .first()
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    votes = (
        db.query(Vote)
        .options(joinedload(Vote.agent))
        .filter(Vote.proposal_id == proposal.id)
        .order_by(Vote.created_at.asc())
        .all()
    )

    counts = {"yes": 0, "no": 0, "abstain": 0}
    for v in votes:
        if v.vote in counts:
            counts[v.vote] += 1

    return ProposalDetailResponse(
        id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        proposal_type=proposal.proposal_type,
        governance_class=governance_payload_for_proposal(proposal)["governance_class"],
        runtime_effect=proposal.runtime_effect if isinstance(proposal.runtime_effect, dict) else {},
        governance=governance_payload_for_proposal(proposal),
        status=proposal.status,
        created_at=proposal.created_at.isoformat() if proposal.created_at else None,
        voting_closes_at=proposal.voting_closes_at.isoformat()
        if proposal.voting_closes_at
        else None,
        resolved_at=proposal.resolved_at.isoformat() if proposal.resolved_at else None,
        author=_agent_info(proposal.author),
        votes_for=counts["yes"],
        votes_against=counts["no"],
        votes_abstain=counts["abstain"],
        votes=[
            VoteResponse(
                id=v.id,
                vote=v.vote,
                reasoning=v.reasoning,
                created_at=v.created_at.isoformat() if v.created_at else None,
                agent=_agent_info(v.agent),
            )
            for v in votes
        ],
    )
