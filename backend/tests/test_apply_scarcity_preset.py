from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, GlobalResources
from scripts import apply_scarcity_preset


@pytest.fixture
def session_factory(monkeypatch):
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
    monkeypatch.setattr(apply_scarcity_preset, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


def test_apply_resource_targets_resets_agent_survival_state(session_factory):
    with session_factory() as db:
        agent = Agent(
            agent_number=1,
            model_type="llama-3.1-8b",
            tier=1,
            personality_type="neutral",
            status="dormant",
            system_prompt="Test prompt",
            starvation_cycles=3,
            death_cause="starvation",
            exiled=True,
        )
        db.add(agent)
        db.flush()
        db.add_all(
            [
                AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("3")),
                AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("0")),
                AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("9")),
            ]
        )
        db.add_all(
            [
                GlobalResources(resource_type="food", total_amount=Decimal("10"), in_common_pool=Decimal("10")),
                GlobalResources(resource_type="energy", total_amount=Decimal("10"), in_common_pool=Decimal("10")),
                GlobalResources(resource_type="materials", total_amount=Decimal("10"), in_common_pool=Decimal("10")),
            ]
        )
        db.commit()
        agent_id = agent.id

    result = apply_scarcity_preset._apply_resource_targets(
        agent_targets={"food": 24.0, "energy": 18.0, "materials": 20.0},
        pool_targets={"food": 550.0, "energy": 200.0, "materials": 500.0},
    )

    assert result["agent_state_reset"] is True

    with session_factory() as db:
        refreshed = db.query(Agent).filter(Agent.id == agent_id).one()
        inventories = {
            row.resource_type: float(row.quantity)
            for row in db.query(AgentInventory).filter(AgentInventory.agent_id == agent_id).all()
        }
        globals_rows = {
            row.resource_type: float(row.in_common_pool)
            for row in db.query(GlobalResources).all()
        }

    assert refreshed.status == "active"
    assert refreshed.starvation_cycles == 0
    assert refreshed.death_cause is None
    assert refreshed.exiled is False
    assert inventories == {"food": 24.0, "energy": 18.0, "materials": 20.0}
    assert globals_rows == {"food": 550.0, "energy": 200.0, "materials": 500.0}
