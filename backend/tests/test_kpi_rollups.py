from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import now_utc
from app.models.models import KpiDailyRollup, KpiEvent
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


def test_normalize_kpi_event_accepts_viewer_journey_events():
    for event_name in (
        "calendar_view",
        "archive_view",
        "run_path_click",
        "run_replay_tab_open",
        "evidence_filter_used",
        "raw_evidence_toggle",
        "report_opened",
        "watch_replay_view",
        "watch_lane_focus",
        "watch_spike_jump",
        "watch_spike_step",
        "watch_selected_moment_click",
    ):
        normalized = kpi_rollups.normalize_kpi_event(
            {
                "event_name": event_name.upper(),
                "visitor_id": "visitor-viewer-1",
                "run_id": "k12-public-canary",
                "surface": "run_calendar",
                "target": "k12",
            }
        )
        assert normalized["event_name"] == event_name
        assert normalized["visitor_id"] == "visitor-viewer-1"


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


def test_get_recent_rollups_attaches_onboarding_metrics():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiEvent.__table__.create(bind=engine)
    KpiDailyRollup.__table__.create(bind=engine)
    session = sessionmaker(bind=engine, future=True)()

    day_key = date(2026, 2, 10)
    session.add(KpiDailyRollup(day_key=day_key, landing_views=10))
    session.add_all(
        [
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="onboarding_shown",
                visitor_id="visitor-1",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="onboarding_shown",
                visitor_id="visitor-2",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="onboarding_completed",
                visitor_id="visitor-1",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="onboarding_skipped",
                visitor_id="visitor-2",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="onboarding_glossary_opened",
                visitor_id="visitor-2",
            ),
        ]
    )
    session.commit()

    payload = kpi_rollups.get_recent_rollups(session, days=7, refresh=False)
    latest = payload["summary"]["latest"]
    seven_day = payload["summary"]["seven_day_avg"]

    assert latest["onboarding_shown_visitors"] == 2
    assert latest["onboarding_completed_visitors"] == 1
    assert latest["onboarding_skipped_visitors"] == 1
    assert latest["onboarding_glossary_opened_visitors"] == 1
    assert latest["onboarding_completion_rate"] == pytest.approx(0.5)
    assert latest["onboarding_skip_rate"] == pytest.approx(0.5)
    assert latest["onboarding_glossary_open_rate"] == pytest.approx(0.5)
    assert seven_day["onboarding_completion_rate"] == pytest.approx(0.5)
    assert seven_day["onboarding_skip_rate"] == pytest.approx(0.5)
    assert seven_day["onboarding_glossary_open_rate"] == pytest.approx(0.5)

    session.close()


def test_get_recent_rollups_attaches_viewer_journey_metrics():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiEvent.__table__.create(bind=engine)
    KpiDailyRollup.__table__.create(bind=engine)
    session = sessionmaker(bind=engine, future=True)()

    day_key = date(2026, 2, 11)
    session.add(KpiDailyRollup(day_key=day_key, landing_views=10))
    session.add_all(
        [
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="calendar_view",
                visitor_id="visitor-1",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="calendar_view",
                visitor_id="visitor-2",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="run_path_click",
                visitor_id="visitor-1",
                target="current_run",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="run_replay_tab_open",
                visitor_id="visitor-1",
                target="evidence",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="evidence_filter_used",
                visitor_id="visitor-1",
                target="governance",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="raw_evidence_toggle",
                visitor_id="visitor-2",
            ),
            KpiEvent(
                day_key=day_key,
                occurred_at=now_utc(),
                event_name="report_opened",
                visitor_id="visitor-1",
                target="approachable_report",
            ),
        ]
    )
    session.commit()

    payload = kpi_rollups.get_recent_rollups(session, days=7, refresh=False)
    latest = payload["summary"]["latest"]
    seven_day = payload["summary"]["seven_day_avg"]

    assert latest["calendar_view_visitors"] == 2
    assert latest["run_path_click_visitors"] == 1
    assert latest["run_replay_tab_open_visitors"] == 1
    assert latest["evidence_filter_used_visitors"] == 1
    assert latest["raw_evidence_toggle_visitors"] == 1
    assert latest["report_open_visitors"] == 1
    assert latest["story_report_open_visitors"] == 1
    assert seven_day["calendar_view_visitors"] == 2
    assert seven_day["story_report_open_visitors"] == 1

    session.close()
