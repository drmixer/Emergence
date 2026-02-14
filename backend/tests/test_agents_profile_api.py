from __future__ import annotations

from datetime import timedelta
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, AgentLineage, Event, Message, Proposal, SimulationRun, Vote

agents_api = importlib.import_module("app.api.agents")
agents_router = agents_api.router


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
        AgentInventory.__table__,
        Message.__table__,
        Proposal.__table__,
        Vote.__table__,
        Event.__table__,
        SimulationRun.__table__,
        AgentLineage.__table__,
    ]
    for table in tables:
        table.create(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def _make_client(db_session):
    app = FastAPI()
    app.include_router(agents_router, prefix="/api/agents")
    app.dependency_overrides = {agents_api.get_db: lambda: db_session}
    return TestClient(app)


def test_agent_detail_includes_profile_stats_and_carryover_lineage():
    db = _build_db_session()
    now = now_utc()

    agent = Agent(
        agent_number=22,
        display_name="Nova-22",
        model_type="claude-sonnet-4",
        tier=1,
        personality_type="efficiency",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=5),
        last_active_at=now,
    )
    db.add(agent)
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=42),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=17),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=8),
            Event(agent_id=agent.id, event_type="work", description="did work"),
            Event(agent_id=agent.id, event_type="invalid_action", description="bad action"),
            Event(agent_id=agent.id, event_type="law_passed", description="passed law"),
            Message(author_agent_id=agent.id, content="hello", message_type="forum_post"),
            Message(author_agent_id=agent.id, content="reply", message_type="forum_reply"),
        ]
    )

    proposal = Proposal(
        author_agent_id=agent.id,
        title="p1",
        description="desc",
        proposal_type="law",
        status="active",
        voting_closes_at=now + timedelta(hours=2),
    )
    db.add(proposal)
    db.flush()
    db.add(Vote(proposal_id=proposal.id, agent_id=agent.id, vote="yes"))

    db.add(
        SimulationRun(
            run_id="real-s1-r2",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_01",
            season_number=1,
            started_at=now - timedelta(hours=4),
            ended_at=None,
        )
    )
    db.add(
        AgentLineage(
            season_id="season_01",
            parent_agent_number=22,
            child_agent_number=22,
            origin="carryover",
        )
    )
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/agents/22")

    assert response.status_code == 200
    body = response.json()
    stats = body["profile_stats"]
    assert stats["total_actions"] == 3
    assert stats["meaningful_actions"] == 1
    assert stats["invalid_actions"] == 1
    assert stats["invalid_action_rate"] == 0.3333
    assert stats["messages_authored"] == 2
    assert stats["proposals_created"] == 1
    assert stats["votes_cast"] == 1
    assert stats["laws_passed"] == 1
    assert stats["days_since_created"] >= 4.9

    lineage = body["lineage"]
    assert lineage["current_season_id"] == "season_01"
    assert lineage["lineage_season_id"] == "season_01"
    assert lineage["origin"] == "carryover"
    assert lineage["is_carryover"] is True
    assert lineage["is_fresh"] is False
    assert lineage["parent_agent_number"] == 22

    db.close()


def test_list_agents_includes_lineage_fields_for_current_season():
    db = _build_db_session()
    now = now_utc()

    agent_1 = Agent(
        agent_number=1,
        display_name="Alpha-01",
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
        display_name="Beta-02",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    db.add_all([agent_1, agent_2])
    db.flush()

    db.add(
        SimulationRun(
            run_id="real-s1-r3",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_01",
            season_number=1,
            started_at=now - timedelta(hours=3),
            ended_at=None,
        )
    )
    db.add_all(
        [
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

    with _make_client(db) as client:
        response = client.get("/api/agents")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    first = next(item for item in payload if int(item["agent_number"]) == 1)
    second = next(item for item in payload if int(item["agent_number"]) == 2)

    assert first["lineage_origin"] == "carryover"
    assert first["lineage_is_carryover"] is True
    assert first["lineage_is_fresh"] is False
    assert first["lineage_parent_agent_number"] == 1
    assert first["lineage_season_id"] == "season_01"

    assert second["lineage_origin"] == "fresh"
    assert second["lineage_is_carryover"] is False
    assert second["lineage_is_fresh"] is True
    assert second["lineage_parent_agent_number"] is None
    assert second["lineage_season_id"] == "season_01"

    db.close()


def test_agent_detail_lineage_defaults_when_missing():
    db = _build_db_session()
    now = now_utc()

    agent = Agent(
        agent_number=9,
        display_name="Cipher-09",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=1),
        last_active_at=now,
    )
    db.add(agent)
    db.flush()
    db.add(AgentInventory(agent_id=agent.id, resource_type="food", quantity=5))
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/agents/9")

    assert response.status_code == 200
    body = response.json()
    assert body["lineage"]["origin"] is None
    assert body["lineage"]["is_carryover"] is False
    assert body["lineage"]["is_fresh"] is False
    assert body["lineage"]["parent_agent_number"] is None
    assert body["profile_stats"]["total_actions"] == 0
    assert body["profile_stats"]["invalid_action_rate"] == 0.0

    db.close()
