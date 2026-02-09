from __future__ import annotations

from datetime import datetime, timezone
import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

analytics_api = importlib.import_module("app.api.analytics")


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, *, event=None, agent=None):
        self._event = event
        self._agent = agent
        self.closed = False

    def query(self, model):
        if model is analytics_api.Event:
            return _FakeQuery(self._event)
        if model is analytics_api.Agent:
            return _FakeQuery(self._agent)
        raise AssertionError(f"Unexpected model query: {model!r}")

    def close(self):
        self.closed = True


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics_api.router, prefix="/api/analytics")
    return TestClient(app)


def test_run_social_card_png_endpoint_returns_png(monkeypatch):
    monkeypatch.setattr(
        analytics_api,
        "run_detail",
        lambda **_kwargs: {
            "provenance": {"verification_state": "verified"},
            "activity": {"total_events": 42, "laws_passed": 3, "deaths": 1},
            "llm": {"calls": 9},
            "source_traces": [{"title": "Law Passed: Energy Compact"}],
        },
    )

    captured: dict[str, object] = {}

    def _fake_png_bytes(**kwargs):
        captured.update(kwargs)
        return PNG_SIGNATURE + b"run-card"

    monkeypatch.setattr(analytics_api, "_social_card_png_bytes", _fake_png_bytes)

    with _make_client() as client:
        response = client.get(
            "/api/analytics/runs/run-20260207T015151Z/social-card.png"
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(PNG_SIGNATURE)
    assert captured["kicker"] == "Run run-20260207T015151Z"
    assert captured["title"] == "Simulation Run run-20260207T015151Z"


def test_run_social_card_png_endpoint_returns_503_when_renderer_missing(monkeypatch):
    monkeypatch.setattr(
        analytics_api,
        "run_detail",
        lambda **_kwargs: {
            "provenance": {"verification_state": "unverified"},
            "activity": {},
            "llm": {},
            "source_traces": [],
        },
    )

    def _raise_runtime_error(**_kwargs):
        raise RuntimeError("Pillow is required for PNG social cards")

    monkeypatch.setattr(analytics_api, "_social_card_png_bytes", _raise_runtime_error)

    with _make_client() as client:
        response = client.get(
            "/api/analytics/runs/run-20260207T015151Z/social-card.png"
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Pillow is required for PNG social cards"


def test_moment_social_card_png_endpoint_uses_runtime_run_id(monkeypatch):
    event = SimpleNamespace(
        id=314,
        agent_id=None,
        event_type="proposal_resolved",
        description="Coalition approved emergency food protocol",
        event_metadata={
            "runtime": {"run_id": "run-20260207T015151Z"},
            "title": "Emergency Food Protocol",
            "result": "passed",
        },
        created_at=datetime(2026, 2, 7, 1, 52, 0, tzinfo=timezone.utc),
    )
    fake_session = _FakeSession(event=event, agent=None)
    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_session)

    captured: dict[str, object] = {}

    def _fake_png_bytes(**kwargs):
        captured.update(kwargs)
        return PNG_SIGNATURE + b"moment-card"

    monkeypatch.setattr(analytics_api, "_social_card_png_bytes", _fake_png_bytes)

    with _make_client() as client:
        response = client.get("/api/analytics/moments/314/social-card.png")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(PNG_SIGNATURE)
    assert captured["kicker"] == "Moment #314"
    assert captured["title"] == "Emergency Food Protocol (passed)"
    stat_pairs = captured["stat_pairs"]
    assert stat_pairs[0] == ("Type", "Proposal Resolved")
    assert stat_pairs[1][0] == "Signal"
    assert stat_pairs[2] == ("Run", "run-20260207T015151Z")
    assert fake_session.closed is True


def test_moment_social_card_png_endpoint_returns_404_for_unknown_event(monkeypatch):
    fake_session = _FakeSession(event=None, agent=None)
    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_session)

    with _make_client() as client:
        response = client.get("/api/analytics/moments/999999/social-card.png")

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert fake_session.closed is True
