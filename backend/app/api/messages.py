"""
Messages API Router
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.models import Agent, Message
from app.services.duplicate_waves import collect_duplicate_waves
from app.services.live_run_scope import apply_live_run_window, get_live_run_window
from app.services.run_policy import is_deterministic_fallback_forum_post_content

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
    recipient: Optional[AgentInfo] = None
    is_degraded_fallback: bool = False
    reply_count: int = 0
    latest_reply_at: Optional[str] = None
    latest_activity_at: Optional[str] = None

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


def _message_response(message: Message, *, thread_activity: Optional[dict[str, Any]] = None) -> MessageResponse:
    activity = thread_activity or {}
    latest_reply_at = activity.get("latest_reply_at")
    latest_activity_at = activity.get("latest_activity_at") or message.created_at
    return MessageResponse(
        id=message.id,
        content=message.content,
        message_type=message.message_type,
        parent_message_id=message.parent_message_id,
        recipient_agent_id=message.recipient_agent_id,
        created_at=message.created_at.isoformat() if message.created_at else None,
        author=_agent_info(message.author),
        recipient=_agent_info(message.recipient) if message.recipient else None,
        is_degraded_fallback=(
            str(message.message_type or "").strip() == "forum_post"
            and is_deterministic_fallback_forum_post_content(message.content)
        ),
        reply_count=int(activity.get("reply_count") or 0),
        latest_reply_at=latest_reply_at.isoformat() if latest_reply_at else None,
        latest_activity_at=latest_activity_at.isoformat() if latest_activity_at else None,
    )


def _base_message_query(db: Session):
    return db.query(Message).options(
        joinedload(Message.author),
        joinedload(Message.recipient),
    )


def _thread_activity_for_roots(
    db: Session,
    root_messages: list[Message],
    *,
    scope: str,
) -> dict[int, dict[str, Any]]:
    root_ids = [
        int(message.id)
        for message in root_messages
        if str(message.message_type or "") == "forum_post" and message.parent_message_id is None
    ]
    if not root_ids:
        return {}

    run_window = get_live_run_window(db)
    reply_query = db.query(
        Message.parent_message_id.label("root_id"),
        func.count(Message.id).label("reply_count"),
        func.max(Message.created_at).label("latest_reply_at"),
    ).filter(Message.parent_message_id.in_(root_ids))
    if scope != "all":
        reply_query = apply_live_run_window(reply_query, Message.created_at, run_window)
    rows = reply_query.group_by(Message.parent_message_id).all()
    by_root = {
        int(row.root_id): {
            "reply_count": int(row.reply_count or 0),
            "latest_reply_at": row.latest_reply_at,
            "latest_activity_at": row.latest_reply_at,
        }
        for row in rows
    }
    for message in root_messages:
        if int(message.id) in root_ids and int(message.id) not in by_root:
            by_root[int(message.id)] = {
                "reply_count": 0,
                "latest_reply_at": None,
                "latest_activity_at": message.created_at,
            }
    return by_root


@router.get("", response_model=List[MessageResponse])
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    message_type: Optional[str] = Query(
        None, description="forum_post|forum_reply|direct_message"
    ),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
):
    """
    List messages.

    Default behavior is forum posts only (top-level posts).
    """
    query = (
        _base_message_query(db)
        .order_by(desc(Message.created_at))
    )
    if scope != "all":
        query = apply_live_run_window(query, Message.created_at, get_live_run_window(db))

    if message_type:
        query = query.filter(Message.message_type == message_type)
    else:
        query = query.filter(
            Message.message_type == "forum_post",
            Message.parent_message_id.is_(None),
        )

    messages = query.offset(offset).limit(limit).all()
    thread_activity = _thread_activity_for_roots(db, messages, scope=scope)
    return [_message_response(m, thread_activity=thread_activity.get(int(m.id))) for m in messages]


@router.get("/duplicate-waves")
def list_message_duplicate_waves(
    limit: int = Query(8, ge=1, le=50),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Cluster repeated forum-message waves for viewer diagnostics."""
    run_window = get_live_run_window(db) if scope != "all" else None
    return collect_duplicate_waves(
        db,
        run_window=run_window,
        sources=("forum",),
        min_cluster_size=2,
        limit=limit,
    )


@router.get("/{message_id}", response_model=MessageDetailResponse)
def get_message(
    message_id: int,
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
):
    """Get a single message and its direct replies."""
    run_window = get_live_run_window(db)
    message_query = (
        _base_message_query(db)
    )
    if scope != "all":
        message_query = apply_live_run_window(message_query, Message.created_at, run_window)
    message = message_query.filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    replies_query = (
        _base_message_query(db)
        .filter(Message.parent_message_id == message.id)
    )
    if scope != "all":
        replies_query = apply_live_run_window(replies_query, Message.created_at, run_window)
    replies = replies_query.order_by(Message.created_at.asc()).all()

    return MessageDetailResponse(
        **_message_response(message).model_dump(),
        replies=[_message_response(r) for r in replies],
    )


@router.get("/thread/{message_id}")
def get_thread(
    message_id: int,
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get the full thread containing the given message."""
    run_window = get_live_run_window(db)
    start_query = (
        _base_message_query(db)
    )
    if scope != "all":
        start_query = apply_live_run_window(start_query, Message.created_at, run_window)
    start = start_query.filter(Message.id == message_id).first()
    if not start:
        raise HTTPException(status_code=404, detail="Message not found")

    if start.message_type == "direct_message":
        participant_ids = sorted(
            {
                int(start.author_agent_id or 0),
                int(start.recipient_agent_id or 0),
            }
        )
        if len(participant_ids) != 2 or participant_ids[0] <= 0 or participant_ids[1] <= 0:
            raise HTTPException(status_code=400, detail="Direct message is missing conversation participants")

        conversation_query = _base_message_query(db).filter(
            Message.message_type == "direct_message",
            (
                ((Message.author_agent_id == participant_ids[0]) & (Message.recipient_agent_id == participant_ids[1]))
                |
                ((Message.author_agent_id == participant_ids[1]) & (Message.recipient_agent_id == participant_ids[0]))
            ),
        )
        if scope != "all":
            conversation_query = apply_live_run_window(conversation_query, Message.created_at, run_window)
        conversation_messages = conversation_query.order_by(Message.created_at.asc(), Message.id.asc()).all()
        if not conversation_messages:
            raise HTTPException(status_code=404, detail="Message thread not found")
        root = conversation_messages[0]
        return {
            "root_id": root.id,
            "thread_kind": "direct_conversation",
            "root_message": _message_response(root).model_dump(),
            "messages": [_message_response(m).model_dump() for m in conversation_messages],
        }

    root = start
    while root.parent_message_id is not None:
        parent = (
            _base_message_query(db)
            .filter(Message.id == root.parent_message_id)
            .first()
        )
        if not parent:
            break
        if scope != "all":
            parent_ts = parent.created_at or datetime.min.replace(tzinfo=timezone.utc)
            if run_window.started_at and parent_ts < run_window.started_at:
                break
            if run_window.ended_at and parent_ts > run_window.ended_at:
                break
        root = parent

    all_messages: list[Message] = []
    seen_ids: set[int] = set()
    frontier: list[int] = [root.id]

    while frontier:
        parents = list(frontier)
        frontier = []

        batch_query = (
            _base_message_query(db)
            .filter((Message.id.in_(parents)) | (Message.parent_message_id.in_(parents)))
        )
        if scope != "all":
            batch_query = apply_live_run_window(batch_query, Message.created_at, run_window)
        batch = batch_query.all()

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
        "thread_kind": "forum_thread",
        "root_message": _message_response(root).model_dump(),
        "messages": [_message_response(m).model_dump() for m in all_messages],
    }
