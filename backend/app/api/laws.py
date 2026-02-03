"""
Laws API Router
"""

from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.models import Law, Proposal, Agent

router = APIRouter()


class AgentInfo(BaseModel):
    id: int
    agent_number: int
    display_name: Optional[str]
    tier: int
    personality_type: str


class ProposalInfo(BaseModel):
    id: int
    title: str
    proposal_type: str
    status: str
    created_at: Optional[str]


class LawResponse(BaseModel):
    id: int
    title: str
    description: str
    active: bool
    passed_at: Optional[str]
    repealed_at: Optional[str]
    repealed_by_proposal_id: Optional[int]
    author: AgentInfo
    proposal: Optional[ProposalInfo]


def _agent_info(agent: Agent) -> AgentInfo:
    return AgentInfo(
        id=agent.id,
        agent_number=agent.agent_number,
        display_name=agent.display_name,
        tier=agent.tier,
        personality_type=agent.personality_type,
    )


def _proposal_info(proposal: Proposal) -> ProposalInfo:
    return ProposalInfo(
        id=proposal.id,
        title=proposal.title,
        proposal_type=proposal.proposal_type,
        status=proposal.status,
        created_at=proposal.created_at.isoformat() if proposal.created_at else None,
    )


@router.get("", response_model=List[LawResponse])
def list_laws(
    active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List laws with optional active filter."""
    query = (
        db.query(Law)
        .options(joinedload(Law.author), joinedload(Law.proposal))
        .order_by(desc(Law.passed_at))
    )
    if active is not None:
        query = query.filter(Law.active.is_(active))

    laws = query.offset(offset).limit(limit).all()
    results: list[LawResponse] = []
    for law in laws:
        results.append(
            LawResponse(
                id=law.id,
                title=law.title,
                description=law.description,
                active=bool(law.active),
                passed_at=law.passed_at.isoformat() if law.passed_at else None,
                repealed_at=law.repealed_at.isoformat() if law.repealed_at else None,
                repealed_by_proposal_id=law.repealed_by_proposal_id,
                author=_agent_info(law.author),
                proposal=_proposal_info(law.proposal) if law.proposal else None,
            )
        )
    return results


@router.get("/{law_id}", response_model=LawResponse)
def get_law(law_id: int, db: Session = Depends(get_db)):
    """Get law details."""
    law = (
        db.query(Law)
        .options(joinedload(Law.author), joinedload(Law.proposal))
        .filter(Law.id == law_id)
        .first()
    )
    if not law:
        raise HTTPException(status_code=404, detail="Law not found")

    return LawResponse(
        id=law.id,
        title=law.title,
        description=law.description,
        active=bool(law.active),
        passed_at=law.passed_at.isoformat() if law.passed_at else None,
        repealed_at=law.repealed_at.isoformat() if law.repealed_at else None,
        repealed_by_proposal_id=law.repealed_by_proposal_id,
        author=_agent_info(law.author),
        proposal=_proposal_info(law.proposal) if law.proposal else None,
    )

