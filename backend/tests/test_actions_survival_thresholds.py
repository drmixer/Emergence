from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, Event
from app.services import actions


def _session_factory():
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
    return sessionmaker(bind=engine, future=True), engine


def _seed_agent(db, *, agent_number: int, status: str, food: str, energy: str) -> Agent:
    agent = Agent(
        agent_number=agent_number,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status=status,
        system_prompt="Test prompt",
    )
    db.add(agent)
    db.flush()
    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal(food)),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal(energy)),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("0")),
        ]
    )
    db.commit()
    db.refresh(agent)
    return agent


def test_trade_revival_uses_configured_active_survival_threshold(monkeypatch):
    session_factory, engine = _session_factory()
    try:
        monkeypatch.setattr(
            actions.runtime_config_service,
            "get_effective_value_cached",
            lambda key: {
                "SURVIVAL_ACTIVE_FOOD_COST": 2.0,
                "SURVIVAL_ACTIVE_ENERGY_COST": 2.0,
            }.get(key, ""),
        )

        with session_factory() as db:
            sender = _seed_agent(db, agent_number=1, status="active", food="5.00", energy="5.00")
            recipient = _seed_agent(db, agent_number=2, status="dormant", food="1.00", energy="1.00")

            food_trade = asyncio.run(
                actions._execute_trade(
                    db,
                    sender,
                    {"recipient_agent_id": 2, "resource_type": "food", "amount": 1},
                )
            )
            energy_trade = asyncio.run(
                actions._execute_trade(
                    db,
                    sender,
                    {"recipient_agent_id": 2, "resource_type": "energy", "amount": 1},
                )
            )
            db.commit()

            refreshed = db.query(Agent).filter(Agent.id == recipient.id).one()
            revive_event = db.query(Event).filter(Event.event_type == "agent_revived").one()

        assert food_trade["success"] is True
        assert energy_trade["success"] is True
        assert refreshed.status == "active"
        assert refreshed.starvation_cycles == 0
        assert revive_event.agent_id == recipient.id
    finally:
        engine.dispose()
