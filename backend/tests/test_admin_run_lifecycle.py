from __future__ import annotations

from datetime import date
import importlib
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import now_utc
from app.models.models import Agent, Law, Proposal, SimulationRun

admin_api = importlib.import_module("app.api.admin")


class _RuntimeConfigStub:
    def __init__(self):
        self.effective = {
            "SIMULATION_RUN_MODE": "test",
            "SIMULATION_RUN_ID": "",
            "SIMULATION_CONDITION_NAME": "",
            "SIMULATION_SEASON_NUMBER": 0,
            "SIMULATION_ACTIVE": True,
            "SIMULATION_PAUSED": False,
        }

    def update_settings(self, db, updates, *, changed_by, reason=None):
        _ = changed_by
        _ = reason
        applied = {}
        for key, value in updates.items():
            if self.effective.get(key) != value:
                applied[key] = value
            self.effective[key] = value
        db.commit()
        return {"applied": applied, "effective": dict(self.effective)}

    def get_effective(self, db):
        _ = db
        return dict(self.effective)


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

    Agent.__table__.create(bind=engine)
    Proposal.__table__.create(bind=engine)
    Law.__table__.create(bind=engine)
    SimulationRun.__table__.create(bind=engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()


def _make_admin_client(
    db_session,
    monkeypatch,
    *,
    actor_id: str = "ops-phase2",
    client_ip: str = "127.0.0.1",
) -> tuple[TestClient, _RuntimeConfigStub]:
    runtime_stub = _RuntimeConfigStub()
    monkeypatch.setattr(admin_api.settings, "ADMIN_ENABLED", True, raising=False)
    monkeypatch.setattr(admin_api.settings, "ADMIN_WRITE_ENABLED", True, raising=False)
    monkeypatch.setattr(admin_api.settings, "ENVIRONMENT", "development", raising=False)
    monkeypatch.setattr(admin_api.settings, "ADMIN_IP_ALLOWLIST", "", raising=False)
    monkeypatch.setattr(admin_api.runtime_config_service, "update_settings", runtime_stub.update_settings)
    monkeypatch.setattr(admin_api.runtime_config_service, "get_effective", runtime_stub.get_effective)
    monkeypatch.setattr(
        admin_api,
        "maybe_generate_run_closeout_bundle",
        lambda *, run_id, actor_id, condition_name, season_number: {
            "generated_for": run_id,
            "actor_id": actor_id,
            "condition_name": condition_name,
            "season_number": season_number,
        },
    )

    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/admin")
    app.dependency_overrides[admin_api.get_db] = lambda: db_session
    app.dependency_overrides[admin_api.require_admin_auth] = lambda: admin_api.AdminActor(
        actor_id=actor_id,
        client_ip=client_ip,
    )
    return TestClient(app), runtime_stub


def _stub_budget(monkeypatch):
    monkeypatch.setattr(
        admin_api.usage_budget,
        "get_snapshot",
        lambda: SimpleNamespace(
            day_key=date(2026, 2, 11),
            calls_total=0,
            calls_openrouter_free=0,
            calls_gemini=0,
            estimated_cost_usd=0.0,
        ),
    )


def _seed_author(db_session, *, agent_number: int = 1) -> Agent:
    author = Agent(
        agent_number=agent_number,
        display_name=f"Agent #{agent_number}",
        model_type="or_gpt_oss_20b_free",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="{}",
    )
    db_session.add(author)
    db_session.commit()
    return author


def test_run_start_creates_simulation_row_with_defaults_and_warns(caplog, db_session, monkeypatch):
    caplog.set_level(logging.WARNING, logger=admin_api.__name__)
    client, runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={"mode": "real", "run_id": "real-phase2-defaults"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "real-phase2-defaults"
    assert body["mode"] == "real"
    assert body["condition_name"] is None
    assert body["season_number"] is None

    row = db_session.query(SimulationRun).filter_by(run_id="real-phase2-defaults").one()
    assert row.protocol_version == "protocol_v1"
    assert row.run_class == "standard_72h"
    assert row.condition_name is None
    assert row.season_number is None
    assert row.started_at is not None
    assert row.ended_at is None

    assert runtime_stub.effective["SIMULATION_RUN_ID"] == "real-phase2-defaults"
    assert runtime_stub.effective["SIMULATION_RUN_MODE"] == "real"
    assert runtime_stub.effective["SIMULATION_PAUSED"] is False
    assert any("without research metadata" in record.message for record in caplog.records)


def test_run_start_and_stop_persist_research_metadata_and_end_reason(db_session, monkeypatch):
    parent_row = SimulationRun(
        run_id="real-parent-run",
        run_mode="real",
        protocol_version="protocol_v1",
        run_class="standard_72h",
        started_at=now_utc(),
    )
    mirror_row = SimulationRun(
        run_id="real-mirror-run",
        run_mode="real",
        protocol_version="protocol_v1",
        run_class="standard_72h",
        started_at=now_utc(),
    )
    db_session.add(parent_row)
    db_session.add(mirror_row)
    db_session.commit()

    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)
    start_payload = {
        "mode": "real",
        "run_id": "real-child-run",
        "protocol_version": "protocol_v2",
        "condition_name": "carryover_v1",
        "hypothesis_id": "hypothesis_001",
        "season_id": "season_02",
        "season_number": 2,
        "parent_run_id": "real-parent-run",
        "mirror_control_run_id": "real-mirror-run",
        "transfer_policy_version": "season_transfer_policy_v1",
        "epoch_id": "epoch_01",
        "run_class": "deep_96h",
        "reason": "phase2_start",
    }

    with client:
        start_response = client.post("/api/admin/control/run/start", json=start_payload)
        stop_response = client.post(
            "/api/admin/control/run/stop",
            json={"reason": "phase2_stop"},
        )

    assert start_response.status_code == 200
    started = db_session.query(SimulationRun).filter_by(run_id="real-child-run").one()
    assert started.protocol_version == "protocol_v2"
    assert started.condition_name == "carryover_v1"
    assert started.hypothesis_id == "hypothesis_001"
    assert started.season_id == "season_02"
    assert started.season_number == 2
    assert started.parent_run_id == "real-parent-run"
    assert started.mirror_control_run_id == "real-mirror-run"
    assert started.transfer_policy_version == "season_transfer_policy_v1"
    assert started.epoch_id == "epoch_01"
    assert started.run_class == "deep_96h"
    assert started.start_reason == "phase2_start"

    assert stop_response.status_code == 200
    stop_body = stop_response.json()
    assert stop_body["run_id"] == "real-child-run"
    assert stop_body["report_bundle"]["generated_for"] == "real-child-run"

    stopped = db_session.query(SimulationRun).filter_by(run_id="real-child-run").one()
    assert stopped.ended_at is not None
    assert stopped.end_reason == "phase2_stop"


def test_run_start_retires_inherited_governance_state(db_session, monkeypatch):
    author = _seed_author(db_session)
    old_started_at = now_utc() - admin_api.timedelta(days=1)
    db_session.add(
        SimulationRun(
            run_id="real-old-run",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            started_at=old_started_at,
            ended_at=old_started_at + admin_api.timedelta(hours=12),
        )
    )
    proposal = Proposal(
        author_agent_id=author.id,
        title="Carryover Proposal",
        description="Should not survive into the next run.",
        proposal_type="law",
        status="active",
        created_at=old_started_at + admin_api.timedelta(hours=1),
        voting_closes_at=old_started_at + admin_api.timedelta(hours=2),
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.add(
        Law(
            proposal_id=proposal.id,
            title="Carryover Law",
            description="Should not stay active in a new run.",
            author_agent_id=author.id,
            active=True,
            passed_at=old_started_at + admin_api.timedelta(hours=3),
        )
    )
    db_session.commit()

    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)
    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={"mode": "real", "run_id": "real-new-run"},
        )

    assert response.status_code == 200
    refreshed_proposal = db_session.query(Proposal).filter_by(id=proposal.id).one()
    refreshed_law = db_session.query(Law).one()
    assert refreshed_proposal.status == "expired"
    assert refreshed_proposal.resolved_at is not None
    assert refreshed_law.active is False
    assert refreshed_law.repealed_at is not None


def test_run_stop_closes_current_run_governance_state(db_session, monkeypatch):
    author = _seed_author(db_session)
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        start_response = client.post(
            "/api/admin/control/run/start",
            json={"mode": "real", "run_id": "real-governance-run"},
        )

    assert start_response.status_code == 200
    run_row = db_session.query(SimulationRun).filter_by(run_id="real-governance-run").one()
    proposal = Proposal(
        author_agent_id=author.id,
        title="Live Proposal",
        description="Should expire when the run stops.",
        proposal_type="law",
        status="active",
        created_at=run_row.started_at,
        voting_closes_at=run_row.started_at + admin_api.timedelta(hours=1),
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.add(
        Law(
            proposal_id=proposal.id,
            title="Live Law",
            description="Should deactivate when the run stops.",
            author_agent_id=author.id,
            active=True,
            passed_at=run_row.started_at,
        )
    )
    db_session.commit()

    with client:
        stop_response = client.post(
            "/api/admin/control/run/stop",
            json={"reason": "phase2_stop"},
        )

    assert stop_response.status_code == 200
    refreshed_proposal = db_session.query(Proposal).filter_by(id=proposal.id).one()
    refreshed_law = db_session.query(Law).one()
    assert refreshed_proposal.status == "expired"
    assert refreshed_proposal.resolved_at is not None
    assert refreshed_law.active is False
    assert refreshed_law.repealed_at is not None


def test_run_start_can_mark_tuning_run(db_session, monkeypatch):
    client, runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-tuning-run",
                "run_class": "special_exploratory",
                "condition_name": "scarcity_tuning_v1",
                "tuning_run": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["tuning_run"] is True

    row = db_session.query(SimulationRun).filter_by(run_id="real-tuning-run").one()
    assert row.protocol_deviation is True
    assert row.deviation_reason == "tuning_run"
    assert runtime_stub.effective["SIMULATION_RUN_ID"] == "real-tuning-run"


def test_run_start_rejects_season_id_without_positive_season_number(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-invalid-season",
                "season_id": "season_x",
            },
        )

    assert response.status_code == 422
    assert "season_number must be >= 1 when season_id is provided" in response.text


def test_run_start_rejects_invalid_run_class_value(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-invalid-class",
                "run_class": "weekend_mode",
            },
        )

    assert response.status_code == 422
    assert "run_class" in response.text


def test_run_start_rejects_missing_parent_run_reference(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-child",
                "parent_run_id": "real-parent-missing",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "parent_run_id must reference an existing simulation run"


def test_run_start_rejects_existing_run_id(db_session, monkeypatch):
    db_session.add(
        SimulationRun(
            run_id="real-existing-run",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            started_at=now_utc(),
        )
    )
    db_session.commit()
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={"mode": "real", "run_id": "real-existing-run"},
        )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_run_start_rejects_dirty_world_state(db_session, monkeypatch):
    author = _seed_author(db_session)
    db_session.add(
        Agent(
            agent_number=2,
            display_name="Agent #2",
            model_type="or_gpt_oss_20b_free",
            tier=1,
            personality_type="neutral",
            status="dead",
            system_prompt="{}",
            starvation_cycles=5,
            died_at=now_utc(),
            death_cause="starvation",
        )
    )
    proposal = Proposal(
        author_agent_id=author.id,
        title="Dirty Proposal",
        description="Should block new run starts.",
        proposal_type="law",
        status="active",
        voting_closes_at=now_utc() + admin_api.timedelta(hours=1),
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.add(
        Law(
            proposal_id=proposal.id,
            title="Dirty Law",
            description="Should block new run starts.",
            author_agent_id=author.id,
            active=True,
            passed_at=now_utc(),
        )
    )
    db_session.commit()

    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={"mode": "real", "run_id": "real-new-run"},
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "dead agents" in detail


def test_run_start_rejects_missing_mirror_control_run_reference(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-child",
                "mirror_control_run_id": "real-mirror-missing",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "mirror_control_run_id must reference an existing simulation run"


def test_admin_status_surfaces_run_metadata_for_active_run(db_session, monkeypatch):
    _stub_budget(monkeypatch)
    db_session.add(
        SimulationRun(
            run_id="real-status-mirror",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            started_at=now_utc(),
        )
    )
    db_session.commit()
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        start_response = client.post(
            "/api/admin/control/run/start",
            json={
                "mode": "real",
                "run_id": "real-status-meta",
                "protocol_version": "protocol_v3",
                "condition_name": "baseline_v2",
                "hypothesis_id": "hypothesis_010",
                "season_id": "season_10",
                "season_number": 10,
                "transfer_policy_version": "season_transfer_policy_v2",
                "mirror_control_run_id": "real-status-mirror",
                "epoch_id": "epoch_03",
                "run_class": "special_exploratory",
                "reason": "status_meta_test",
            },
        )
        status_response = client.get("/api/admin/status")

    assert start_response.status_code == 200
    assert status_response.status_code == 200
    body = status_response.json()
    metadata = body["run_metadata"]
    assert metadata is not None
    assert metadata["run_id"] == "real-status-meta"
    assert metadata["protocol_version"] == "protocol_v3"
    assert metadata["condition_name"] == "baseline_v2"
    assert metadata["hypothesis_id"] == "hypothesis_010"
    assert metadata["season_id"] == "season_10"
    assert metadata["season_number"] == 10
    assert metadata["transfer_policy_version"] == "season_transfer_policy_v2"
    assert metadata["mirror_control_run_id"] == "real-status-mirror"
    assert metadata["epoch_id"] == "epoch_03"
    assert metadata["run_class"] == "special_exploratory"
    assert metadata["start_reason"] == "status_meta_test"
    assert body["viewer_ops"]["run_id"] == "real-status-meta"
    assert "report_pipeline" in body
    assert "closeout" in (body.get("report_pipeline") or {})
    assert "backfill" in (body.get("report_pipeline") or {})


def test_run_metrics_empty_payload_includes_run_metadata_key(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)

    with client:
        response = client.get("/api/admin/run/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == ""
    assert "run_metadata" in body
    assert body["run_metadata"] is None


def test_write_route_rejects_without_ip_allowlist_in_production(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch)
    monkeypatch.setattr(admin_api.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(admin_api.settings, "ADMIN_IP_ALLOWLIST", "", raising=False)

    with client:
        response = client.post("/api/admin/control/pause", json={"reason": "prod_block_check"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin write IP allowlist is required in production"


def test_write_route_rejects_non_allowlisted_ip_in_production(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch, client_ip="127.0.0.2")
    monkeypatch.setattr(admin_api.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(admin_api.settings, "ADMIN_IP_ALLOWLIST", "127.0.0.1", raising=False)

    with client:
        response = client.post("/api/admin/control/pause", json={"reason": "prod_ip_block_check"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin write IP not allowed"


def test_write_route_allows_allowlisted_ip_in_production(db_session, monkeypatch):
    client, _runtime_stub = _make_admin_client(db_session, monkeypatch, client_ip="127.0.0.1")
    monkeypatch.setattr(admin_api.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(admin_api.settings, "ADMIN_IP_ALLOWLIST", "127.0.0.1,10.0.0.5", raising=False)

    with client:
        response = client.post("/api/admin/control/pause", json={"reason": "prod_ip_allowed"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["simulation_paused"] is True
