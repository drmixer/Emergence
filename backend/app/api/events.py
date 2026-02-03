"""
Events API Router
"""

from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Event

router = APIRouter()


class EventResponse(BaseModel):
    id: int
    agent_id: Optional[int]
    event_type: str
    description: str
    metadata: dict
    created_at: Optional[str]


@router.get("", response_model=List[EventResponse])
def list_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    type: Optional[str] = Query(None, description="Filter by event_type"),
    db: Session = Depends(get_db),
):
    """Paginated event log."""
    query = db.query(Event).order_by(desc(Event.created_at))
    if type:
        query = query.filter(Event.event_type == type)

    events = query.offset(offset).limit(limit).all()
    return [
        EventResponse(
            id=e.id,
            agent_id=e.agent_id,
            event_type=e.event_type,
            description=e.description,
            metadata=e.event_metadata or {},
            created_at=e.created_at.isoformat() if e.created_at else None,
        )
        for e in events
    ]

