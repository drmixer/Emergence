from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.models.models import (
    Agent,
    AgentInventory,
    AgentLineage,
    AgentMemory,
    Law,
    Proposal,
    SeasonSnapshot,
    SimulationRun,
    Vote,
)
from app.services.season_transfer import (
    SURVIVOR_SNAPSHOT_TYPE_V1,
    export_season_snapshot,
    seed_next_season,
)


@pytest.fixture
def db_session():
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

    SimulationRun.__table__.create(bind=engine)
    Agent.__table__.create(bind=engine)
    AgentInventory.__table__.create(bind=engine)
    AgentMemory.__table__.create(bind=engine)
    Proposal.__table__.create(bind=engine)
    Vote.__table__.create(bind=engine)
    Law.__table__.create(bind=engine)
    SeasonSnapshot.__table__.create(bind=engine)
    AgentLineage.__table__.create(bind=engine)

    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _seed_parent_run(db_session, run_id: str = "real-parent-run") -> SimulationRun:
    row = SimulationRun(
        run_id=run_id,
        run_mode="real",
        protocol_version="protocol_v1",
        run_class="standard_72h",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _seed_agents(db_session, *, total: int = 10, active: set[int] | None = None) -> None:
    active_numbers = active or set()
    for number in range(1, total + 1):
        is_active = number in active_numbers
        agent = Agent(
            agent_number=number,
            display_name=f"Agent {number}",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active" if is_active else "dead",
            system_prompt=f"Prompt {number}",
            starvation_cycles=(0 if is_active else 3),
        )
        db_session.add(agent)
        db_session.flush()
        db_session.add_all(
            [
                AgentInventory(agent_id=agent.id, resource_type="food", quantity=Decimal("99")),
                AgentInventory(agent_id=agent.id, resource_type="energy", quantity=Decimal("88")),
                AgentInventory(agent_id=agent.id, resource_type="materials", quantity=Decimal("77")),
                AgentMemory(
                    agent_id=agent.id,
                    summary_text=f"memory-{number}",
                    last_checkpoint_number=number,
                    last_updated_at=datetime.now(timezone.utc),
                ),
            ]
        )
    db_session.commit()


def test_export_season_snapshot_persists_survivor_payload(db_session):
    _seed_parent_run(db_session, run_id="real-export-source")
    _seed_agents(db_session, total=8, active={1, 3, 5})

    result = export_season_snapshot(
        db_session,
        run_id="real-export-source",
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["snapshot_id"] is not None
    assert result["payload"]["survivor_count"] == 3
    assert [item["agent_number"] for item in result["payload"]["survivors"]] == [1, 3, 5]

    stored = db_session.query(SeasonSnapshot).filter_by(run_id="real-export-source").one()
    assert stored.snapshot_type == SURVIVOR_SNAPSHOT_TYPE_V1
    assert stored.payload_json["survivor_count"] == 3


def test_seed_next_season_dry_run_uses_snapshot_and_produces_deterministic_plan(db_session):
    _seed_parent_run(db_session, run_id="real-parent-for-dry-run")
    _seed_agents(db_session, total=10, active={2, 4, 6})

    db_session.add(
        SeasonSnapshot(
            run_id="real-parent-for-dry-run",
            snapshot_type=SURVIVOR_SNAPSHOT_TYPE_V1,
            payload_json={
                "survivors": [
                    {"agent_number": 2},
                    {"agent_number": 4},
                    {"agent_number": 6},
                ]
            },
        )
    )
    db_session.commit()

    result = seed_next_season(
        db_session,
        season_id="season-02",
        parent_run_id="real-parent-for-dry-run",
        transfer_policy_version="season_transfer_policy_v1",
        dry_run=True,
        target_agent_count=10,
    )

    assert result["dry_run"] is True
    assert result["snapshot_source"] == "season_snapshot"
    assert result["carryover_agent_numbers"] == [2, 4, 6]
    assert result["fresh_agent_numbers"] == [1, 3, 5, 7, 8, 9, 10]
    assert result["carryover_agent_count"] + result["fresh_agent_count"] == 10
    assert len(result["lineage_rows"]) == 10


def test_seed_next_season_confirmed_apply_normalizes_state_and_writes_lineage(db_session):
    _seed_parent_run(db_session, run_id="real-parent-for-apply")
    _seed_agents(db_session, total=10, active={1, 2, 3, 4})

    author = db_session.query(Agent).filter_by(agent_number=1).one()
    proposal = Proposal(
        author_agent_id=author.id,
        title="Active Proposal",
        description="desc",
        proposal_type="law",
        status="active",
        voting_closes_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.add(
        Vote(
            proposal_id=proposal.id,
            agent_id=author.id,
            vote="yes",
            reasoning="support",
        )
    )
    db_session.add(
        Law(
            proposal_id=proposal.id,
            title="Legacy Law",
            description="legacy",
            author_agent_id=author.id,
            active=True,
        )
    )
    db_session.add(
        SeasonSnapshot(
            run_id="real-parent-for-apply",
            snapshot_type=SURVIVOR_SNAPSHOT_TYPE_V1,
            payload_json={
                "survivors": [
                    {"agent_number": 1},
                    {"agent_number": 2},
                    {"agent_number": 3},
                    {"agent_number": 4},
                ]
            },
        )
    )
    db_session.commit()

    result = seed_next_season(
        db_session,
        season_id="season-03",
        parent_run_id="real-parent-for-apply",
        transfer_policy_version="season_transfer_policy_v1",
        carry_passed_laws=False,
        dry_run=False,
        confirm=True,
        target_agent_count=10,
    )

    assert result["dry_run"] is False
    assert result["carryover_agent_count"] == 4
    assert result["fresh_agent_count"] == 6
    assert result["votes_cleared"] == 1
    assert result["active_proposals_expired"] == 1
    assert result["laws_deactivated"] == 1

    assert db_session.query(Vote).count() == 0
    assert db_session.query(Proposal).filter_by(status="active").count() == 0
    assert db_session.query(Law).filter_by(active=True).count() == 0

    lineage_rows = db_session.query(AgentLineage).filter_by(season_id="season-03").all()
    assert len(lineage_rows) == 10
    assert len([row for row in lineage_rows if row.origin == "carryover"]) == 4
    assert len([row for row in lineage_rows if row.origin == "fresh"]) == 6

    carryover_agent = db_session.query(Agent).filter_by(agent_number=1).one()
    fresh_agent = db_session.query(Agent).filter_by(agent_number=10).one()
    assert carryover_agent.status == "active"
    assert fresh_agent.status == "active"
    assert fresh_agent.display_name is None

    carryover_memory = db_session.query(AgentMemory).filter_by(agent_id=carryover_agent.id).one()
    fresh_memory = db_session.query(AgentMemory).filter_by(agent_id=fresh_agent.id).one()
    assert carryover_memory.summary_text == "memory-1"
    assert fresh_memory.summary_text == ""
    assert fresh_memory.last_checkpoint_number == 0

    expected_food = Decimal(str(settings.STARTING_FOOD))
    expected_energy = Decimal(str(settings.STARTING_ENERGY))
    expected_materials = Decimal(str(settings.STARTING_MATERIALS))

    carryover_inventory = {
        row.resource_type: row.quantity
        for row in db_session.query(AgentInventory).filter_by(agent_id=carryover_agent.id).all()
    }
    fresh_inventory = {
        row.resource_type: row.quantity
        for row in db_session.query(AgentInventory).filter_by(agent_id=fresh_agent.id).all()
    }

    assert carryover_inventory["food"] == expected_food
    assert carryover_inventory["energy"] == expected_energy
    assert carryover_inventory["materials"] == expected_materials
    assert fresh_inventory["food"] == expected_food
    assert fresh_inventory["energy"] == expected_energy
    assert fresh_inventory["materials"] == expected_materials
