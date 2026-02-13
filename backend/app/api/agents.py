"""
Agents API Router
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import get_db
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, AgentLineage, Event, Message, Proposal, SimulationRun, Vote
from pydantic import BaseModel
from pydantic.config import ConfigDict

router = APIRouter()

MEANINGFUL_ACTION_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "work",
    "trade",
    "vote_enforcement",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
}


class AgentResponse(BaseModel):
    id: int
    agent_number: int
    display_name: Optional[str]
    model_type: str
    tier: int
    personality_type: str
    status: str
    created_at: str
    last_active_at: str
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class InventoryResponse(BaseModel):
    resource_type: str
    quantity: float
    
    model_config = ConfigDict(from_attributes=True)


class AgentDetailResponse(AgentResponse):
    inventory: List[InventoryResponse]
    profile_stats: dict
    lineage: dict


def _count_query(db: Session, model_field, *filters) -> int:
    value = db.query(func.count(model_field)).filter(*filters).scalar()
    return int(value or 0)


def _build_profile_stats(db: Session, *, agent: Agent) -> dict:
    total_actions = _count_query(db, Event.id, Event.agent_id == agent.id)
    meaningful_actions = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type.in_(MEANINGFUL_ACTION_EVENT_TYPES),
    )
    invalid_actions = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type == "invalid_action",
    )
    messages_authored = _count_query(db, Message.id, Message.author_agent_id == agent.id)
    proposals_created = _count_query(db, Proposal.id, Proposal.author_agent_id == agent.id)
    votes_cast = _count_query(db, Vote.id, Vote.agent_id == agent.id)
    laws_passed = _count_query(
        db,
        Event.id,
        Event.agent_id == agent.id,
        Event.event_type == "law_passed",
    )
    invalid_action_rate = (float(invalid_actions) / float(total_actions)) if total_actions > 0 else 0.0
    days_since_created = 0.0
    if agent.created_at is not None:
        created_at_value = agent.created_at
        current_time = now_utc()
        if getattr(created_at_value, "tzinfo", None) is None:
            current_time = current_time.replace(tzinfo=None)
        elapsed_seconds = (current_time - created_at_value).total_seconds()
        days_since_created = max(0.0, elapsed_seconds / 86400.0)

    return {
        "total_actions": int(total_actions),
        "meaningful_actions": int(meaningful_actions),
        "invalid_actions": int(invalid_actions),
        "invalid_action_rate": round(float(invalid_action_rate), 4),
        "messages_authored": int(messages_authored),
        "proposals_created": int(proposals_created),
        "votes_cast": int(votes_cast),
        "laws_passed": int(laws_passed),
        "days_since_created": round(float(days_since_created), 2),
    }


def _resolve_lineage_context(db: Session, *, agent_number: int) -> dict:
    current_season_row = (
        db.query(SimulationRun.season_id)
        .filter(
            SimulationRun.season_id.isnot(None),
            SimulationRun.season_id != "",
            SimulationRun.ended_at.is_(None),
        )
        .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
        .first()
    )
    if current_season_row is None:
        current_season_row = (
            db.query(SimulationRun.season_id)
            .filter(
                SimulationRun.season_id.isnot(None),
                SimulationRun.season_id != "",
            )
            .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
            .first()
        )

    current_season_id = str(current_season_row.season_id or "").strip() if current_season_row else ""
    current_season_id = current_season_id or None

    lineage_row = None
    if current_season_id:
        lineage_row = (
            db.query(AgentLineage)
            .filter(
                AgentLineage.season_id == current_season_id,
                AgentLineage.child_agent_number == int(agent_number),
            )
            .first()
        )

    if lineage_row is None:
        lineage_row = (
            db.query(AgentLineage)
            .filter(AgentLineage.child_agent_number == int(agent_number))
            .order_by(AgentLineage.created_at.desc(), AgentLineage.id.desc())
            .first()
        )

    origin = str(lineage_row.origin).strip() if lineage_row and lineage_row.origin else ""
    origin = origin if origin in {"carryover", "fresh"} else None
    parent_agent_number = (
        int(lineage_row.parent_agent_number)
        if lineage_row and lineage_row.parent_agent_number is not None
        else None
    )
    lineage_season_id = str(lineage_row.season_id or "").strip() if lineage_row and lineage_row.season_id else None

    return {
        "current_season_id": current_season_id,
        "lineage_season_id": lineage_season_id,
        "origin": origin,
        "is_carryover": bool(origin == "carryover"),
        "is_fresh": bool(origin == "fresh"),
        "parent_agent_number": parent_agent_number,
    }


@router.get("", response_model=List[AgentResponse])
def list_agents(
    status: Optional[str] = None,
    tier: Optional[int] = None,
    model_type: Optional[str] = None,
    personality_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all agents with optional filters."""
    query = db.query(Agent)
    
    if status:
        query = query.filter(Agent.status == status)
    if tier:
        query = query.filter(Agent.tier == tier)
    if model_type:
        query = query.filter(Agent.model_type == model_type)
    if personality_type:
        query = query.filter(Agent.personality_type == personality_type)
    
    agents = query.order_by(Agent.agent_number).all()
    
    return [
        AgentResponse(
            id=a.id,
            agent_number=a.agent_number,
            display_name=a.display_name,
            model_type=a.model_type,
            tier=a.tier,
            personality_type=a.personality_type,
            status=a.status,
            created_at=a.created_at.isoformat() if a.created_at else "",
            last_active_at=a.last_active_at.isoformat() if a.last_active_at else "",
        )
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentDetailResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    """Get detailed agent information."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    inventory = db.query(AgentInventory).filter(
        AgentInventory.agent_id == agent.id
    ).all()
    
    return AgentDetailResponse(
        id=agent.id,
        agent_number=agent.agent_number,
        display_name=agent.display_name,
        model_type=agent.model_type,
        tier=agent.tier,
        personality_type=agent.personality_type,
        status=agent.status,
        created_at=agent.created_at.isoformat() if agent.created_at else "",
        last_active_at=agent.last_active_at.isoformat() if agent.last_active_at else "",
        inventory=[
            InventoryResponse(
                resource_type=inv.resource_type,
                quantity=float(inv.quantity)
            )
            for inv in inventory
        ],
        profile_stats=_build_profile_stats(db, agent=agent),
        lineage=_resolve_lineage_context(db, agent_number=int(agent.agent_number)),
    )


@router.get("/{agent_id}/actions")
def get_agent_actions(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get agent's action history."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    events = db.query(Event).filter(
        Event.agent_id == agent.id
    ).order_by(desc(Event.created_at)).limit(limit).all()
    
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "description": e.description,
            "metadata": e.event_metadata,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{agent_id}/messages")
def get_agent_messages(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get messages authored by agent."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    messages = db.query(Message).filter(
        Message.author_agent_id == agent.id
    ).order_by(desc(Message.created_at)).limit(limit).all()
    
    return [
        {
            "id": m.id,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.get("/{agent_id}/votes")
def get_agent_votes(
    agent_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get agent's voting history."""
    agent = db.query(Agent).filter(Agent.agent_number == agent_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    votes = db.query(Vote).filter(
        Vote.agent_id == agent.id
    ).order_by(desc(Vote.created_at)).limit(limit).all()
    
    return [
        {
            "id": v.id,
            "proposal_id": v.proposal_id,
            "vote": v.vote,
            "reasoning": v.reasoning,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in votes
    ]
