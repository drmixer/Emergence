from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, GlobalResources
from app.services import events_generator


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


def _seed_agent(db, *, agent_number: int, food: str, energy: str, status: str = "active") -> Agent:
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


def test_world_event_generation_enabled_defaults_true(monkeypatch):
    monkeypatch.setattr(
        events_generator.runtime_config_service,
        "get_effective_value_cached",
        lambda key: None,
    )

    assert events_generator.world_event_generation_enabled() is True


def test_world_event_generation_enabled_parses_false(monkeypatch):
    monkeypatch.setattr(
        events_generator.runtime_config_service,
        "get_effective_value_cached",
        lambda key: "false" if key == "WORLD_EVENT_GENERATION_ENABLED" else None,
    )

    assert events_generator.world_event_generation_enabled() is False


def test_apply_event_destroy_percentage_reduces_food_stores(session_factory, monkeypatch):
    monkeypatch.setattr(events_generator, "SessionLocal", session_factory)
    generator = events_generator.EventGenerator()

    with session_factory() as db:
        _seed_agent(db, agent_number=1, food="10.00", energy="5.00")
        db.add(
            GlobalResources(
                resource_type="food",
                total_amount=Decimal("100.00"),
                in_common_pool=Decimal("20.00"),
            )
        )
        db.commit()

    asyncio.run(
        generator.apply_event(
            {
                "id": "blight",
                "name": "Crop Blight",
                "message": "blight",
                "effect": {"resource": "food", "destroy_percentage": 0.20},
            }
        )
    )

    with session_factory() as db:
        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.resource_type == "food")
            .one()
        )
        food_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "food").one()

    assert float(food_inventory.quantity) == pytest.approx(8.0)
    assert float(food_pool.in_common_pool) == pytest.approx(16.0)
    assert float(food_pool.total_amount) == pytest.approx(96.0)


def test_apply_event_reduce_all_agents_hits_energy_inventories(session_factory, monkeypatch):
    monkeypatch.setattr(events_generator, "SessionLocal", session_factory)
    generator = events_generator.EventGenerator()

    with session_factory() as db:
        _seed_agent(db, agent_number=1, food="5.00", energy="3.00")
        _seed_agent(db, agent_number=2, food="5.00", energy="1.00")

    asyncio.run(
        generator.apply_event(
            {
                "id": "energy_shortage",
                "name": "Energy Grid Failure",
                "message": "grid failure",
                "effect": {"resource": "energy", "reduce_all_agents": 2},
            }
        )
    )

    with session_factory() as db:
        energy_rows = (
            db.query(AgentInventory)
            .filter(AgentInventory.resource_type == "energy")
            .order_by(AgentInventory.agent_id.asc())
            .all()
        )

    assert [float(row.quantity) for row in energy_rows] == pytest.approx([1.0, 0.0])


def test_get_active_effects_rehydrates_from_db(session_factory, monkeypatch):
    monkeypatch.setattr(events_generator, "SessionLocal", session_factory)
    generator = events_generator.EventGenerator()

    asyncio.run(
        generator.apply_event(
            {
                "id": "drought",
                "name": "Drought",
                "message": "drought",
                "effect": {"resource": "food", "production_modifier": 0.5, "duration_hours": 24},
            }
        )
    )

    generator.active_effects = []
    hydrated = generator.get_active_effects()

    assert len(hydrated) == 1
    assert hydrated[0].event_id == "drought"
    assert hydrated[0].effect["production_modifier"] == 0.5
