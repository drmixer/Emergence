from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import kpi_rollups


def test_normalize_kpi_event_sanitizes_payload():
    payload = {
        "event_name": "RUN_DETAIL_VIEW",
        "visitor_id": " visitor-123 ",
        "session_id": " session-456 ",
        "run_id": " run-abc ",
        "event_id": "42",
        "surface": " run_detail_page ",
        "target": " focused_event ",
        "path": " /runs/run-abc ",
        "referrer": " https://example.test/share ",
        "metadata": {"foo": "bar", "nested": {"ok": True}},
    }

    normalized = kpi_rollups.normalize_kpi_event(payload)
    assert normalized["event_name"] == "run_detail_view"
    assert normalized["visitor_id"] == "visitor-123"
    assert normalized["session_id"] == "session-456"
    assert normalized["run_id"] == "run-abc"
    assert normalized["event_id"] == 42
    assert normalized["surface"] == "run_detail_page"
    assert normalized["target"] == "focused_event"
    assert normalized["path"] == "/runs/run-abc"
    assert normalized["referrer"] == "https://example.test/share"
    assert normalized["event_metadata"]["foo"] == "bar"
    assert isinstance(normalized["event_metadata"]["nested"], dict)


def test_normalize_kpi_event_accepts_onboarding_events():
    normalized = kpi_rollups.normalize_kpi_event(
        {
            "event_name": "ONBOARDING_COMPLETED",
            "visitor_id": "visitor-onboarding-1",
            "surface": "onboarding_modal",
            "target": "open_dashboard",
            "metadata": {"version": "v1"},
        }
    )
    assert normalized["event_name"] == "onboarding_completed"
    assert normalized["visitor_id"] == "visitor-onboarding-1"
    assert normalized["surface"] == "onboarding_modal"
    assert normalized["target"] == "open_dashboard"


def test_normalize_kpi_event_rejects_unsupported_event():
    with pytest.raises(ValueError, match="unsupported event_name"):
        kpi_rollups.normalize_kpi_event(
            {"event_name": "unknown_event", "visitor_id": "visitor-1"}
        )


def test_record_kpi_event_rejects_when_ingest_disabled(monkeypatch):
    monkeypatch.setattr(kpi_rollups.settings, "KPI_EVENT_INGEST_ENABLED", False, raising=False)
    with pytest.raises(ValueError, match="disabled"):
        kpi_rollups.record_kpi_event(
            db=SimpleNamespace(),
            payload={"event_name": "landing_view", "visitor_id": "visitor-1"},
        )
