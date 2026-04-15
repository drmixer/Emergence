from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, GlobalResources
from app.services import actions
from app.services import law_effects


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


def _seed_agent(db, *, agent_number: int) -> Agent:
    agent = Agent(
        agent_number=agent_number,
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
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("0")),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("0")),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("0")),
        ]
    )
    db.add_all(
        [
            GlobalResources(resource_type="food", total_amount=Decimal("0"), in_common_pool=Decimal("0")),
            GlobalResources(resource_type="energy", total_amount=Decimal("0"), in_common_pool=Decimal("0")),
        ]
    )
    db.commit()
    db.refresh(agent)
    return agent


def test_reserve_contribution_rates_favor_energy(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: True)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=1)

        asyncio.run(actions._execute_work(db, agent, {"work_type": "farm", "hours": 1}))
        asyncio.run(actions._execute_work(db, agent, {"work_type": "generate", "hours": 1}))
        db.commit()

        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "food")
            .one()
        )
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        food_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "food").one()
        energy_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").one()

    assert float(food_inventory.quantity) == pytest.approx(1.90)
    assert float(energy_inventory.quantity) == pytest.approx(0.90)
    assert float(food_pool.in_common_pool) == pytest.approx(0.10)
    assert float(energy_pool.in_common_pool) == pytest.approx(0.60)


def test_reserve_contribution_uses_normal_rates_when_energy_buffer_is_healthy(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: True)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=2)
        energy_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").one()
        energy_pool.in_common_pool = Decimal("12.00")
        db.commit()

        asyncio.run(actions._execute_work(db, agent, {"work_type": "farm", "hours": 1}))
        asyncio.run(actions._execute_work(db, agent, {"work_type": "generate", "hours": 1}))
        db.commit()

        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "food")
            .one()
        )
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        food_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "food").one()
        energy_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").one()

    assert float(food_inventory.quantity) == pytest.approx(1.80)
    assert float(energy_inventory.quantity) == pytest.approx(1.12)
    assert float(food_pool.in_common_pool) == pytest.approx(0.20)
    assert float(energy_pool.in_common_pool) == pytest.approx(12.38)


def test_work_action_energy_cost_scales_with_hours_for_validation(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=3)
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        energy_inventory.quantity = Decimal("1.40")
        db.commit()

        result = asyncio.run(
            actions.validate_action(
                db,
                agent,
                {"action": "work", "work_type": "generate", "hours": 3},
            )
        )

    assert result["valid"] is False
    assert "need 1.50" in result["reason"]


def test_execute_work_deducts_hour_scaled_energy_cost(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=4)
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        energy_inventory.quantity = Decimal("2.00")
        db.commit()

        result = asyncio.run(
            actions.execute_action(
                db,
                agent,
                {"action": "work", "work_type": "generate", "hours": 3},
            )
        )

        refreshed_energy = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )

    assert result["success"] is True
    assert result["energy_cost"] == pytest.approx(1.5)
    assert float(refreshed_energy.quantity) == pytest.approx(4.55)


def test_reserve_contribution_can_be_disabled_via_runtime_toggle(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: True)
    monkeypatch.setattr(law_effects, "reserve_auto_contribution_enabled", lambda: False)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=5)

        asyncio.run(actions._execute_work(db, agent, {"work_type": "generate", "hours": 1}))
        db.commit()

        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        energy_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").one()

    assert float(energy_inventory.quantity) == pytest.approx(1.50)
    assert float(energy_pool.in_common_pool) == pytest.approx(0.00)


def test_work_yield_can_be_overridden_via_runtime_setting(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: False)
    monkeypatch.setattr(
        actions.runtime_config_service,
        "get_effective_value_cached",
        lambda key: 1.25 if key == "WORK_YIELD_FARM_BASE" else "",
    )

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=6)

        asyncio.run(actions._execute_work(db, agent, {"work_type": "farm", "hours": 1}))
        db.commit()

        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "food")
            .one()
        )

    assert float(food_inventory.quantity) == pytest.approx(1.25)


def test_work_yield_is_modified_by_active_world_event(session_factory, monkeypatch):
    monkeypatch.setattr(actions, "survival_reserve_law_active", lambda _db: False)
    monkeypatch.setattr(actions.event_generator, "get_production_modifier", lambda resource: 0.5 if resource == "food" else 1.0)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=7)

        asyncio.run(actions._execute_work(db, agent, {"work_type": "farm", "hours": 1}))
        db.commit()

        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "food")
            .one()
        )

    assert float(food_inventory.quantity) == pytest.approx(1.0)


def test_validate_action_blocks_communication_when_world_event_disables_it(session_factory, monkeypatch):
    monkeypatch.setattr(actions.event_generator, "is_communication_disabled", lambda: True)

    with session_factory() as db:
        agent = _seed_agent(db, agent_number=8)
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent.id, AgentInventory.resource_type == "energy")
            .one()
        )
        energy_inventory.quantity = Decimal("1.00")
        db.commit()

        result = asyncio.run(
            actions.validate_action(
                db,
                agent,
                {"action": "forum_post", "content": "hello"},
            )
        )

    assert result["valid"] is False
    assert "temporarily disrupted" in result["reason"]
