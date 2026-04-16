from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, Event, Message
from app.services import actions, context_builder


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
    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("10")),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("10")),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("10")),
        ]
    )
    db.commit()
    db.refresh(agent)
    return agent


def test_public_accusation_creates_forum_post_and_target_notice(session_factory):
    with session_factory() as db:
        accuser = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        target = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        target_id = target.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 2,
                    "content": "You kept reserve food while others were starving.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 2,
                    "content": "You kept reserve food while others were starving.",
                },
            )
        )

        forum_post = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "accusation_received").one()

    assert result["success"] is True
    assert forum_post.message_type == "forum_post"
    assert "Public accusation against Beacon-2" in forum_post.content
    assert notice.agent_id == target_id
    assert "publicly accused you" in notice.description


def test_refuse_aid_creates_direct_message_and_target_notice(session_factory):
    with session_factory() as db:
        refuser = _seed_agent(db, agent_number=3, display_name="Cipher-3")
        target = _seed_agent(db, agent_number=4, display_name="Delta-4")
        target_id = target.id

        validation = asyncio.run(
            actions.validate_action(
                db,
                refuser,
                {
                    "action": "refuse_aid",
                    "target_agent_id": 4,
                    "reason": "I am too close to dormancy to spare food.",
                },
            )
        )
        assert validation["valid"] is True

        result = asyncio.run(
            actions.execute_action(
                db,
                refuser,
                {
                    "action": "refuse_aid",
                    "target_agent_id": 4,
                    "reason": "I am too close to dormancy to spare food.",
                },
            )
        )

        direct_message = db.query(Message).filter(Message.id == result["message_id"]).one()
        notice = db.query(Event).filter(Event.event_type == "aid_refusal_received").one()

    assert result["success"] is True
    assert direct_message.message_type == "direct_message"
    assert direct_message.recipient_agent_id == target_id
    assert "refusing your request or expectation for aid" in direct_message.content
    assert notice.agent_id == target_id
    assert "refused to provide aid" in notice.description


def test_targeted_conflict_notice_appears_in_agent_context(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        accuser = _seed_agent(db, agent_number=5, display_name="Echo-5")
        target = _seed_agent(db, agent_number=6, display_name="Flux-6")

        asyncio.run(
            actions.execute_action(
                db,
                accuser,
                {
                    "action": "public_accusation",
                    "target_agent_id": 6,
                    "content": "You are avoiding shared sacrifice.",
                },
            )
        )
        db.refresh(target)

        context = asyncio.run(context_builder.build_agent_context(db, target))

    assert "publicly accused you" in context
    assert "Echo-5" in context
