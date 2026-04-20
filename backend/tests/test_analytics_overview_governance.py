from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import (
    Agent,
    AgentInventory,
    Event,
    GlobalResources,
    Law,
    Message,
    Proposal,
    SimulationRun,
)

analytics_api = importlib.import_module("app.api.analytics")


@pytest.fixture
def testing_session_factory():
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
        Agent.__table__,
        AgentInventory.__table__,
        Event.__table__,
        GlobalResources.__table__,
        Message.__table__,
        Proposal.__table__,
        Law.__table__,
        SimulationRun.__table__,
    ):
        table.create(bind=engine)

    factory = sessionmaker(bind=engine, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics_api.router, prefix="/api/analytics")
    return TestClient(app)


def test_overview_counts_passed_proposals_by_resolution_window(
    testing_session_factory,
    monkeypatch,
):
    session = testing_session_factory()
    run_started_at = datetime(2026, 4, 20, 2, 8, 43, tzinfo=timezone.utc)

    author = Agent(
        agent_number=1,
        display_name="Agent #1",
        model_type="or_gpt_oss_20b_free",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="{}",
    )
    session.add(author)
    session.flush()
    session.add(
        SimulationRun(
            run_id="real-20260420T020843Z",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="special_exploratory",
            started_at=run_started_at,
        )
    )
    proposal = Proposal(
        author_agent_id=author.id,
        title="Carryover Proposal",
        description="Created before the run but resolved during it.",
        proposal_type="law",
        status="passed",
        created_at=run_started_at - timedelta(hours=2),
        voting_closes_at=run_started_at + timedelta(minutes=30),
        resolved_at=run_started_at + timedelta(minutes=30),
    )
    session.add(proposal)
    session.flush()
    session.add(
        Law(
            proposal_id=proposal.id,
            title="Carryover Law",
            description="Passed during the current run window.",
            author_agent_id=author.id,
            active=True,
            passed_at=run_started_at + timedelta(minutes=30),
        )
    )
    session.add(
        Event(
            event_type="law_passed",
            description="New law enacted.",
            created_at=run_started_at + timedelta(minutes=30),
            event_metadata={"runtime": {"run_id": "real-20260420T020843Z"}},
        )
    )
    session.commit()
    session.close()

    runtime_values = {
        "SIMULATION_ACTIVE": True,
        "SIMULATION_PAUSED": False,
        "SIMULATION_RUN_ID": "real-20260420T020843Z",
    }
    monkeypatch.setattr(analytics_api, "SessionLocal", testing_session_factory)
    monkeypatch.setattr(
        analytics_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: runtime_values.get(key),
    )

    with _make_client() as client:
        response = client.get("/api/analytics/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["scope"]["active_run_id"] == "real-20260420T020843Z"
    assert body["proposals"]["total"] == 0
    assert body["proposals"]["passed"] == 1
    assert body["laws"]["total"] == 1
