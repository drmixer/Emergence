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


def test_replay_story_excludes_routine_work_even_when_salient(playback_session_factory, monkeypatch):
    session = playback_session_factory()
    run_started_at = datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc)

    agent = Agent(
        agent_number=4,
        display_name="Agent #4",
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
            run_id="run-story-no-work",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="special_exploratory",
            started_at=run_started_at,
            ended_at=run_started_at + timedelta(hours=2),
        )
    )

    session.add_all(
        [
            Event(
                agent_id=agent.id,
                event_type="work",
                description="Agent #4 farmed 1.40 food in 1h",
                created_at=run_started_at + timedelta(minutes=1),
                event_metadata={"runtime": {"run_id": "run-story-no-work"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="vote",
                description="Agent #4 voted yes on a proposal",
                created_at=run_started_at + timedelta(minutes=2),
                event_metadata={"runtime": {"run_id": "run-story-no-work"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="proposal_resolved",
                description="Proposal 'Emergency Aid Floor' passed (8/1)",
                created_at=run_started_at + timedelta(minutes=20),
                event_metadata={"runtime": {"run_id": "run-story-no-work"}, "result": "passed"},
            ),
            Event(
                agent_id=agent.id,
                event_type="request_aid",
                description="Agent #4 requested 2 food from Agent #5",
                created_at=run_started_at + timedelta(minutes=40),
                event_metadata={"runtime": {"run_id": "run-story-no-work"}},
            ),
            Event(
                agent_id=agent.id,
                event_type="agent_died",
                description="Agent #9 died after dormant upkeep failure",
                created_at=run_started_at + timedelta(minutes=80),
                event_metadata={"runtime": {"run_id": "run-story-no-work"}},
            ),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get(
            "/api/analytics/plot-turns/replay-story"
            "?run_id=run-story-no-work&hours=96&min_salience=1&limit=4"
        )

    assert response.status_code == 200
    body = response.json()
    event_types = [item["event_type"] for item in body["items"]]
    assert "work" not in event_types
    assert "vote" not in event_types
    assert event_types == ["proposal_resolved", "request_aid", "agent_died"]
    assert [item["chapter"] for item in body["items"]] == ["Trigger", "Escalation", "Outcome"]


def test_run_watch_board_returns_explicit_signal_lanes(playback_session_factory, monkeypatch):
    session = playback_session_factory()
    run_started_at = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
    run_ended_at = run_started_at + timedelta(hours=3)

    agent = Agent(
        agent_number=8,
        display_name="Agent #8",
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
            run_id="run-watch-board",
            run_mode="real",
            protocol_version="protocol_v1",
            run_class="special_exploratory",
            started_at=run_started_at,
            ended_at=run_ended_at,
        )
    )

    def event_row(event_type: str, minutes: int, description: str, metadata: dict | None = None) -> Event:
        payload = {"runtime": {"run_id": "run-watch-board"}}
        if metadata:
            payload.update(metadata)
        return Event(
            agent_id=agent.id,
            event_type=event_type,
            description=description,
            created_at=run_started_at + timedelta(minutes=minutes),
            event_metadata=payload,
        )

    session.add_all(
        [
            event_row("direct_message", 2, "Generic private coordination"),
            event_row("forum_reply", 3, "Generic reply pile-on"),
            event_row("work", 4, "Routine work"),
            event_row("create_proposal", 15, "Agent #8 created proposal: Aid Floor"),
            event_row("trade", 35, "Agent #8 traded 5 food to Agent #9"),
            event_row("request_aid", 70, "Agent #9 requested 2 food from Agent #8"),
            event_row("law_passed", 110, "Law passed", {"title": "Aid Floor"}),
            event_row("agent_died", 150, "Agent #4 died"),
            Event(
                agent_id=agent.id,
                event_type="law_passed",
                description="Other run law",
                created_at=run_started_at + timedelta(minutes=120),
                event_metadata={"runtime": {"run_id": "other-run"}, "title": "Other Law"},
            ),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(analytics_api, "SessionLocal", playback_session_factory)

    with _make_client() as client:
        response = client.get("/api/analytics/runs/run-watch-board/watch?bucket_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["contract"]["source_type"] == "watch_replay_board"
    assert body["contract"]["moment_policy"] == "explicit_watch_signal_event_types"
    assert body["activity"]["total_events"] == 8
    assert body["activity"]["direct_messages"] == 1
    assert body["activity"]["forum_actions"] == 1
    assert body["activity"]["laws_passed"] == 1
    assert body["activity"]["deaths"] == 1

    event_types = [item["event_type"] for item in body["items"]]
    assert event_types == ["create_proposal", "trade", "request_aid", "law_passed", "agent_died"]
    assert "direct_message" not in event_types
    assert "forum_reply" not in event_types
    assert [item["lane"] for item in body["items"]] == [
        "governance",
        "aid_trade",
        "aid_trade",
        "governance",
        "survival",
    ]
    assert body["bucket_count"] == 3
    assert [bucket["linked_moment_count"] for bucket in body["buckets"]] == [2, 2, 1]
    assert body["buckets"][0]["representative"]["event_type"] == "create_proposal"
    lane_counts = {lane["key"]: lane["count"] for lane in body["lanes"]}
    assert lane_counts["governance"] == 2
    assert lane_counts["aid_trade"] == 2
    assert lane_counts["survival"] == 1


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
