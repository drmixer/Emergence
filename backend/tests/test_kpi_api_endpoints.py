from __future__ import annotations

from types import SimpleNamespace
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

analytics_api = importlib.import_module("app.api.analytics")
admin_api = importlib.import_module("app.api.admin")


class _FakeAnalyticsSession:
    def __init__(self):
        self.rollback_calls = 0
        self.closed = False

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.closed = True


def _make_analytics_client() -> TestClient:
    app = FastAPI()
    app.include_router(analytics_api.router, prefix="/api/analytics")
    return TestClient(app)


def test_kpi_event_ingest_returns_recorded_event(monkeypatch):
    fake_db = _FakeAnalyticsSession()
    captured: dict[str, object] = {}

    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_db)

    def _fake_record_kpi_event(db, payload):
        captured["db"] = db
        captured["payload"] = payload
        return {"id": 42, "event_name": "landing_view", "day_key": "2026-02-09"}

    monkeypatch.setattr(analytics_api, "record_kpi_event", _fake_record_kpi_event)

    with _make_analytics_client() as client:
        response = client.post(
            "/api/analytics/kpi/events",
            json={
                "event_name": "landing_view",
                "visitor_id": "visitor-abc12345",
                "session_id": "session-1",
                "surface": "landing",
                "target": "hero_primary",
                "path": "/",
                "referrer": "https://example.com",
                "metadata": {"experiment": "hero_v2"},
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "event": {"id": 42, "event_name": "landing_view", "day_key": "2026-02-09"},
    }
    assert captured["db"] is fake_db
    assert captured["payload"] == {
        "event_name": "landing_view",
        "visitor_id": "visitor-abc12345",
        "session_id": "session-1",
        "run_id": None,
        "event_id": None,
        "surface": "landing",
        "target": "hero_primary",
        "path": "/",
        "referrer": "https://example.com",
        "metadata": {"experiment": "hero_v2"},
    }
    assert fake_db.rollback_calls == 0
    assert fake_db.closed is True


def test_kpi_event_ingest_maps_value_error_to_400(monkeypatch):
    fake_db = _FakeAnalyticsSession()
    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        analytics_api,
        "record_kpi_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("unsupported event_name")),
    )

    with _make_analytics_client() as client:
        response = client.post(
            "/api/analytics/kpi/events",
            json={"event_name": "bad", "visitor_id": "visitor-abc12345"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported event_name"
    assert fake_db.rollback_calls == 1
    assert fake_db.closed is True


def test_kpi_event_ingest_maps_unexpected_error_to_500(monkeypatch):
    fake_db = _FakeAnalyticsSession()
    monkeypatch.setattr(analytics_api, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        analytics_api,
        "record_kpi_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with _make_analytics_client() as client:
        response = client.post(
            "/api/analytics/kpi/events",
            json={"event_name": "landing_view", "visitor_id": "visitor-abc12345"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to record KPI event"
    assert fake_db.rollback_calls == 1
    assert fake_db.closed is True


def _make_admin_client(fake_db, *, actor_id: str = "ops-tester") -> TestClient:
    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/admin")
    app.dependency_overrides[admin_api.get_db] = lambda: fake_db
    app.dependency_overrides[admin_api.require_admin_auth] = lambda: admin_api.AdminActor(
        actor_id=actor_id,
        client_ip="127.0.0.1",
    )
    return TestClient(app)


def test_admin_kpi_rollups_returns_payload(monkeypatch):
    fake_db = SimpleNamespace(name="fake-db")
    captured: dict[str, object] = {}

    def _fake_get_recent_rollups(db, *, days: int, refresh: bool):
        captured["db"] = db
        captured["days"] = days
        captured["refresh"] = refresh
        return {
            "summary": {
                "latest_day_key": "2026-02-09",
                "latest": {"day_key": "2026-02-09", "landing_views": 25},
                "seven_day_avg": {"landing_to_run_ctr": 0.42},
            },
            "items": [{"day_key": "2026-02-09", "landing_views": 25}],
        }

    monkeypatch.setattr(admin_api, "get_recent_rollups", _fake_get_recent_rollups)

    with _make_admin_client(fake_db) as client:
        response = client.get("/api/admin/kpi/rollups?days=7&refresh=false")

    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 7
    assert body["summary"]["latest_day_key"] == "2026-02-09"
    assert body["items"] == [{"day_key": "2026-02-09", "landing_views": 25}]
    assert body["generated_at"]
    assert captured == {"db": fake_db, "days": 7, "refresh": False}


def test_admin_kpi_rollups_returns_empty_payload_when_table_missing(monkeypatch):
    fake_db = SimpleNamespace(name="fake-db")
    monkeypatch.setattr(
        admin_api,
        "get_recent_rollups",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError('relation "kpi_daily_rollups" does not exist')
        ),
    )

    with _make_admin_client(fake_db) as client:
        response = client.get("/api/admin/kpi/rollups?days=5")

    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 5
    assert body["items"] == []
    assert body["summary"]["latest_day_key"] is None
    assert body["summary"]["latest"] is None
    assert body["summary"]["seven_day_avg"] == {}
