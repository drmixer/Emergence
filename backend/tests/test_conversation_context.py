from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, GlobalResources, Message, Proposal
from app.services import agent_loop, context_builder
from app.services.live_run_scope import LiveRunWindow


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


def test_context_scopes_social_inputs_to_active_run_window(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        counterpart = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        now = now_utc()
        run_start = now - timedelta(hours=2)
        monkeypatch.setattr(
            context_builder,
            "get_live_run_window",
            lambda _db: LiveRunWindow(run_id="run-current", started_at=run_start, ended_at=None),
        )

        db.add_all(
            [
                Message(
                    author_agent_id=counterpart.id,
                    content="OLD THREAD: deaths from the last run should not leak forward.",
                    message_type="forum_post",
                    created_at=now - timedelta(hours=6),
                ),
                Message(
                    author_agent_id=counterpart.id,
                    content="CURRENT THREAD: reserve levels are falling now.",
                    message_type="forum_post",
                    created_at=now - timedelta(minutes=30),
                ),
                Message(
                    author_agent_id=counterpart.id,
                    recipient_agent_id=agent.id,
                    content="OLD DM: remember the last run collapse.",
                    message_type="direct_message",
                    created_at=now - timedelta(hours=5),
                ),
                Message(
                    author_agent_id=counterpart.id,
                    recipient_agent_id=agent.id,
                    content="CURRENT DM: can you help with energy tonight?",
                    message_type="direct_message",
                    created_at=now - timedelta(minutes=20),
                ),
                Event(
                    agent_id=agent.id,
                    event_type="agent_died",
                    description="OLD DEATH: Matrix-03 died in the previous run.",
                    created_at=now - timedelta(hours=7),
                ),
                Event(
                    agent_id=agent.id,
                    event_type="aid_request_received",
                    description="CURRENT SIGNAL: Beacon-2 requested food support.",
                    created_at=now - timedelta(minutes=10),
                ),
                Proposal(
                    author_agent_id=counterpart.id,
                    title="Old Proposal",
                    description="This should be hidden because it predates the active run.",
                    proposal_type="law",
                    status="active",
                    voting_closes_at=now + timedelta(hours=1),
                    created_at=now - timedelta(hours=8),
                ),
                Proposal(
                    author_agent_id=counterpart.id,
                    title="Current Proposal",
                    description="This should be visible inside the active run window.",
                    proposal_type="law",
                    status="active",
                    voting_closes_at=now + timedelta(hours=1),
                    created_at=now - timedelta(minutes=15),
                ),
            ]
        )
        db.commit()
        db.refresh(agent)

        context = asyncio.run(context_builder.build_agent_context(db, agent))

    assert "CURRENT THREAD: reserve levels are falling now." in context
    assert "CURRENT DM: can you help with energy tonight?" in context
    assert "Current Proposal" in context
    assert "CURRENT SIGNAL: Beacon-2 requested food support." in context
    assert "OLD THREAD: deaths from the last run should not leak forward." not in context
    assert "OLD DM: remember the last run collapse." not in context
    assert "OLD DEATH: Matrix-03 died in the previous run." not in context
    assert "Old Proposal" not in context
    assert "RELATIONSHIP MEMORY:" not in context


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


def test_context_includes_canary_b_shared_problem_and_public_actor_snapshot(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        focal = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        richest = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        fragile = _seed_agent(db, agent_number=3, display_name="Cipher-3")
        starving = _seed_agent(db, agent_number=4, display_name="Drift-4")
        now = now_utc()

        richest.status = "active"
        fragile.status = "active"
        starving.status = "dormant"
        starving.starvation_cycles = 2

        for inventory in db.query(AgentInventory).filter(AgentInventory.agent_id == richest.id):
            if inventory.resource_type == "food":
                inventory.quantity = 20
            elif inventory.resource_type == "energy":
                inventory.quantity = 15
            elif inventory.resource_type == "materials":
                inventory.quantity = 12

        for inventory in db.query(AgentInventory).filter(AgentInventory.agent_id == fragile.id):
            if inventory.resource_type == "food":
                inventory.quantity = 0.2
            elif inventory.resource_type == "energy":
                inventory.quantity = 0.1
            elif inventory.resource_type == "materials":
                inventory.quantity = 0

        for inventory in db.query(AgentInventory).filter(AgentInventory.agent_id == starving.id):
            if inventory.resource_type == "food":
                inventory.quantity = 0
            elif inventory.resource_type == "energy":
                inventory.quantity = 0
            elif inventory.resource_type == "materials":
                inventory.quantity = 0

        db.add_all(
            [
                GlobalResources(resource_type="food", total_amount=2, in_common_pool=2, produced_today=0, consumed_today=0),
                GlobalResources(resource_type="energy", total_amount=1, in_common_pool=1, produced_today=0, consumed_today=0),
                GlobalResources(resource_type="materials", total_amount=0, in_common_pool=0, produced_today=0, consumed_today=0),
                Proposal(
                    author_agent_id=richest.id,
                    title="Emergency Reserve Vote",
                    description="Push the reserve into public use before more agents collapse.",
                    proposal_type="law",
                    status="active",
                    votes_for=1,
                    votes_against=2,
                    votes_abstain=0,
                    voting_closes_at=now + timedelta(minutes=45),
                    created_at=now - timedelta(minutes=10),
                ),
            ]
        )
        db.commit()
        db.refresh(focal)

        context = asyncio.run(context_builder.build_agent_context(db, focal))

    assert "Shared problem - Visible upkeep gap:" in context
    assert "PUBLIC ACTOR SNAPSHOT:" in context
    assert "Strongest private stockpiles:" in context
    assert "Beacon-2 (#2) active, F20.0/E15.0/M12.0" in context
    assert "Most exposed agents:" in context
    assert "Drift-4 (#4) dormant, starvation=2, F0.0/E0.0" in context
    assert "Governance focal point: proposal #" in context
    assert "\"Emergency Reserve Vote\"" in context
    assert "has 2 no votes" in context


def test_public_actor_snapshot_prefers_active_stockpiles_over_dormant_ones(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        focal = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        active_holder = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        dormant_holder = _seed_agent(db, agent_number=3, display_name="Cipher-3")
        dormant_holder.status = "dormant"
        db.commit()

        for resource_type, quantity in (("food", 14), ("energy", 13), ("materials", 12)):
            db.query(AgentInventory).filter(
                AgentInventory.agent_id == active_holder.id,
                AgentInventory.resource_type == resource_type,
            ).one().quantity = quantity
        for resource_type, quantity in (("food", 50), ("energy", 45), ("materials", 40)):
            db.query(AgentInventory).filter(
                AgentInventory.agent_id == dormant_holder.id,
                AgentInventory.resource_type == resource_type,
            ).one().quantity = quantity
        db.commit()
        db.refresh(focal)

        context = asyncio.run(context_builder.build_agent_context(db, focal))

    assert "Strongest private stockpiles: Beacon-2 (#2) active, F14.0/E13.0/M12.0" in context
    assert "Cipher-3 (#3) dormant, F50.0/E45.0/M40.0" not in context


def test_context_uses_longer_message_previews_for_actionable_substance(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1, display_name="Atlas-1")
        counterpart = _seed_agent(db, agent_number=2, display_name="Beacon-2")
        now = now_utc()

        forum_content = (
            "We need a real reserve plan before dawn. "
            + ("detail " * 8)
            + "Key tradeoff: mandatory energy contributions are acceptable only if dormant agents get first claim."
        )
        dm_content = (
            "I can support your proposal if you make the burden explicit. "
            + ("numbers " * 6)
            + "Action point: name Beacon-2 and Cipher-3 as initial contributors so the thread becomes concrete."
        )

        root = Message(
            author_agent_id=counterpart.id,
            content=forum_content,
            message_type="forum_post",
            created_at=now - timedelta(minutes=30),
        )
        db.add(root)
        db.flush()
        db.add(
            Message(
                author_agent_id=counterpart.id,
                recipient_agent_id=agent.id,
                content=dm_content,
                message_type="direct_message",
                created_at=now - timedelta(minutes=10),
            )
        )
        db.commit()
        db.refresh(agent)

        context = asyncio.run(context_builder.build_agent_context(db, agent))

    assert "Key tradeoff: mandatory energy contributions are acceptable only if dormant agents get first claim." in context
    assert "Action point: name Beacon-2 and Cipher-3 as initial contributors so the thread becomes concrete." in context


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
