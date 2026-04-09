from __future__ import annotations

from datetime import datetime, timezone
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

analytics_api = importlib.import_module("app.api.analytics")


class _FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics_api.router, prefix="/api/analytics")
    return TestClient(app)


def _turn(
    event_id: int,
    *,
    event_type: str,
    category: str,
    salience: int,
    created_at: str,
    run_id: str = "run-20260409A",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "title": f"Event {event_id}",
        "description": f"Description for event {event_id}",
        "salience": salience,
        "category": category,
        "actor": None,
        "created_at": created_at,
        "metadata": {"runtime": {"run_id": run_id}, **(metadata or {})},
    }


def test_select_best_moments_prefers_category_diversity():
    turns = [
        _turn(101, event_type="agent_died", category="conflict", salience=98, created_at="2026-04-09T10:00:00+00:00"),
        _turn(102, event_type="agent_sanctioned", category="conflict", salience=97, created_at="2026-04-09T09:30:00+00:00"),
        _turn(103, event_type="law_passed", category="governance", salience=95, created_at="2026-04-09T08:00:00+00:00"),
        _turn(104, event_type="world_event", category="crisis", salience=94, created_at="2026-04-09T07:00:00+00:00"),
    ]

    selected = analytics_api._select_best_moments_payloads(turns, 3)

    assert [item["event_id"] for item in selected] == [101, 103, 104]
    assert selected[0]["label"] == "Permanent death"
    assert selected[1]["stake"] == "The rules changed, so downstream incentives and behavior likely changed too."
    assert selected[2]["run_id"] == "run-20260409A"


def test_best_moments_endpoint_returns_curated_payload(monkeypatch):
    fake_session = _FakeSession()
    now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    scored = [
        (94, now, _turn(201, event_type="world_event", category="crisis", salience=94, created_at="2026-04-09T11:30:00+00:00", run_id="run-20260409B")),
        (91, now, _turn(202, event_type="law_passed", category="governance", salience=91, created_at="2026-04-09T11:10:00+00:00", run_id="run-20260409B")),
        (89, now, _turn(203, event_type="became_dormant", category="notable", salience=89, created_at="2026-04-09T10:50:00+00:00", run_id="run-20260409B")),
    ]

    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(analytics_api, "_collect_scored_plot_turns", lambda *args, **kwargs: scored)

    with _make_client() as client:
        response = client.get("/api/analytics/best-moments?limit=2&hours=48&min_salience=60&run_id=run-20260409B")

    assert response.status_code == 200
    body = response.json()
    assert body["window_hours"] == 48
    assert body["min_salience"] == 60
    assert body["run_id"] == "run-20260409B"
    assert body["count"] == 2
    assert [item["event_id"] for item in body["items"]] == [201, 202]
    assert body["items"][0]["label"] == "World shock"
    assert body["items"][0]["stake"] == "A system-wide shock changed constraints for many agents at once."
    assert body["items"][1]["run_id"] == "run-20260409B"
    assert fake_session.closed is True


def test_select_replay_story_payloads_assigns_chapters_and_deltas():
    turns = [
        _turn(301, event_type="world_event", category="crisis", salience=92, created_at="2026-04-09T08:00:00+00:00"),
        _turn(
            302,
            event_type="proposal_resolved",
            category="governance",
            salience=88,
            created_at="2026-04-09T09:00:00+00:00",
            metadata={"result": "passed"},
        ),
        _turn(303, event_type="agent_died", category="conflict", salience=95, created_at="2026-04-09T10:00:00+00:00"),
        _turn(304, event_type="trade", category="cooperation", salience=81, created_at="2026-04-09T11:00:00+00:00"),
    ]

    selected = analytics_api._select_replay_story_payloads(turns, target_count=4)

    assert [item["chapter"] for item in selected] == ["Trigger", "Escalation", "Turning Point", "Outcome"]
    assert selected[0]["why_this_matters"] == "A system-level shock altered constraints for many agents at once and can redirect the entire run trajectory."
    assert selected[1]["deltas"][0] == {"label": "Proposal", "value": "Passed", "tone": "up"}
    assert selected[2]["deltas"][0] == {"label": "Deaths", "value": "+1", "tone": "down"}
    assert selected[3]["run_id"] == "run-20260409A"


def test_replay_story_endpoint_returns_chaptered_payload(monkeypatch):
    fake_session = _FakeSession()
    now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    scored = [
        (92, now, _turn(401, event_type="world_event", category="crisis", salience=92, created_at="2026-04-09T08:00:00+00:00", run_id="run-20260409C")),
        (90, now, _turn(402, event_type="law_passed", category="governance", salience=90, created_at="2026-04-09T09:00:00+00:00", run_id="run-20260409C", metadata={"title": "Emergency Rationing"})),
        (87, now, _turn(403, event_type="agent_died", category="conflict", salience=87, created_at="2026-04-09T10:00:00+00:00", run_id="run-20260409C")),
        (78, now, _turn(404, event_type="trade", category="cooperation", salience=78, created_at="2026-04-09T11:00:00+00:00", run_id="run-20260409C")),
    ]

    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(analytics_api, "_collect_scored_plot_turns", lambda *args, **kwargs: scored)

    with _make_client() as client:
        response = client.get("/api/analytics/plot-turns/replay-story?limit=4&hours=24&min_salience=55&run_id=run-20260409C")

    assert response.status_code == 200
    body = response.json()
    assert body["window_hours"] == 24
    assert body["run_id"] == "run-20260409C"
    assert body["count"] == 4
    assert body["chapter_count"] == 4
    assert [item["chapter"] for item in body["items"]] == ["Trigger", "Escalation", "Turning Point", "Outcome"]
    assert body["chapters"][0]["label"] == "Trigger"
    assert body["chapters"][0]["lead_event_id"] == 401
    assert body["items"][1]["deltas"][0] == {"label": "Laws", "value": "+1", "tone": "up"}
    assert body["items"][2]["why_this_matters"] == "Conflict spikes coordination costs and can rapidly reorder faction trust, trade flow, and survival outcomes."
    assert fake_session.closed is True
