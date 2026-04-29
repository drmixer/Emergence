from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import AdminConfigChange, Agent, Event, SimulationRun

analytics_api = importlib.import_module("app.api.analytics")


@pytest.fixture
def playback_session_factory():
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
        Event.__table__,
        SimulationRun.__table__,
        AdminConfigChange.__table__,
    ):
        table.create(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NULL,
                    agent_id INTEGER NULL,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    fallback_used BOOLEAN NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    provider TEXT NULL,
                    model_name TEXT NULL,
                    resolved_model_name TEXT NULL,
                    error_type TEXT NULL,
                    created_at TIMESTAMP NULL
                )
                """
            )
        )

    factory = sessionmaker(bind=engine, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics_api.router, prefix="/api/analytics")
    return TestClient(app)


def test_run_playback_is_run_scoped_and_ordered(playback_session_factory, monkeypatch):
    session = playback_session_factory()
    run_started_at = datetime(2026, 4, 20, 2, 0, 0, tzinfo=timezone.utc)
    run_ended_at = run_started_at + timedelta(hours=2)

    agent = Agent(
        agent_number=1,
        display_name="Agent #1",
        model_type="or_gpt_oss_20b_free",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="{}",
    )
    session.add(agent)
    session.flush()

    session.add(
        SimulationRun(
            run_id="run-playback-a",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            started_at=run_started_at,
            ended_at=run_ended_at,
        )
    )

    first = Event(
        agent_id=agent.id,
        event_type="forum_post",
        description="first event in run",
        created_at=run_started_at,
        event_metadata={"runtime": {"run_id": "run-playback-a"}},
    )
    second_same_timestamp = Event(
        agent_id=agent.id,
        event_type="work",
        description="second event with same timestamp",
        created_at=run_started_at,
        event_metadata={"runtime": {"run_id": "run-playback-a"}},
    )
    middle = Event(
        agent_id=agent.id,
        event_type="vote",
        description="middle event in run",
        created_at=run_started_at + timedelta(minutes=45),
        event_metadata={"runtime": {"run_id": "run-playback-a"}},
    )
    other_run = Event(
        agent_id=agent.id,
        event_type="forum_post",
        description="belongs to another run",
        created_at=run_started_at + timedelta(minutes=15),
        event_metadata={"runtime": {"run_id": "run-playback-b"}},
    )
    missing_runtime = Event(
        agent_id=agent.id,
        event_type="trade",
        description="missing runtime run id",
        created_at=run_started_at + timedelta(minutes=30),
        event_metadata={},
    )
    after_end = Event(
        agent_id=agent.id,
        event_type="forum_reply",
        description="after run end",
        created_at=run_ended_at + timedelta(minutes=1),
        event_metadata={"runtime": {"run_id": "run-playback-a"}},
    )
    session.add_all([first, second_same_timestamp, middle, other_run, missing_runtime, after_end])
    session.commit()
    session.close()

    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get("/api/analytics/runs/run-playback-a/playback?limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["contract"]["source_type"] == "full_event_playback"
    assert body["contract"]["ordering"] == "created_at_asc_id_asc"
    assert body["contract"]["run_scope"] == "event_metadata.runtime.run_id"
    assert body["contract"]["completeness"] == "logged_events_only"
    assert body["time_window"]["source"] == "simulation_runs_registry"
    assert body["total_count"] == 3
    assert body["count"] == 3
    assert body["items"][0]["title"] == "Forum Post"
    assert body["items"][0]["category"] == "cooperation"
    assert isinstance(body["items"][0]["salience"], int)
    assert [item["description"] for item in body["items"]] == [
        "first event in run",
        "second event with same timestamp",
        "middle event in run",
    ]
    assert [item["run_id"] for item in body["items"]] == [
        "run-playback-a",
        "run-playback-a",
        "run-playback-a",
    ]


def test_run_playback_supports_pagination(playback_session_factory, monkeypatch):
    session = playback_session_factory()
    run_started_at = datetime(2026, 4, 20, 5, 0, 0, tzinfo=timezone.utc)

    agent = Agent(
        agent_number=2,
        display_name="Agent #2",
        model_type="or_gpt_oss_20b_free",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="{}",
    )
    session.add(agent)
    session.flush()

    session.add(
        SimulationRun(
            run_id="run-playback-page",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="special_exploratory",
            started_at=run_started_at,
            ended_at=run_started_at + timedelta(hours=1),
        )
    )

    session.add_all(
        [
            Event(
                agent_id=agent.id,
                event_type="forum_post",
                description="page event 1",
                created_at=run_started_at + timedelta(minutes=1),
                event_metadata={"runtime": {"run_id": "run-playback-page"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="forum_reply",
                description="page event 2",
                created_at=run_started_at + timedelta(minutes=2),
                event_metadata={"runtime": {"run_id": "run-playback-page"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="work",
                description="page event 3",
                created_at=run_started_at + timedelta(minutes=3),
                event_metadata={"runtime": {"run_id": "run-playback-page"}},
            ),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get("/api/analytics/runs/run-playback-page/playback?limit=1&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 3
    assert body["count"] == 1
    assert body["items"][0]["description"] == "page event 2"


def test_run_detail_is_strictly_run_scoped_and_end_clamped(playback_session_factory, monkeypatch):
    session = playback_session_factory()
    run_started_at = datetime(2026, 4, 20, 2, 0, 0, tzinfo=timezone.utc)
    run_ended_at = run_started_at + timedelta(hours=1)

    agent = Agent(
        agent_number=3,
        display_name="Agent #3",
        model_type="or_gpt_oss_20b_free",
        tier=1,
        personality_type="neutral",
        status="active",
        system_prompt="{}",
    )
    session.add(agent)
    session.flush()

    session.add(
        SimulationRun(
            run_id="run-detail-a",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="standard_72h",
            started_at=run_started_at,
            ended_at=run_ended_at,
        )
    )
    session.add(
        AdminConfigChange(
            key="SIMULATION_RUN_ID",
            old_value="old-run",
            new_value="run-detail-a",
            changed_by="test",
            environment="test",
            created_at=run_started_at,
        )
    )
    session.add_all(
        [
            Event(
                agent_id=agent.id,
                event_type="forum_post",
                description="in-run forum event",
                created_at=run_started_at + timedelta(minutes=5),
                event_metadata={"runtime": {"run_id": "run-detail-a"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="in-run death",
                created_at=run_started_at + timedelta(minutes=15),
                event_metadata={"runtime": {"run_id": "run-detail-a"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="different run inside the same clock window",
                created_at=run_started_at + timedelta(minutes=20),
                event_metadata={"runtime": {"run_id": "run-detail-b"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="same run tag after recorded end",
                created_at=run_ended_at + timedelta(minutes=1),
                event_metadata={"runtime": {"run_id": "run-detail-a"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="later run for the same agent",
                created_at=run_ended_at + timedelta(days=1),
                event_metadata={"runtime": {"run_id": "later-run"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="missing runtime run id",
                created_at=run_started_at + timedelta(minutes=25),
                event_metadata={},
            ),
        ]
    )
    session.execute(
        text(
            """
            INSERT INTO llm_usage (
                run_id, agent_id, success, fallback_used,
                prompt_tokens, completion_tokens, total_tokens,
                estimated_cost_usd, created_at
            )
            VALUES
                (:run_id, :agent_id, 1, 0, 10, 5, 15, 0.01, :inside_ts),
                (:run_id, :agent_id, 1, 0, 10, 5, 15, 0.01, :after_ts),
                ('later-run', :agent_id, 1, 0, 20, 10, 30, 0.02, :later_ts)
            """
        ),
        {
            "run_id": "run-detail-a",
            "agent_id": agent.id,
            "inside_ts": run_started_at + timedelta(minutes=10),
            "after_ts": run_ended_at + timedelta(minutes=1),
            "later_ts": run_ended_at + timedelta(days=1),
        },
    )
    session.commit()
    session.close()

    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get("/api/analytics/runs/run-detail-a?trace_limit=3&min_salience=1")

    assert response.status_code == 200
    body = response.json()
    assert body["activity"]["total_events"] == 2
    assert body["activity"]["deaths"] == 1
    assert body["llm"]["calls"] == 1
    assert body["llm"]["total_tokens"] == 15
    assert body["provenance"]["time_window"]["start_utc"] == run_started_at.isoformat()
    assert body["provenance"]["time_window"]["end_utc"] == run_ended_at.isoformat()
    assert [item["description"] for item in body["source_traces"]] == [
        "in-run death",
        "in-run forum event",
    ]


def test_run_playback_returns_404_for_unknown_run(playback_session_factory, monkeypatch):
    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get("/api/analytics/runs/run-missing/playback")

    assert response.status_code == 404
    assert response.json()["detail"] == "Run not found"
