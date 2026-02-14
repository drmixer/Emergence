"""
Events API Router
"""

from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Event
from app.services.lineage import (
    agent_number_map,
    lineage_map_for_season,
    lineage_payload_for_agent_number,
    resolve_active_or_latest_season_id,
)

router = APIRouter()


class EventResponse(BaseModel):
    id: int
    agent_id: Optional[int]
    agent_number: Optional[int] = None
    event_type: str
    description: str
    metadata: dict
    lineage_origin: Optional[str] = None
    lineage_is_carryover: bool = False
    lineage_is_fresh: bool = False
    lineage_parent_agent_number: Optional[int] = None
    lineage_season_id: Optional[str] = None
    created_at: Optional[str]


def _build_lineage_context_by_agent_id(db: Session, events: list[Event]) -> dict[int, dict]:
    agent_ids = {int(event.agent_id) for event in events if event.agent_id is not None}
    by_agent_id: dict[int, dict] = {}
    if not agent_ids:
        return by_agent_id

    numbers_by_id = agent_number_map(db, agent_ids=agent_ids)
    season_id = resolve_active_or_latest_season_id(db)
    lineage_by_agent_number = lineage_map_for_season(db, season_id=season_id)

    for agent_id, agent_number in numbers_by_id.items():
        payload = lineage_payload_for_agent_number(agent_number, lineage_by_agent_number)
        payload["agent_number"] = int(agent_number)
        by_agent_id[int(agent_id)] = payload

    return by_agent_id


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
    lineage_by_agent_id = _build_lineage_context_by_agent_id(db, events)
    payload: list[EventResponse] = []
    for event in events:
        lineage = lineage_by_agent_id.get(int(event.agent_id or 0), {})
        payload.append(
            EventResponse(
                id=event.id,
                agent_id=event.agent_id,
                agent_number=lineage.get("agent_number"),
                event_type=event.event_type,
                description=event.description,
                metadata=event.event_metadata or {},
                lineage_origin=lineage.get("lineage_origin"),
                lineage_is_carryover=bool(lineage.get("lineage_is_carryover")),
                lineage_is_fresh=bool(lineage.get("lineage_is_fresh")),
                lineage_parent_agent_number=lineage.get("lineage_parent_agent_number"),
                lineage_season_id=lineage.get("lineage_season_id"),
                created_at=event.created_at.isoformat() if event.created_at else None,
            )
        )
    return payload


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Fetch a single event by ID."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    lineage_by_agent_id = _build_lineage_context_by_agent_id(db, [event])
    lineage = lineage_by_agent_id.get(int(event.agent_id or 0), {})

    return EventResponse(
        id=event.id,
        agent_id=event.agent_id,
        agent_number=lineage.get("agent_number"),
        event_type=event.event_type,
        description=event.description,
        metadata=event.event_metadata or {},
        lineage_origin=lineage.get("lineage_origin"),
        lineage_is_carryover=bool(lineage.get("lineage_is_carryover")),
        lineage_is_fresh=bool(lineage.get("lineage_is_fresh")),
        lineage_parent_agent_number=lineage.get("lineage_parent_agent_number"),
        lineage_season_id=lineage.get("lineage_season_id"),
        created_at=event.created_at.isoformat() if event.created_at else None,
    )
