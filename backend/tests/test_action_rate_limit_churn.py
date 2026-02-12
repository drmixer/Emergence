from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.time import now_utc
from app.models.models import Agent, AgentAction, AgentInventory, Event
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


def _seed_active_agent(db, *, agent_number: int = 1) -> Agent:
    now = now_utc()
    agent = Agent(
        agent_number=agent_number,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="Test prompt",
        current_intent={"strategy": "conserve_energy", "checkpoint_number": 1},
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


def test_rate_limit_backoff_suppresses_consecutive_invalid_actions(monkeypatch, session_factory):
    with session_factory() as db:
        agent = _seed_active_agent(db)
        db.add(
            AgentAction(
                agent_id=agent.id,
                action_type="idle",
                created_at=now_utc() - timedelta(minutes=5),
            )
        )
        db.commit()
        agent_id = agent.id

    monkeypatch.setattr(agent_loop, "SessionLocal", session_factory)
    monkeypatch.setattr(agent_loop.settings, "MAX_ACTIONS_PER_HOUR", 1, raising=False)
    monkeypatch.setattr(
        agent_loop.settings,
        "ACTION_RATE_LIMIT_COOLDOWN_BUFFER_SECONDS",
        5,
        raising=False,
    )
    monkeypatch.setattr(
        agent_loop.runtime_config_service,
        "get_effective_value_cached",
        lambda _key: "",
    )
    monkeypatch.setattr(
        agent_loop.routine_executor,
        "build_action",
        lambda _db, _agent: {"action": "idle"},
    )

    processor = agent_loop.AgentProcessor()

    asyncio.run(processor._process_agent_turn(agent_id))
    with session_factory() as db:
        invalid_count_after_first = db.query(Event).filter(Event.event_type == "invalid_action").count()
    assert invalid_count_after_first == 1
    assert agent_id in processor._rate_limit_backoff_until

    asyncio.run(processor._process_agent_turn(agent_id))
    with session_factory() as db:
        invalid_count_after_second = db.query(Event).filter(Event.event_type == "invalid_action").count()
    assert invalid_count_after_second == 1


def test_context_includes_action_budget_remaining_and_reset(session_factory, monkeypatch):
    monkeypatch.setattr(context_builder.settings, "MAX_ACTIONS_PER_HOUR", 3, raising=False)
    monkeypatch.setattr(context_builder.settings, "PERCEPTION_LAG_SECONDS", 0, raising=False)

    with session_factory() as db:
        agent = _seed_active_agent(db, agent_number=2)
        db.add_all(
            [
                AgentAction(
                    agent_id=agent.id,
                    action_type="idle",
                    created_at=now_utc() - timedelta(minutes=40),
                ),
                AgentAction(
                    agent_id=agent.id,
                    action_type="work",
                    created_at=now_utc() - timedelta(minutes=10),
                ),
            ]
        )
        db.commit()
        db.refresh(agent)

        context = asyncio.run(context_builder.build_agent_context(db, agent))

    assert "ACTION BUDGET (rolling 60 minutes):" in context
    assert "- Actions used this hour: 2/3" in context
    assert "- Remaining actions this hour: 1" in context
    assert "- Next action slot reset (UTC):" in context
