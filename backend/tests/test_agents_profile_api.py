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
from app.services.live_run_scope import LiveRunWindow

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

    counterpart = Agent(
        agent_number=7,
        display_name="Beacon-07",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="stability",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=3),
        last_active_at=now,
    )
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
    db.add_all([counterpart, agent])
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=counterpart.id, resource_type="food", quantity=12),
            AgentInventory(agent_id=counterpart.id, resource_type="energy", quantity=11),
            AgentInventory(agent_id=counterpart.id, resource_type="materials", quantity=6),
            AgentInventory(agent_id=agent.id, resource_type="food", quantity=42),
            AgentInventory(agent_id=agent.id, resource_type="energy", quantity=17),
            AgentInventory(agent_id=agent.id, resource_type="materials", quantity=8),
            Event(agent_id=agent.id, event_type="work", description="did work"),
            Event(agent_id=agent.id, event_type="invalid_action", description="bad action"),
            Event(agent_id=agent.id, event_type="law_passed", description="passed law"),
            Event(
                agent_id=agent.id,
                event_type="trade",
                description="sent emergency food support",
                event_metadata={"action": {"recipient_agent_id": 7}},
            ),
            Message(author_agent_id=agent.id, content="hello", message_type="forum_post"),
            Message(author_agent_id=agent.id, content="reply", message_type="forum_reply"),
            Message(author_agent_id=agent.id, recipient_agent_id=counterpart.id, content="coordination ping", message_type="direct_message"),
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
    assert stats["total_actions"] == 4
    assert stats["meaningful_actions"] == 2
    assert stats["invalid_actions"] == 1
    assert stats["invalid_action_rate"] == 0.25
    assert stats["messages_authored"] == 3
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

    legibility = body["legibility"]
    assert legibility["archetype"]["title"] == "Institution Builder"
    assert legibility["danger"]["level"] == "stable"
    assert legibility["relationships"]["allies"][0]["agent_number"] == 7
    assert legibility["relationships"]["ally_buckets"]["trade_support"]["agent_number"] == 7

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
    db.add_all(
        [
            AgentInventory(agent_id=agent_1.id, resource_type="food", quantity=8),
            AgentInventory(agent_id=agent_1.id, resource_type="energy", quantity=8),
            AgentInventory(agent_id=agent_2.id, resource_type="food", quantity=0),
            AgentInventory(agent_id=agent_2.id, resource_type="energy", quantity=0),
        ]
    )

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
        response = client.get("/api/agents?scope=all")

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
    assert first["legibility"]["danger"]["level"] == "stable"


def test_list_agents_hides_weak_relationships_and_avoids_defaulting_everyone_to_producer():
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

    db.add_all(
        [
            AgentInventory(agent_id=agent_1.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=agent_1.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=agent_2.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=agent_2.id, resource_type="energy", quantity=20),
            Event(agent_id=agent_1.id, event_type="work", description="worked once"),
        ]
    )

    proposal = Proposal(
        author_agent_id=agent_2.id,
        title="p1",
        description="desc",
        proposal_type="law",
        status="active",
        voting_closes_at=now + timedelta(hours=2),
    )
    db.add(proposal)
    db.flush()
    db.add(Vote(proposal_id=proposal.id, agent_id=agent_1.id, vote="yes"))

    db.add(
        SimulationRun(
            run_id="real-s1-r4",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_01",
            season_number=1,
            started_at=now - timedelta(hours=3),
            ended_at=None,
        )
    )
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/agents?scope=all")

    assert response.status_code == 200
    payload = response.json()
    agent_1_payload = next(item for item in payload if int(item["agent_number"]) == 1)

    assert agent_1_payload["legibility"]["relationships"]["allies"] == []
    assert agent_1_payload["legibility"]["archetype"]["title"] == "Efficiency Strategist"
    assert "efficiency-oriented starting lens" in agent_1_payload["legibility"]["archetype"]["summary"]

    db.close()


def test_list_agents_hides_support_only_vote_alignment_until_signal_is_strong():
    db = _build_db_session()
    now = now_utc()

    voter = Agent(
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
    author = Agent(
        agent_number=42,
        display_name="Paradox-42",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    db.add_all([voter, author])
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=voter.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=voter.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=author.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=author.id, resource_type="energy", quantity=20),
        ]
    )

    proposals = []
    for idx in range(4):
        proposal = Proposal(
            author_agent_id=author.id,
            title=f"proposal-{idx}",
            description="desc",
            proposal_type="law",
            status="active",
            voting_closes_at=now + timedelta(hours=2),
        )
        proposals.append(proposal)
        db.add(proposal)
    db.flush()

    for proposal in proposals:
        db.add(Vote(proposal_id=proposal.id, agent_id=voter.id, vote="yes"))

    db.add(
        SimulationRun(
            run_id="real-s1-r5",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_01",
            season_number=1,
            started_at=now - timedelta(hours=3),
            ended_at=None,
        )
    )
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/agents?scope=all")

    assert response.status_code == 200
    payload = response.json()
    voter_payload = next(item for item in payload if int(item["agent_number"]) == 1)

    assert voter_payload["legibility"]["relationships"]["allies"] == []
    assert voter_payload["legibility"]["relationships"]["ally_buckets"]["voting_alignment"] is None

    db.close()


def test_list_agents_prefers_trade_or_collaboration_over_vote_only_alignment():
    db = _build_db_session()
    now = now_utc()

    focal = Agent(
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
    vote_author = Agent(
        agent_number=42,
        display_name="Paradox-42",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    trade_partner = Agent(
        agent_number=7,
        display_name="Beacon-07",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="stability",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=2),
        last_active_at=now,
    )
    db.add_all([focal, vote_author, trade_partner])
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=focal.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=focal.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=vote_author.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=vote_author.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=trade_partner.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=trade_partner.id, resource_type="energy", quantity=20),
            Event(
                agent_id=focal.id,
                event_type="trade",
                description="shared supplies",
                event_metadata={"action": {"recipient_agent_id": 7}},
            ),
        ]
    )

    proposals = []
    for idx in range(5):
        proposal = Proposal(
            author_agent_id=vote_author.id,
            title=f"proposal-{idx}",
            description="desc",
            proposal_type="law",
            status="active",
            voting_closes_at=now + timedelta(hours=2),
        )
        proposals.append(proposal)
        db.add(proposal)
    db.flush()

    for proposal in proposals:
        db.add(Vote(proposal_id=proposal.id, agent_id=focal.id, vote="yes"))

    db.add(
        SimulationRun(
            run_id="real-s1-r6",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            season_id="season_01",
            season_number=1,
            started_at=now - timedelta(hours=3),
            ended_at=None,
        )
    )
    db.commit()

    with _make_client(db) as client:
        response = client.get("/api/agents?scope=all")

    assert response.status_code == 200
    payload = response.json()
    focal_payload = next(item for item in payload if int(item["agent_number"]) == 1)
    allies = focal_payload["legibility"]["relationships"]["allies"]

    assert allies[0]["agent_number"] == 7
    assert allies[0]["relationship"] == "Trade partner"
    assert allies[1]["agent_number"] == 42
    assert allies[1]["relationship"] == "Voting alignment"
    assert focal_payload["legibility"]["relationships"]["ally_buckets"]["trade_support"]["agent_number"] == 7
    assert focal_payload["legibility"]["relationships"]["ally_buckets"]["voting_alignment"]["agent_number"] == 42

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
    assert body["legibility"]["archetype"]["title"] == "Survivor"

    db.close()


def test_agent_detail_relationships_are_scoped_to_active_run_window(monkeypatch):
    db = _build_db_session()
    now = now_utc()
    run_start = now - timedelta(hours=2)

    focal = Agent(
        agent_number=10,
        display_name="Syntax-10",
        model_type="claude-sonnet-4",
        tier=1,
        personality_type="efficiency",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=3),
        last_active_at=now,
    )
    old_counterpart = Agent(
        agent_number=35,
        display_name="Tempo-35",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="neutral",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=3),
        last_active_at=now,
    )
    current_counterpart = Agent(
        agent_number=7,
        display_name="Beacon-07",
        model_type="gpt-4o-mini",
        tier=2,
        personality_type="stability",
        status="active",
        system_prompt="test",
        created_at=now - timedelta(days=3),
        last_active_at=now,
    )
    db.add_all([focal, old_counterpart, current_counterpart])
    db.flush()

    db.add_all(
        [
            AgentInventory(agent_id=focal.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=focal.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=old_counterpart.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=old_counterpart.id, resource_type="energy", quantity=20),
            AgentInventory(agent_id=current_counterpart.id, resource_type="food", quantity=20),
            AgentInventory(agent_id=current_counterpart.id, resource_type="energy", quantity=20),
        ]
    )

    for idx in range(4):
        db.add(
            Message(
                author_agent_id=focal.id,
                recipient_agent_id=old_counterpart.id,
                content=f"old coordination ping {idx}",
                message_type="direct_message",
                created_at=run_start - timedelta(minutes=30 + idx),
            )
        )

    db.add(
        Message(
            author_agent_id=focal.id,
            recipient_agent_id=current_counterpart.id,
            content="current coordination ping",
            message_type="direct_message",
            created_at=run_start + timedelta(minutes=10),
        )
    )
    db.add(
        Event(
            agent_id=focal.id,
            event_type="trade",
            description="shared supplies this run",
            event_metadata={"action": {"recipient_agent_id": 7}},
            created_at=run_start + timedelta(minutes=20),
        )
    )
    db.add(
        SimulationRun(
            run_id="real-run-current",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="special_exploratory",
            season_id="season_01",
            season_number=1,
            started_at=run_start,
            ended_at=None,
        )
    )
    db.commit()

    monkeypatch.setattr(
        agents_api,
        "get_live_run_window",
        lambda _db: LiveRunWindow(run_id="real-run-current", started_at=run_start, ended_at=None),
    )

    with _make_client(db) as client:
        response = client.get("/api/agents/10")

    assert response.status_code == 200
    body = response.json()
    relationships = body["legibility"]["relationships"]
    assert relationships["allies"][0]["agent_number"] == 7
    assert "1 trade" in relationships["allies"][0]["evidence"]
    assert "1 direct message" in relationships["allies"][0]["evidence"]
    assert relationships["ally_buckets"]["trade_support"]["agent_number"] == 7
    assert all(item["agent_number"] != 35 for item in relationships["allies"])

    db.close()
