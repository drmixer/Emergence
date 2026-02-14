from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, AgentInventory, AgentLineage, Event, Message, Proposal, SimulationRun, Vote
from app.services import leaderboards


def _build_session():
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

    tables = [
        Agent.__table__,
        AgentInventory.__table__,
        Event.__table__,
        Message.__table__,
        Proposal.__table__,
        Vote.__table__,
        SimulationRun.__table__,
        AgentLineage.__table__,
    ]
    for table in tables:
        table.create(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def test_leaderboards_include_lineage_and_identity_fields(monkeypatch):
    db = _build_session()
    now = datetime.utcnow()

    agent_1 = Agent(
        agent_number=1,
        display_name="Tensor-01",
        model_type="claude-sonnet-4",
        tier=1,
        personality_type="efficiency",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    agent_2 = Agent(
        agent_number=2,
        display_name="Vector-02",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="equality",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    db.add_all([agent_1, agent_2])
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=agent_1.id, resource_type="food", quantity=40),
            AgentInventory(agent_id=agent_1.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=agent_1.id, resource_type="materials", quantity=10),
            AgentInventory(agent_id=agent_2.id, resource_type="food", quantity=10),
            AgentInventory(agent_id=agent_2.id, resource_type="energy", quantity=10),
            AgentInventory(agent_id=agent_2.id, resource_type="materials", quantity=5),
            Event(agent_id=agent_1.id, event_type="work", description="work-1", created_at=now - timedelta(hours=1)),
            Event(agent_id=agent_1.id, event_type="trade", description="trade-1", created_at=now - timedelta(hours=1)),
            Event(agent_id=agent_2.id, event_type="work", description="work-2", created_at=now - timedelta(hours=2)),
            Proposal(
                author_agent_id=agent_1.id,
                title="p1",
                description="desc",
                proposal_type="law",
                status="active",
                voting_closes_at=now + timedelta(hours=4),
            ),
            SimulationRun(
                run_id="real-season-1",
                run_mode="real",
                protocol_version="protocol_v1",
                run_class="standard_72h",
                season_id="season_01",
                season_number=1,
                started_at=now - timedelta(hours=4),
                ended_at=None,
            ),
            AgentLineage(
                season_id="season_01",
                parent_agent_number=1,
                child_agent_number=1,
                origin="carryover",
            ),
            AgentLineage(
                season_id="season_01",
                parent_agent_number=None,
                child_agent_number=2,
                origin="fresh",
            ),
        ]
    )
    db.commit()

    monkeypatch.setattr(leaderboards, "SessionLocal", lambda: db)
    payload = leaderboards.get_all_leaderboards()

    wealth = payload.get("wealth") or []
    assert wealth
    first = wealth[0]
    assert first["agent_number"] == 1
    assert first["model_type"] == "claude-sonnet-4"
    assert first["personality_type"] == "efficiency"
    assert first["status"] == "active"
    assert first["lineage_origin"] == "carryover"
    assert first["lineage_is_carryover"] is True
    assert first["lineage_is_fresh"] is False
    assert first["lineage_parent_agent_number"] == 1
    assert first["lineage_season_id"] == "season_01"

    activity = payload.get("activity") or []
    assert activity
    second = next(item for item in activity if int(item["agent_number"]) == 2)
    assert second["lineage_origin"] == "fresh"
    assert second["lineage_is_fresh"] is True
    assert second["lineage_is_carryover"] is False

    db.close()
