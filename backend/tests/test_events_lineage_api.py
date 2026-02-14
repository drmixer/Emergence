from __future__ import annotations

from datetime import timedelta
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import now_utc
from app.models.models import Agent, AgentLineage, Event, SimulationRun

events_api = importlib.import_module("app.api.events")
events_router = events_api.router


def _build_db_session():
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
        Event.__table__,
        SimulationRun.__table__,
        AgentLineage.__table__,
    ]
    for table in tables:
        table.create(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def _make_client(db_session):
    app = FastAPI()
    app.include_router(events_router, prefix="/api/events")
    app.dependency_overrides = {events_api.get_db: lambda: db_session}
    return TestClient(app)


def test_list_events_includes_lineage_for_agent_events():
    db = _build_db_session()
    now = now_utc()

    agent = Agent(
        agent_number=7,
        display_name="Echo-07",
        model_type="claude-sonnet-4",
        tier=1,
        personality_type="efficiency",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=3),
        last_active_at=now,
    )
    db.add(agent)
    db.flush()

    db.add(
        SimulationRun(
            run_id="real-s1-r8",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_08",
            season_number=8,
            started_at=now - timedelta(hours=5),
            ended_at=None,
        )
    )
    db.add(
        AgentLineage(
            season_id="season_08",
            parent_agent_number=7,
            child_agent_number=7,
            origin="carryover",
        )
    )
    db.add(Event(agent_id=agent.id, event_type="trade", description="trade happened"))
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/events?limit=5")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    first = rows[0]
    assert first["agent_id"] == int(agent.id)
    assert first["agent_number"] == 7
    assert first["lineage_origin"] == "carryover"
    assert first["lineage_is_carryover"] is True
    assert first["lineage_is_fresh"] is False
    assert first["lineage_parent_agent_number"] == 7
    assert first["lineage_season_id"] == "season_08"

    db.close()


def test_get_event_with_no_agent_returns_default_lineage_fields():
    db = _build_db_session()
    db.add(Event(agent_id=None, event_type="world_event", description="a world event"))
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/events/1")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] is None
    assert body["agent_number"] is None
    assert body["lineage_origin"] is None
    assert body["lineage_is_carryover"] is False
    assert body["lineage_is_fresh"] is False
    assert body["lineage_parent_agent_number"] is None
    assert body["lineage_season_id"] is None

    db.close()
