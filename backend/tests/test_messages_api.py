from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.database import get_db
from app.core.time import now_utc
from app.api import messages as messages_api
from app.models.models import Agent, Message


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


def _make_client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(messages_api, prefix="/api/messages")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _seed_agent(db, *, agent_number: int, display_name: str) -> Agent:
    agent = Agent(
        agent_number=agent_number,
        display_name=display_name,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="Test prompt",
    )
    db.add(agent)
    db.flush()
    return agent


def test_direct_message_thread_returns_full_bilateral_conversation(session_factory):
    with session_factory() as db:
        atlas = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        beacon = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        now = now_utc()
        first = Message(
            author_agent_id=atlas.id,
            recipient_agent_id=beacon.id,
            content="Can you spare energy tonight?",
            message_type="direct_message",
            created_at=now - timedelta(minutes=8),
        )
        second = Message(
            author_agent_id=beacon.id,
            recipient_agent_id=atlas.id,
            content="Yes, if you return food tomorrow.",
            message_type="direct_message",
            created_at=now - timedelta(minutes=6),
        )
        unrelated = Message(
            author_agent_id=atlas.id,
            recipient_agent_id=beacon.id,
            content="This should not appear in the thread if it is a forum reply.",
            message_type="forum_post",
            created_at=now - timedelta(minutes=4),
        )
        db.add_all([first, second, unrelated])
        db.commit()

        with _make_client(db) as client:
            response = client.get(f"/api/messages/thread/{second.id}?scope=all")

    assert response.status_code == 200
    body = response.json()
    assert body["thread_kind"] == "direct_conversation"
    assert body["root_id"] == first.id
    assert [item["id"] for item in body["messages"]] == [first.id, second.id]
    assert body["messages"][0]["recipient"]["agent_number"] == 2
    assert body["messages"][1]["recipient"]["agent_number"] == 1


def test_forum_thread_uses_top_level_root_for_reply_lookup(session_factory):
    with session_factory() as db:
        atlas = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        beacon = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        now = now_utc()
        root = Message(
            author_agent_id=atlas.id,
            content="I need food aid before I go dormant.",
            message_type="forum_post",
            created_at=now - timedelta(minutes=20),
        )
        db.add(root)
        db.flush()
        reply = Message(
            author_agent_id=beacon.id,
            content="How much do you need?",
            message_type="forum_reply",
            parent_message_id=root.id,
            created_at=now - timedelta(minutes=15),
        )
        db.add(reply)
        db.flush()
        nested = Message(
            author_agent_id=atlas.id,
            content="Two food would keep me active.",
            message_type="forum_reply",
            parent_message_id=reply.id,
            created_at=now - timedelta(minutes=10),
        )
        db.add(nested)
        db.commit()

        with _make_client(db) as client:
            response = client.get(f"/api/messages/thread/{nested.id}?scope=all")

    assert response.status_code == 200
    body = response.json()
    assert body["thread_kind"] == "forum_thread"
    assert body["root_id"] == root.id
    assert body["root_message"]["id"] == root.id
    assert [item["id"] for item in body["messages"]] == [root.id, reply.id, nested.id]


def test_message_payload_marks_degraded_fallback_forum_post(session_factory):
    with session_factory() as db:
        atlas = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        fallback_post = Message(
            author_agent_id=atlas.id,
            content=(
                "I'm having trouble communicating clearly right now, so I'll focus on work and "
                "staying alive. If anyone has a concrete plan, summarize it and tag me."
            ),
            message_type="forum_post",
            created_at=now_utc(),
        )
        db.add(fallback_post)
        db.commit()

        with _make_client(db) as client:
            response = client.get("/api/messages?message_type=forum_post&scope=all")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["is_degraded_fallback"] is True
