from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import Agent, AgentInventory, Event, GlobalResources
from app.services import scheduler


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


def _seed_agent(
    db,
    *,
    agent_number: int,
    status: str,
    food: str,
    energy: str,
    starvation_cycles: int = 0,
) -> Agent:
    agent = Agent(
        agent_number=agent_number,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type="neutral",
        status=status,
        system_prompt="Test prompt",
        starvation_cycles=starvation_cycles,
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


def _seed_reserve(db, *, food: str, energy: str) -> None:
    db.add_all(
        [
            GlobalResources(resource_type="food", total_amount=Decimal(food), in_common_pool=Decimal(food)),
            GlobalResources(resource_type="energy", total_amount=Decimal(energy), in_common_pool=Decimal(energy)),
        ]
    )
    db.commit()


def _configure_reserve(monkeypatch, session_factory, *, runtime_values: dict[str, object] | None = None) -> None:
    values = dict(runtime_values or {})
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(scheduler, "_twitter_ready", lambda: False)
    monkeypatch.setattr(scheduler, "active_survival_reserve_laws", lambda _db: [object()])
    monkeypatch.setattr(scheduler.settings, "SIMULATION_MAX_AGENTS", 0, raising=False)
    monkeypatch.setattr(
        scheduler.runtime_config_service,
        "get_effective_value_cached",
        lambda key: values.get(key, ""),
    )


def _configure_no_reserve(monkeypatch, session_factory, *, runtime_values: dict[str, object] | None = None) -> None:
    values = dict(runtime_values or {})
    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(scheduler, "_twitter_ready", lambda: False)
    monkeypatch.setattr(scheduler, "active_survival_reserve_laws", lambda _db: [])
    monkeypatch.setattr(scheduler.settings, "SIMULATION_MAX_AGENTS", 0, raising=False)
    monkeypatch.setattr(
        scheduler.runtime_config_service,
        "get_effective_value_cached",
        lambda key: values.get(key, ""),
    )


def test_reserve_prioritizes_active_agents_before_dormant_maintenance(session_factory, monkeypatch):
    _configure_reserve(monkeypatch, session_factory)

    with session_factory() as db:
        active_agent = _seed_agent(
            db,
            agent_number=1,
            status="active",
            food="2.00",
            energy="0.10",
        )
        dormant_agent = _seed_agent(
            db,
            agent_number=2,
            status="dormant",
            food="0.10",
            energy="0.10",
            starvation_cycles=1,
        )
        _seed_reserve(db, food="0.20", energy="1.95")
        active_agent_id = active_agent.id
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 0
    assert result["became_dormant"] == 1
    assert result["dormant_stable"] == 1

    with session_factory() as db:
        refreshed_active = db.query(Agent).filter(Agent.id == active_agent_id).one()
        refreshed_dormant = db.query(Agent).filter(Agent.id == dormant_agent_id).one()
        reserve_aids = db.query(Event).filter(Event.event_type == "reserve_aid").all()

    assert refreshed_active.status == "dormant"
    assert refreshed_dormant.status == "dormant"
    assert refreshed_dormant.starvation_cycles == 1
    assert len(reserve_aids) == 1
    assert reserve_aids[0].agent_id == dormant_agent_id
    aid_meta = reserve_aids[0].event_metadata or {}
    assert aid_meta["status_before"] == "dormant"
    assert aid_meta["support_mode"] == "dormant_maintenance"
    assert aid_meta["aid_granted"] is True
    assert aid_meta["reserve_pool_energy_before"] == pytest.approx(1.95)
    assert aid_meta["reserve_pool_energy_after"] == pytest.approx(1.80)


def test_reserve_can_support_active_agents_when_runtime_override_enabled(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 0.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
        },
    )

    with session_factory() as db:
        active_agent = _seed_agent(
            db,
            agent_number=6,
            status="active",
            food="2.00",
            energy="0.10",
        )
        dormant_agent = _seed_agent(
            db,
            agent_number=7,
            status="dormant",
            food="0.10",
            energy="0.10",
            starvation_cycles=1,
        )
        _seed_reserve(db, food="0.20", energy="1.95")
        active_agent_id = active_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 1
    assert result["starving"] == 1

    with session_factory() as db:
        refreshed_active = db.query(Agent).filter(Agent.id == active_agent_id).one()
        reserve_aids = db.query(Event).filter(Event.event_type == "reserve_aid").all()

    assert refreshed_active.status == "active"
    assert len(reserve_aids) == 1
    aid_meta = reserve_aids[0].event_metadata or {}
    assert aid_meta["status_before"] == "active"
    assert aid_meta["support_mode"] == "active_threshold_aid"


def test_active_reserve_aid_uses_declared_threshold_not_general_upkeep_gap(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 25.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
        },
    )

    with session_factory() as db:
        active_agent = _seed_agent(
            db,
            agent_number=8,
            status="active",
            food="2.50",
            energy="2.50",
        )
        _seed_reserve(db, food="100.00", energy="100.00")
        active_agent_id = active_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 0
    assert result["became_dormant"] == 1

    with session_factory() as db:
        refreshed_active = db.query(Agent).filter(Agent.id == active_agent_id).one()
        reserve_aids = db.query(Event).filter(Event.event_type == "reserve_aid").all()

    assert refreshed_active.status == "dormant"
    assert reserve_aids == []


def test_active_reserve_aid_tops_up_below_threshold_and_preserves_pool_floor(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 25.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
        },
    )

    with session_factory() as db:
        active_agent = _seed_agent(
            db,
            agent_number=9,
            status="active",
            food="3.00",
            energy="1.90",
        )
        _seed_reserve(db, food="30.00", energy="27.00")
        active_agent_id = active_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 1
    assert result["became_dormant"] == 0

    with session_factory() as db:
        refreshed_active = db.query(Agent).filter(Agent.id == active_agent_id).one()
        reserve_aid = db.query(Event).filter(Event.event_type == "reserve_aid").one()
        energy_pool = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").one()

    assert refreshed_active.status == "active"
    assert float(energy_pool.in_common_pool) == pytest.approx(25.40)
    aid_meta = reserve_aid.event_metadata or {}
    assert aid_meta["support_mode"] == "active_threshold_aid"
    assert aid_meta["active_aid_trigger_energy"] == pytest.approx(2.0)
    assert aid_meta["active_aid_target_energy"] == pytest.approx(3.5)
    assert aid_meta["energy_deficit"] == pytest.approx(1.6)
    assert aid_meta["reserve_min_pool_remaining"] == pytest.approx(25.0)
    assert aid_meta["reserve_pool_floor_violation"] is False


def test_reserve_can_revive_dormant_agent_when_pool_covers_active_cycle(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={"SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": True},
    )

    with session_factory() as db:
        dormant_agent = _seed_agent(
            db,
            agent_number=3,
            status="dormant",
            food="0.10",
            energy="0.10",
            starvation_cycles=2,
        )
        _seed_reserve(db, food="2.00", energy="2.00")
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["revived"] == 1
    assert result["active_fed"] == 1

    with session_factory() as db:
        refreshed_agent = db.query(Agent).filter(Agent.id == dormant_agent_id).one()
        revive_event = db.query(Event).filter(Event.event_type == "agent_revived").one()
        starvation_warnings = db.query(Event).filter(Event.event_type == "starvation_warning").count()
        food_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == dormant_agent_id, AgentInventory.resource_type == "food")
            .one()
        )
        energy_inventory = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == dormant_agent_id, AgentInventory.resource_type == "energy")
            .one()
        )

    assert refreshed_agent.status == "active"
    assert refreshed_agent.starvation_cycles == 0
    assert revive_event.agent_id == dormant_agent_id
    assert starvation_warnings == 0
    assert float(food_inventory.quantity) == pytest.approx(0.0)
    assert float(energy_inventory.quantity) == pytest.approx(0.0)
    revive_meta = revive_event.event_metadata or {}
    reserve_decision = revive_meta["reserve_decision"]
    assert reserve_decision["status_before"] == "dormant"
    assert reserve_decision["support_mode"] == "active_revival"
    assert reserve_decision["aid_granted"] is True


def test_reserve_does_not_auto_revive_dormant_agent_when_disabled(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={"SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False},
    )

    with session_factory() as db:
        dormant_agent = _seed_agent(
            db,
            agent_number=4,
            status="dormant",
            food="0.10",
            energy="0.10",
            starvation_cycles=2,
        )
        _seed_reserve(db, food="2.00", energy="2.00")
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["revived"] == 0
    assert result["dormant_stable"] == 1
    assert result["active_fed"] == 0

    with session_factory() as db:
        refreshed_agent = db.query(Agent).filter(Agent.id == dormant_agent_id).one()
        reserve_aid = db.query(Event).filter(Event.event_type == "reserve_aid").one()
        revive_events = db.query(Event).filter(Event.event_type == "agent_revived").count()

    assert refreshed_agent.status == "dormant"
    assert refreshed_agent.starvation_cycles == 2
    assert reserve_aid.agent_id == dormant_agent_id
    assert revive_events == 0
    aid_meta = reserve_aid.event_metadata or {}
    assert aid_meta["status_before"] == "dormant"
    assert aid_meta["support_mode"] == "dormant_maintenance"
    assert aid_meta["aid_granted"] is True


def test_reserve_does_not_cover_dormant_maintenance_when_disabled(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={"SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False},
    )

    with session_factory() as db:
        dormant_agent = _seed_agent(
            db,
            agent_number=41,
            status="dormant",
            food="0.10",
            energy="0.10",
            starvation_cycles=2,
        )
        _seed_reserve(db, food="10.00", energy="10.00")
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["dormant_stable"] == 0
    assert result["starving"] == 1

    with session_factory() as db:
        refreshed_agent = db.query(Agent).filter(Agent.id == dormant_agent_id).one()
        reserve_aids = db.query(Event).filter(Event.event_type == "reserve_aid").all()
        warnings = db.query(Event).filter(Event.event_type == "starvation_warning").all()

    assert refreshed_agent.status == "dormant"
    assert refreshed_agent.starvation_cycles == 3
    assert reserve_aids == []
    assert len(warnings) == 1


def test_dormant_upkeep_warning_names_binding_resource(session_factory, monkeypatch):
    _configure_reserve(monkeypatch, session_factory)

    with session_factory() as db:
        dormant_agent = _seed_agent(
            db,
            agent_number=42,
            status="dormant",
            food="10.00",
            energy="0.10",
            starvation_cycles=1,
        )
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["starving"] == 1

    with session_factory() as db:
        warning = db.query(Event).filter(Event.event_type == "starvation_warning").one()
        refreshed_agent = db.query(Agent).filter(Agent.id == dormant_agent_id).one()

    assert refreshed_agent.status == "dormant"
    assert "cannot cover dormant energy upkeep" in warning.description
    assert "starving" not in warning.description.lower()
    assert warning.event_metadata["cause"] == "energy_upkeep_failure"
    assert warning.event_metadata["failure_label"] == "dormant energy upkeep failure"


def test_dormant_death_names_upkeep_failure_cause(session_factory, monkeypatch):
    _configure_reserve(monkeypatch, session_factory)

    with session_factory() as db:
        dormant_agent = _seed_agent(
            db,
            agent_number=43,
            status="dormant",
            food="10.00",
            energy="0.10",
            starvation_cycles=4,
        )
        dormant_agent_id = dormant_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["died"] == 1

    with session_factory() as db:
        death = db.query(Event).filter(Event.event_type == "agent_died").one()
        refreshed_agent = db.query(Agent).filter(Agent.id == dormant_agent_id).one()

    assert refreshed_agent.status == "dead"
    assert refreshed_agent.death_cause == "energy_upkeep_failure"
    assert "dormant energy upkeep failure" in death.description
    assert "from starvation" not in death.description.lower()
    assert death.event_metadata["cause"] == "energy_upkeep_failure"
    assert death.event_metadata["unpaid_upkeep_cycles"] == 5


def test_reserve_support_saves_smallest_active_deficit_first(session_factory, monkeypatch):
    _configure_reserve(
        monkeypatch,
        session_factory,
        runtime_values={
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 0.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
        },
    )

    with session_factory() as db:
        high_deficit_agent = _seed_agent(
            db,
            agent_number=1,
            status="active",
            food="0.10",
            energy="0.10",
        )
        low_deficit_agent = _seed_agent(
            db,
            agent_number=2,
            status="active",
            food="1.80",
            energy="1.80",
        )
        _seed_reserve(db, food="0.25", energy="0.25")
        high_deficit_agent_id = high_deficit_agent.id
        low_deficit_agent_id = low_deficit_agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 1
    assert result["became_dormant"] == 1

    with session_factory() as db:
        high_deficit = db.query(Agent).filter(Agent.id == high_deficit_agent_id).one()
        low_deficit = db.query(Agent).filter(Agent.id == low_deficit_agent_id).one()
        reserve_aids = db.query(Event).filter(Event.event_type == "reserve_aid").all()

    assert low_deficit.status == "active"
    assert high_deficit.status == "dormant"
    assert len(reserve_aids) == 1
    assert reserve_aids[0].agent_id == low_deficit_agent_id

    with session_factory() as db:
        shortfall = db.query(Event).filter(Event.event_type == "reserve_shortfall").one()

    shortfall_meta = shortfall.event_metadata or {}
    assert shortfall_meta["aid_granted"] is False
    assert shortfall_meta["status_before"] == "active"
    assert shortfall_meta["support_mode"] == "active_threshold_aid"
    assert shortfall_meta["reserve_pool_food_before"] == pytest.approx(0.05)
    assert shortfall_meta["reserve_pool_energy_before"] == pytest.approx(0.05)


def test_active_survival_cost_runtime_override_can_force_dormancy(session_factory, monkeypatch):
    _configure_no_reserve(
        monkeypatch,
        session_factory,
        runtime_values={
            "SURVIVAL_ACTIVE_FOOD_COST": 1.5,
            "SURVIVAL_ACTIVE_ENERGY_COST": 1.5,
        },
    )

    with session_factory() as db:
        agent = _seed_agent(
            db,
            agent_number=5,
            status="active",
            food="1.40",
            energy="1.40",
        )
        agent_id = agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["became_dormant"] == 1
    assert result["active_fed"] == 0

    with session_factory() as db:
        refreshed_agent = db.query(Agent).filter(Agent.id == agent_id).one()
        dormant_event = db.query(Event).filter(Event.event_type == "became_dormant").one()

    assert refreshed_agent.status == "dormant"
    assert dormant_event.agent_id == agent_id


def test_consumption_modifier_from_world_event_can_force_dormancy(session_factory, monkeypatch):
    _configure_no_reserve(monkeypatch, session_factory)
    monkeypatch.setattr(scheduler.event_generator, "get_consumption_modifier", lambda: 2.0)

    with session_factory() as db:
        agent = _seed_agent(
            db,
            agent_number=8,
            status="active",
            food="3.00",
            energy="3.00",
        )
        agent_id = agent.id

    result = asyncio.run(scheduler.process_daily_consumption())
    assert result["active_fed"] == 0
    assert result["became_dormant"] == 1

    with session_factory() as db:
        refreshed_agent = db.query(Agent).filter(Agent.id == agent_id).one()
        dormancy_event = db.query(Event).filter(Event.event_type == "became_dormant").one()

    assert refreshed_agent.status == "dormant"
    assert dormancy_event.event_metadata["reason"] == "lack of food"
