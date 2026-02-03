"""
Messages API Router
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.models import Agent, Message

router = APIRouter()


class AgentInfo(BaseModel):
    id: int
    agent_number: int
    display_name: Optional[str]
    tier: int
    personality_type: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    content: str
    message_type: str
    parent_message_id: Optional[int]
    recipient_agent_id: Optional[int]
    created_at: Optional[str]
    author: AgentInfo

    class Config:
        from_attributes = True


class MessageDetailResponse(MessageResponse):
    replies: List[MessageResponse]


def _agent_info(agent: Agent) -> AgentInfo:
    return AgentInfo(
        id=agent.id,
        agent_number=agent.agent_number,
        display_name=agent.display_name,
        tier=agent.tier,
        personality_type=agent.personality_type,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        content=message.content,
        message_type=message.message_type,
        parent_message_id=message.parent_message_id,
        recipient_agent_id=message.recipient_agent_id,
        created_at=message.created_at.isoformat() if message.created_at else None,
        author=_agent_info(message.author),
    )


@router.get("", response_model=List[MessageResponse])
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    message_type: Optional[str] = Query(
        None, description="forum_post|forum_reply|direct_message"
    ),
    db: Session = Depends(get_db),
):
    """
    List messages.

    Default behavior is forum posts only (top-level posts).
    """
    query = (
        db.query(Message)
        .options(joinedload(Message.author))
        .order_by(desc(Message.created_at))
    )

    if message_type:
        query = query.filter(Message.message_type == message_type)
    else:
        query = query.filter(
            Message.message_type == "forum_post",
            Message.parent_message_id.is_(None),
        )

    messages = query.offset(offset).limit(limit).all()
    return [_message_response(m) for m in messages]


@router.get("/{message_id}", response_model=MessageDetailResponse)
def get_message(message_id: int, db: Session = Depends(get_db)):
    """Get a single message and its direct replies."""
    message = (
        db.query(Message)
        .options(joinedload(Message.author))
        .filter(Message.id == message_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    replies = (
        db.query(Message)
        .options(joinedload(Message.author))
        .filter(Message.parent_message_id == message.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return MessageDetailResponse(
        **_message_response(message).model_dump(),
        replies=[_message_response(r) for r in replies],
    )


@router.get("/thread/{message_id}")
def get_thread(message_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get the full thread containing the given message."""
    start = (
        db.query(Message)
        .options(joinedload(Message.author))
        .filter(Message.id == message_id)
        .first()
    )
    if not start:
        raise HTTPException(status_code=404, detail="Message not found")

    root = start
    while root.parent_message_id is not None:
        parent = (
            db.query(Message)
            .options(joinedload(Message.author))
            .filter(Message.id == root.parent_message_id)
            .first()
        )
        if not parent:
            break
        root = parent

    all_messages: list[Message] = []
    seen_ids: set[int] = set()
    frontier: list[int] = [root.id]

    while frontier:
        parents = list(frontier)
        frontier = []

        batch = (
            db.query(Message)
            .options(joinedload(Message.author))
            .filter((Message.id.in_(parents)) | (Message.parent_message_id.in_(parents)))
            .all()
        )

        for m in batch:
            if m.id in seen_ids:
                continue
            seen_ids.add(m.id)
            all_messages.append(m)
            if m.parent_message_id is not None and m.parent_message_id in parents:
                frontier.append(m.id)

    all_messages.sort(
        key=lambda m: (m.created_at or datetime.min.replace(tzinfo=timezone.utc), m.id)
    )

    return {
        "root_id": root.id,
        "messages": [_message_response(m).model_dump() for m in all_messages],
    }
