from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import Agent, Event, RunReportArtifact

analytics_api = importlib.import_module("app.api.analytics")


@pytest.fixture
def summary_session_factory(tmp_path):
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Agent.__table__.create(bind=engine)
    Event.__table__.create(bind=engine)
    RunReportArtifact.__table__.create(bind=engine)
    return sessionmaker(bind=engine, future=True), Path(tmp_path)


def _write_run_summary_artifact(tmp_dir: Path, *, run_id: str, payload: dict) -> Path:
    artifact_path = tmp_dir / "runs" / run_id / "run_report_summary.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return artifact_path


def test_get_latest_summary_prefers_daily_summary(monkeypatch, summary_session_factory):
    SessionLocal, tmp_dir = summary_session_factory
    with SessionLocal() as db:
        db.add(
            Event(
                event_type="daily_summary",
                description="Day 3 Summary",
                event_metadata={
                    "day_number": 3,
                    "summary": "Daily summary text.",
                    "stats": {"messages": 12, "votes": 4, "laws_passed": 1},
                },
                created_at=datetime(2026, 2, 12, 8, 0, tzinfo=timezone.utc),
            )
        )

        artifact_payload = {
            "run_id": "run-fallback",
            "generated_at_utc": "2026-02-12T07:00:00+00:00",
            "condition_name": "baseline_v1",
            "replicate_count": 1,
            "metrics": {"total_events": 900, "llm_calls": 400},
        }
        artifact_path = _write_run_summary_artifact(tmp_dir, run_id="run-fallback", payload=artifact_payload)
        db.add(
            RunReportArtifact(
                run_id="run-fallback",
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(artifact_path),
                status="completed",
            )
        )
        db.commit()

    monkeypatch.setattr(analytics_api, "SessionLocal", SessionLocal)
    payload = analytics_api.get_latest_summary()

    assert payload["source"] == "daily_summary"
    assert payload["day_number"] == 3
    assert payload["summary"] == "Daily summary text."


def test_get_latest_summary_uses_run_summary_fallback(monkeypatch, summary_session_factory):
    SessionLocal, tmp_dir = summary_session_factory
    with SessionLocal() as db:
        artifact_payload = {
            "run_id": "run-20260211T063855Z",
            "generated_at_utc": "2026-02-12T06:12:00+00:00",
            "condition_name": "pilot_real_8h",
            "replicate_count": 1,
            "metrics": {
                "total_events": 11155,
                "llm_calls": 1286,
                "proposal_actions": 12,
                "vote_actions": 299,
                "forum_actions": 54,
                "laws_passed": 0,
            },
        }
        artifact_path = _write_run_summary_artifact(
            tmp_dir,
            run_id="run-20260211T063855Z",
            payload=artifact_payload,
        )
        db.add(
            RunReportArtifact(
                run_id="run-20260211T063855Z",
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(artifact_path),
                status="completed",
            )
        )
        db.commit()

    monkeypatch.setattr(analytics_api, "SessionLocal", SessionLocal)
    payload = analytics_api.get_latest_summary()

    assert payload["source"] == "run_summary_fallback"
    assert payload["run_id"] == "run-20260211T063855Z"
    assert payload["condition_name"] == "pilot_real_8h"
    assert payload["stats"]["total_events"] == 11155
    assert payload["stats"]["llm_calls"] == 1286
    assert "fallback summary" in payload["summary"]
