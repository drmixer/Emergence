"""
Agents API Router
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.models.models import Agent, AgentInventory, Event, Message, Vote
from pydantic import BaseModel

router = APIRouter()


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
    
    class Config:
        from_attributes = True


class InventoryResponse(BaseModel):
    resource_type: str
    quantity: float
    
    class Config:
        from_attributes = True


class AgentDetailResponse(AgentResponse):
    inventory: List[InventoryResponse]


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
        ]
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
            "metadata": e.metadata,
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
