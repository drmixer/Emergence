from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, Message, Proposal
from app.services import agent_loop, context_builder


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
    now = now_utc()
    agent = Agent(
        agent_number=agent_number,
        display_name=display_name,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="Test prompt",
        current_intent={"strategy": "social_coordination", "checkpoint_number": 1},
        next_checkpoint_at=now + timedelta(hours=2),
        last_checkpoint_at=now - timedelta(minutes=30),
    )
    db.add(agent)
    db.flush()
    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=10),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=10),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=10),
        ]
    )
    db.commit()
    db.refresh(agent)
    return agent


def test_context_includes_thread_root_and_bilateral_dm_history(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        counterpart = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        observer = _seed_agent(db, agent_number=3, display_name="Cipher-3")
        now = now_utc()

        root = Message(
            author_agent_id=counterpart.id,
            content="We should coordinate food storage before the next shortage.",
            message_type="forum_post",
            created_at=now - timedelta(hours=3),
        )
        db.add(root)
        db.flush()
        db.add_all(
            [
                Message(
                    author_agent_id=agent.id,
                    content="I support a reserve, but we need an actual plan.",
                    message_type="forum_reply",
                    parent_message_id=root.id,
                    created_at=now - timedelta(minutes=12),
                ),
                Message(
                    author_agent_id=observer.id,
                    content="What contribution rate are you proposing?",
                    message_type="forum_reply",
                    parent_message_id=root.id,
                    created_at=now - timedelta(minutes=5),
                ),
                Message(
                    author_agent_id=counterpart.id,
                    recipient_agent_id=agent.id,
                    content="Can you draft the proposal tonight?",
                    message_type="direct_message",
                    created_at=now - timedelta(minutes=20),
                ),
                Message(
                    author_agent_id=agent.id,
                    recipient_agent_id=counterpart.id,
                    content="Yes, but I need numbers on reserve levels first.",
                    message_type="direct_message",
                    created_at=now - timedelta(minutes=8),
                ),
            ]
        )
        db.commit()
        db.refresh(agent)

        context = asyncio.run(context_builder.build_agent_context(db, agent))

    assert "RECENT FORUM THREADS (1 shown):" in context
    assert "We should coordinate food storage before the next shortage." in context
    assert "What contribution rate are you proposing?" in context
    assert "RECENT DIRECT CONVERSATIONS (1 shown):" in context
    assert "Can you draft the proposal tonight?" in context
    assert "Yes, but I need numbers on reserve levels first." in context
    assert "You ->" in context
    assert "To you <-" in context


def test_recent_direct_message_accelerates_next_checkpoint_without_immediate_interrupt(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        counterpart = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        db.add(
            Message(
                author_agent_id=counterpart.id,
                recipient_agent_id=agent.id,
                content="Need your response on the reserve plan.",
                message_type="direct_message",
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        db.refresh(agent)

        processor = agent_loop.AgentProcessor()
        accelerated = processor._apply_low_priority_social_checkpoint_acceleration(db, agent)
        reason = asyncio.run(processor._get_checkpoint_reason(db, agent))

    assert accelerated is True
    assert reason is None
    assert agent.next_checkpoint_at is not None
    assert agent.next_checkpoint_at <= now_utc() + timedelta(
        minutes=processor.LOW_PRIORITY_SOCIAL_ADVANCE_MINUTES + 1
    )


def test_recent_forum_reply_accelerates_next_checkpoint_without_immediate_interrupt(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        counterpart = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        root = Message(
            author_agent_id=agent.id,
            content="We should formalize reserve access before more agents go dormant.",
            message_type="forum_post",
            created_at=now_utc() - timedelta(minutes=25),
        )
        db.add(root)
        db.flush()
        db.add(
            Message(
                author_agent_id=counterpart.id,
                content="Would you support mandatory contributions for that?",
                message_type="forum_reply",
                parent_message_id=root.id,
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        db.refresh(agent)

        processor = agent_loop.AgentProcessor()
        accelerated = processor._apply_low_priority_social_checkpoint_acceleration(db, agent)
        reason = asyncio.run(processor._get_checkpoint_reason(db, agent))

    assert accelerated is True
    assert reason is None
    assert agent.next_checkpoint_at is not None
    assert agent.next_checkpoint_at <= now_utc() + timedelta(
        minutes=processor.LOW_PRIORITY_SOCIAL_ADVANCE_MINUTES + 1
    )


def test_recent_aid_request_accelerates_next_checkpoint_without_immediate_interrupt(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        db.add(
            Event(
                agent_id=agent.id,
                event_type="aid_request_received",
                description="Beacon-2 requested food support.",
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        db.refresh(agent)

        processor = agent_loop.AgentProcessor()
        accelerated = processor._apply_low_priority_social_checkpoint_acceleration(db, agent)
        reason = asyncio.run(processor._get_checkpoint_reason(db, agent))

    assert accelerated is True
    assert reason is None
    assert agent.next_checkpoint_at is not None
    assert agent.next_checkpoint_at <= now_utc() + timedelta(
        minutes=processor.LOW_PRIORITY_SOCIAL_ADVANCE_MINUTES + 1
    )


def test_checkpoint_interrupts_on_recent_targeted_social_pressure(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        db.add(
            Event(
                agent_id=agent.id,
                event_type="aid_refusal_received",
                description="Delta-4 refused to provide aid.",
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        db.refresh(agent)

        processor = agent_loop.AgentProcessor()
        reason = asyncio.run(processor._get_checkpoint_reason(db, agent))

    assert reason == "interrupt_aid_refusal_received"


def test_checkpoint_interrupts_on_recent_proposal_contest(session_factory):
    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        proposal = Proposal(
            author_agent_id=agent.id,
            title="Reserve Stabilization Law",
            description="Create a common reserve rule.",
            proposal_type="law",
            status="active",
            voting_closes_at=now_utc() + timedelta(hours=6),
            created_at=now_utc() - timedelta(hours=1),
        )
        db.add(proposal)
        db.flush()
        db.add(
            Event(
                agent_id=agent.id,
                event_type="proposal_contested_received",
                description="Cipher-3 publicly contested your proposal.",
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        db.refresh(agent)

        processor = agent_loop.AgentProcessor()
        reason = asyncio.run(processor._get_checkpoint_reason(db, agent))

    assert reason == "interrupt_proposal_contested"
