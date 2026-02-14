"""
SSE (Server-Sent Events) implementation for real-time updates.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import Event
from app.services.lineage import (
    agent_number_map,
    lineage_map_for_season,
    lineage_payload_for_agent_number,
    resolve_active_or_latest_season_id,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class EventBroadcaster:
    """Manages SSE connections and broadcasts events."""
    
    def __init__(self):
        self.connections: list[asyncio.Queue] = []
        self._last_event_id = 0
    
    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to event stream."""
        queue = asyncio.Queue()
        self.connections.append(queue)
        logger.info(f"New SSE connection, total: {len(self.connections)}")
        return queue
    
    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from event stream."""
        if queue in self.connections:
            self.connections.remove(queue)
        logger.info(f"SSE connection closed, total: {len(self.connections)}")
    
    async def broadcast(self, event_data: dict):
        """Broadcast an event to all connected clients."""
        message = f"data: {json.dumps(event_data)}\n\n"
        
        for queue in self.connections:
            try:
                await queue.put(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")


# Global broadcaster instance
broadcaster = EventBroadcaster()


async def event_generator(request: Request, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Generate SSE events for a connected client."""
    try:
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to Emergence event stream'})}\n\n"
        
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            try:
                # Wait for new events with timeout
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield message
            except asyncio.TimeoutError:
                # Send keepalive ping
                yield f": keepalive\n\n"
                
    except asyncio.CancelledError:
        pass
    finally:
        await broadcaster.unsubscribe(queue)


@router.get("/stream")
async def event_stream(request: Request):
    """SSE endpoint for real-time event streaming."""
    queue = await broadcaster.subscribe()
    
    return StreamingResponse(
        event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


async def broadcast_event(event: Event, *, lineage_context: dict | None = None):
    """Broadcast a new event to all connected clients."""
    lineage = lineage_context or {}
    event_data = {
        "type": "event",
        "id": event.id,
        "event_type": event.event_type,
        "agent_id": event.agent_id,
        "agent_number": lineage.get("agent_number"),
        "description": event.description,
        "metadata": event.event_metadata or {},
        "lineage_origin": lineage.get("lineage_origin"),
        "lineage_is_carryover": bool(lineage.get("lineage_is_carryover")),
        "lineage_is_fresh": bool(lineage.get("lineage_is_fresh")),
        "lineage_parent_agent_number": lineage.get("lineage_parent_agent_number"),
        "lineage_season_id": lineage.get("lineage_season_id"),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    
    await broadcaster.broadcast(event_data)


async def broadcast_proposal_update(proposal_id: int, status: str):
    """Broadcast proposal status update."""
    event_data = {
        "type": "proposal_update",
        "proposal_id": proposal_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    await broadcaster.broadcast(event_data)


async def broadcast_agent_status(agent_id: int, status: str):
    """Broadcast agent status change (active/dormant)."""
    event_data = {
        "type": "agent_status",
        "agent_id": agent_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    await broadcaster.broadcast(event_data)


# Background task to poll for new events and broadcast them
async def event_polling_task():
    """Poll database for new events and broadcast them."""
    last_id = 0

    # On (re)start, avoid replaying the entire event history over SSE.
    db: Session | None = None
    try:
        db = SessionLocal()
        last_id = int(db.query(func.max(Event.id)).scalar() or 0)
    except Exception as e:
        logger.error(f"Error initializing event polling cursor: {e}")
        last_id = 0
    finally:
        if db is not None:
            db.close()
    
    while True:
        db: Session | None = None
        try:
            db = SessionLocal()

            new_events = (
                db.query(Event)
                .filter(Event.id > last_id)
                .order_by(Event.id)
                .limit(50)
                .all()
            )

            agent_ids = {int(item.agent_id) for item in new_events if item.agent_id is not None}
            numbers_by_id = agent_number_map(db, agent_ids=agent_ids)
            season_id = resolve_active_or_latest_season_id(db)
            lineage_by_agent_number = lineage_map_for_season(db, season_id=season_id)

            for event in new_events:
                agent_number = numbers_by_id.get(int(event.agent_id or 0))
                lineage = lineage_payload_for_agent_number(agent_number, lineage_by_agent_number)
                lineage["agent_number"] = int(agent_number) if agent_number is not None else None
                await broadcast_event(event, lineage_context=lineage)
                last_id = max(last_id, event.id)

        except Exception as e:
            logger.error(f"Error in event polling: {e}")
        finally:
            if db is not None:
                db.close()
        
        await asyncio.sleep(1)  # Poll every second
