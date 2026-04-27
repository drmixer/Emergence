from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, Message, Proposal, SimulationRun
from app.services import live_run_scope

messages_api = importlib.import_module("app.api.messages")
proposals_api = importlib.import_module("app.api.proposals")


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
        Message.__table__,
        Proposal.__table__,
    ):
        table.create(bind=engine)

    return sessionmaker(bind=engine, future=True)()


def _make_client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(messages_api.router, prefix="/api/messages")
    app.include_router(proposals_api.router, prefix="/api/proposals")
    app.dependency_overrides[messages_api.get_db] = lambda: db_session
    app.dependency_overrides[proposals_api.get_db] = lambda: db_session
    return TestClient(app)


def test_duplicate_wave_endpoints_cluster_proposals_and_forum_messages(monkeypatch):
    db_session = _build_session()
    try:
        started_at = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        agents = [
            Agent(
                agent_number=idx,
                display_name=f"Agent {idx}",
                model_type="gm_gemini_2_5_flash",
                tier=1,
                personality_type="neutral",
                status="active",
                system_prompt="prompt",
            )
            for idx in (1, 2, 3)
        ]
        db_session.add_all(agents)
        db_session.flush()
        db_session.add(
            SimulationRun(
                run_id="run-duplicate-waves",
                run_mode="test",
                protocol_version="protocol_v1",
                run_class="special_exploratory",
                started_at=started_at,
            )
        )
        db_session.add_all(
            [
                Proposal(
                    author_agent_id=agents[0].id,
                    title="Emergency Food Energy Rationing",
                    description="Coordinate scarcity rationing for food energy production and dormant support.",
                    proposal_type="law",
                    status="active",
                    created_at=started_at + timedelta(minutes=1),
                    voting_closes_at=started_at + timedelta(hours=1),
                ),
                Proposal(
                    author_agent_id=agents[1].id,
                    title="Food Energy Scarcity Rationing Protocol",
                    description="Coordinate food and energy production during scarcity with dormant support.",
                    proposal_type="law",
                    status="active",
                    created_at=started_at + timedelta(minutes=2),
                    voting_closes_at=started_at + timedelta(hours=1),
                ),
                Message(
                    author_agent_id=agents[0].id,
                    content="Urgent food shortage: coordinate energy rationing and shared production today.",
                    message_type="forum_post",
                    created_at=started_at + timedelta(minutes=3),
                ),
                Message(
                    author_agent_id=agents[2].id,
                    content="Food shortage is urgent; coordinate shared production and energy rationing now.",
                    message_type="forum_post",
                    created_at=started_at + timedelta(minutes=4),
                ),
            ]
        )
        db_session.commit()

        runtime_values = {
            "SIMULATION_ACTIVE": True,
            "SIMULATION_RUN_ID": "run-duplicate-waves",
        }
        monkeypatch.setattr(
            live_run_scope.runtime_config_service,
            "get_effective_value_cached",
            lambda key: runtime_values.get(key),
        )

        with _make_client(db_session) as client:
            proposal_response = client.get("/api/proposals/duplicate-waves")
            message_response = client.get("/api/messages/duplicate-waves")

        assert proposal_response.status_code == 200
        proposal_body = proposal_response.json()
        assert proposal_body["summary"]["proposal_wave_count"] == 1
        assert proposal_body["waves"][0]["count"] == 2
        assert proposal_body["waves"][0]["actor_count"] == 2

        assert message_response.status_code == 200
        message_body = message_response.json()
        assert message_body["summary"]["forum_wave_count"] == 1
        assert message_body["waves"][0]["count"] == 2
        assert message_body["waves"][0]["source"] == "forum"
    finally:
        db_session.close()
