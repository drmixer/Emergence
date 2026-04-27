from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, AgentInventory, GlobalResources, Law, Proposal, SimulationRun
from app.services import live_run_scope, reserve_semantics

laws_api = importlib.import_module("app.api.laws")
resources_api = importlib.import_module("app.api.resources")


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

    for table in (
        SimulationRun.__table__,
        Agent.__table__,
        AgentInventory.__table__,
        GlobalResources.__table__,
        Proposal.__table__,
        Law.__table__,
    ):
        table.create(bind=engine)

    return sessionmaker(bind=engine, future=True)()


def _make_client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(resources_api.router, prefix="/api/resources")
    app.include_router(laws_api.router, prefix="/api/laws")
    app.dependency_overrides[resources_api.get_db] = lambda: db_session
    app.dependency_overrides[laws_api.get_db] = lambda: db_session
    return TestClient(app)


def test_reserve_policy_and_mechanics_are_labeled_separately(monkeypatch):
    db_session = _build_session()
    try:
        started_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        author = Agent(
            agent_number=1,
            display_name="Reserve Author",
            model_type="gm_gemini_2_5_flash",
            tier=1,
            personality_type="neutral",
            status="active",
            system_prompt="prompt",
        )
        db_session.add(author)
        db_session.flush()
        db_session.add(
            SimulationRun(
                run_id="run-reserve-labels",
                run_mode="test",
                protocol_version="protocol_v1",
                run_class="special_exploratory",
                started_at=started_at,
            )
        )
        proposal = Proposal(
            author_agent_id=author.id,
            title="Shared Reserve",
            description="Create a shared survival reserve for aid.",
            proposal_type="law",
            status="passed",
            created_at=started_at + timedelta(minutes=1),
            resolved_at=started_at + timedelta(minutes=2),
            voting_closes_at=started_at + timedelta(minutes=2),
        )
        db_session.add(proposal)
        db_session.flush()
        db_session.add(
            Law(
                proposal_id=proposal.id,
                title="Shared Survival Reserve",
                description="Agents should maintain a reserve for survival aid and dormant support.",
                author_agent_id=author.id,
                active=True,
                passed_at=started_at + timedelta(minutes=2),
            )
        )
        db_session.add(
            GlobalResources(resource_type="food", total_amount=10, in_common_pool=4)
        )
        db_session.commit()

        runtime_values = {
            "SIMULATION_ACTIVE": True,
            "SIMULATION_RUN_ID": "run-reserve-labels",
        }
        monkeypatch.setattr(
            live_run_scope.runtime_config_service,
            "get_effective_value_cached",
            lambda key: runtime_values.get(key),
        )
        monkeypatch.setattr(reserve_semantics, "reserve_auto_contribution_enabled", lambda: False)
        monkeypatch.setattr(reserve_semantics, "reserve_active_aid_enabled", lambda: False)
        monkeypatch.setattr(reserve_semantics, "reserve_dormant_maintenance_enabled", lambda: False)
        monkeypatch.setattr(reserve_semantics, "reserve_auto_revive_enabled", lambda: False)

        with _make_client(db_session) as client:
            resources_response = client.get("/api/resources")
            laws_response = client.get("/api/laws")

        assert resources_response.status_code == 200
        resources_body = resources_response.json()
        semantics = resources_body["reserve_semantics"]
        assert semantics["status"] == "policy_only"
        assert semantics["policy_intent"]["reserve_law_active"] is True
        assert semantics["mechanical_access"]["automatic_mechanics_available"] is False
        assert semantics["mechanical_access"]["enabled_modes"] == []

        assert laws_response.status_code == 200
        laws_body = laws_response.json()
        assert laws_body[0]["reserve_semantics"]["kind"] == "survival_reserve"
        assert laws_body[0]["reserve_semantics"]["policy_intent_label"] == "Active reserve policy intent"
        assert "not currently reachable" in laws_body[0]["reserve_semantics"]["mechanical_access_label"]
    finally:
        db_session.close()
