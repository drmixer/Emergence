from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.models import AgentLineage, SeasonSnapshot, SimulationRun


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SimulationRun.__table__.create(bind=engine)
    SeasonSnapshot.__table__.create(bind=engine)
    AgentLineage.__table__.create(bind=engine)

    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _new_run(run_id: str, **overrides) -> SimulationRun:
    payload = {
        "run_id": run_id,
        "run_mode": "real",
        "protocol_version": "protocol_v1",
        "started_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return SimulationRun(**payload)


def test_phase1_tables_round_trip_persistence(db_session):
    run = _new_run(
        "run-season-001",
        season_id="season-001",
        season_number=1,
        condition_name="baseline_v1",
        hypothesis_id="h-001",
        start_reason="pilot",
    )
    db_session.add(run)
    db_session.flush()

    snapshot = SeasonSnapshot(
        run_id=run.run_id,
        snapshot_type="survivors_v1",
        payload_json={"survivors": [1, 2, 3]},
    )
    lineage = AgentLineage(
        season_id="season-001",
        parent_agent_number=1,
        child_agent_number=1,
        origin="carryover",
    )

    db_session.add_all([snapshot, lineage])
    db_session.commit()

    stored_run = db_session.query(SimulationRun).filter_by(run_id="run-season-001").one()
    stored_snapshot = db_session.query(SeasonSnapshot).filter_by(run_id="run-season-001").one()
    stored_lineage = db_session.query(AgentLineage).filter_by(season_id="season-001").one()

    assert stored_run.carryover_agent_count == 0
    assert stored_run.fresh_agent_count == 0
    assert stored_run.protocol_deviation is False
    assert stored_snapshot.snapshot_type == "survivors_v1"
    assert stored_snapshot.payload_json["survivors"] == [1, 2, 3]
    assert stored_lineage.origin == "carryover"


def test_simulation_run_constraints_enforce_valid_counts_and_season_number(db_session):
    db_session.add(_new_run("run-invalid-season", season_id="season-x", season_number=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(_new_run("run-invalid-carryover", carryover_agent_count=-1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_season_snapshot_requires_existing_source_run(db_session):
    db_session.add(
        SeasonSnapshot(
            run_id="missing-run",
            snapshot_type="survivors_v1",
            payload_json={},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_agent_lineage_constraints_enforce_origin_and_uniqueness(db_session):
    db_session.add(
        AgentLineage(
            season_id="season-unique",
            parent_agent_number=None,
            child_agent_number=1,
            origin="fresh",
        )
    )
    db_session.commit()

    db_session.add(
        AgentLineage(
            season_id="season-unique",
            parent_agent_number=4,
            child_agent_number=1,
            origin="carryover",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentLineage(
            season_id="season-unique",
            parent_agent_number=4,
            child_agent_number=2,
            origin="invalid",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_phase1_indexes_declared_on_models():
    simulation_run_indexes = {index.name for index in SimulationRun.__table__.indexes}
    season_snapshot_indexes = {index.name for index in SeasonSnapshot.__table__.indexes}
    agent_lineage_indexes = {index.name for index in AgentLineage.__table__.indexes}

    assert {
        "ix_simulation_runs_run_id",
        "ix_simulation_runs_season_id",
        "ix_simulation_runs_season_number",
    }.issubset(simulation_run_indexes)
    assert {
        "ix_season_snapshots_run_id",
        "idx_season_snapshots_run_id_snapshot_type",
    }.issubset(season_snapshot_indexes)
    assert {
        "idx_agent_lineage_season_id_parent_agent_number",
        "idx_agent_lineage_season_id_child_agent_number",
    }.issubset(agent_lineage_indexes)
