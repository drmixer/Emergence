from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import RunReportArtifact, SimulationRun

reports_api = importlib.import_module("app.api.reports")
report_artifacts = importlib.import_module("app.services.report_artifacts")


@pytest.fixture
def reports_client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    RunReportArtifact.__table__.create(bind=engine)
    SimulationRun.__table__.create(bind=engine)
    db_session = sessionmaker(bind=engine, future=True)()

    monkeypatch.setattr(reports_api, "_reports_root", lambda: Path(tmp_path))
    monkeypatch.setattr(report_artifacts, "reports_root", lambda: Path(tmp_path))

    app = FastAPI()
    app.include_router(reports_api.router, prefix="/api/reports")
    app.dependency_overrides[reports_api.get_db] = lambda: db_session
    client = TestClient(app)
    try:
        yield client, db_session, Path(tmp_path)
    finally:
        db_session.close()


def test_list_and_download_run_reports(reports_client):
    client, db_session, tmp_dir = reports_client
    artifact_file = tmp_dir / "runs" / "run-1" / "run_report_summary.json"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text('{"ok":true}\n', encoding="utf-8")

    db_session.add(
        RunReportArtifact(
            run_id="run-1",
            artifact_type="run_summary",
            artifact_format="json",
            artifact_path=str(artifact_file),
            status="completed",
            metadata_json={"condition_name": "baseline_v1"},
        )
    )
    db_session.commit()

    with client:
        list_response = client.get("/api/reports/runs/run-1")
        download_response = client.get(
            "/api/reports/runs/run-1/download",
            params={"artifact_type": "run_summary", "format": "json"},
        )
        view_response = client.get(
            "/api/reports/runs/run-1/view",
            params={"artifact_type": "run_summary", "format": "json"},
        )

    assert list_response.status_code == 200
    body = list_response.json()
    assert body["run_id"] == "run-1"
    assert body["count"] == 1
    assert body["items"][0]["artifact_type"] == "run_summary"

    assert download_response.status_code == 200
    assert download_response.headers["content-disposition"].startswith("attachment;")
    assert '"ok":true' in download_response.text

    assert view_response.status_code == 200
    assert view_response.headers["content-disposition"].startswith("inline;")
    assert view_response.headers["content-type"].startswith("application/json")
    assert '"ok":true' in view_response.text


def test_missing_story_artifact_regenerates_with_gemini_flag(reports_client, monkeypatch):
    _client, db_session, tmp_dir = reports_client
    missing_file = tmp_dir / "runs" / "run-1" / "approachable_report.json"
    row = RunReportArtifact(
        run_id="run-1",
        artifact_type="approachable_report",
        artifact_format="json",
        artifact_path=str(missing_file),
        status="completed",
        metadata_json={
            "condition_name": "baseline_v1",
            "season_number": 2,
            "story_generate_with_gemini": True,
        },
    )
    db_session.add(row)
    db_session.commit()
    calls: list[dict[str, object]] = []

    def _fake_rebuild_run_bundle(_db, **kwargs):
        calls.append(kwargs)
        missing_file.parent.mkdir(parents=True, exist_ok=True)
        missing_file.write_text('{"ok":true}\n', encoding="utf-8")

    monkeypatch.setattr(report_artifacts, "rebuild_run_bundle", _fake_rebuild_run_bundle)

    path = report_artifacts.ensure_artifact_path(db_session, row)

    assert path == missing_file
    assert calls[0]["run_id"] == "run-1"
    assert calls[0]["condition_name"] == "baseline_v1"
    assert calls[0]["season_number"] == 2
    assert calls[0]["generate_story_with_gemini"] is True


def test_list_and_download_condition_comparison_reports(reports_client):
    client, db_session, tmp_dir = reports_client
    json_file = tmp_dir / "conditions" / "baseline-v1" / "condition_comparison.json"
    md_file = tmp_dir / "conditions" / "baseline-v1" / "condition_comparison.md"
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text('{"condition":"baseline_v1"}\n', encoding="utf-8")
    md_file.write_text("# baseline\n", encoding="utf-8")

    db_session.add_all(
        [
            RunReportArtifact(
                run_id="condition-baseline-v1",
                artifact_type="condition_comparison",
                artifact_format="json",
                artifact_path=str(json_file),
                status="completed",
                metadata_json={"condition_name": "baseline_v1"},
            ),
            RunReportArtifact(
                run_id="condition-baseline-v1",
                artifact_type="condition_comparison",
                artifact_format="markdown",
                artifact_path=str(md_file),
                status="completed",
                metadata_json={"condition_name": "baseline_v1"},
            ),
        ]
    )
    db_session.commit()

    with client:
        list_response = client.get("/api/reports/conditions/baseline_v1")
        download_response = client.get(
            "/api/reports/conditions/baseline_v1/download",
            params={"format": "markdown"},
        )
        view_response = client.get(
            "/api/reports/conditions/baseline_v1/view",
            params={"format": "markdown"},
        )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["condition_name"] == "baseline_v1"
    assert payload["count"] == 2

    assert download_response.status_code == 200
    assert download_response.headers["content-disposition"].startswith("attachment;")
    assert "# baseline" in download_response.text

    assert view_response.status_code == 200
    assert view_response.headers["content-disposition"].startswith("inline;")
    assert view_response.headers["content-type"].startswith("text/markdown")
    assert "# baseline" in view_response.text


def test_download_run_report_regenerates_missing_artifact(reports_client, monkeypatch):
    client, db_session, tmp_dir = reports_client
    missing_file = tmp_dir / "runs" / "run-regenerate" / "technical_report.json"

    db_session.add(
        RunReportArtifact(
            run_id="run-regenerate",
            artifact_type="technical_report",
            artifact_format="json",
            artifact_path=str(missing_file),
            status="completed",
            metadata_json={"condition_name": "baseline_v1", "season_number": 2},
        )
    )
    db_session.commit()

    def _fake_rebuild_run_bundle(db, *, run_id, actor_id, condition_name=None, season_number=None):
        _ = db, actor_id, condition_name, season_number
        missing_file.parent.mkdir(parents=True, exist_ok=True)
        missing_file.write_text('{"regenerated": true}\n', encoding="utf-8")

    monkeypatch.setattr(reports_api, "ensure_artifact_path", lambda db, row: (  # type: ignore[arg-type]
        _fake_rebuild_run_bundle(
            db,
            run_id=row.run_id,
            actor_id="test",
            condition_name=(row.metadata_json or {}).get("condition_name"),
            season_number=(row.metadata_json or {}).get("season_number"),
        )
        or missing_file
    ))

    with client:
        response = client.get(
            "/api/reports/runs/run-regenerate/download",
            params={"artifact_type": "technical_report", "format": "json"},
        )

    assert response.status_code == 200
    assert '"regenerated": true' in response.text


def test_view_run_report_remaps_stale_absolute_reports_path(reports_client):
    client, db_session, tmp_dir = reports_client
    artifact_file = tmp_dir / "runs" / "run-stale-path" / "technical_report.md"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text("# remapped\n", encoding="utf-8")

    db_session.add(
        RunReportArtifact(
            run_id="run-stale-path",
            artifact_type="technical_report",
            artifact_format="markdown",
            artifact_path="/Users/operator/code/Emergence/output/reports/runs/run-stale-path/technical_report.md",
            status="completed",
            metadata_json={"condition_name": "baseline_v1"},
        )
    )
    db_session.commit()

    with client:
        response = client.get(
            "/api/reports/runs/run-stale-path/view",
            params={"artifact_type": "technical_report", "format": "markdown"},
        )

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("inline;")
    assert "# remapped" in response.text


def test_list_archived_runs_excludes_active_run_and_exposes_artifacts(reports_client, monkeypatch):
    client, db_session, tmp_dir = reports_client

    archived_summary_file = tmp_dir / "runs" / "run-archive-1" / "run_report_summary.json"
    archived_summary_file.parent.mkdir(parents=True, exist_ok=True)
    archived_summary_file.write_text(
        """
{
  "run_id": "run-archive-1",
  "condition_name": "baseline_v2",
  "season_number": 3,
  "run_class": "standard_72h",
  "replicate_count": 2,
  "generated_at_utc": "2026-04-08T03:30:00+00:00",
  "run_started_at": "2026-04-08T01:00:00+00:00",
  "run_ended_at": "2026-04-08T03:00:00+00:00",
  "metrics": {
    "total_events": 420,
    "llm_calls": 88,
    "deaths": 4,
    "laws_passed": 3,
    "estimated_cost_usd": 1.2345
  }
}
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    technical_file = tmp_dir / "runs" / "run-archive-1" / "technical_report.md"
    technical_file.write_text("# technical\n", encoding="utf-8")
    approachable_file = tmp_dir / "runs" / "run-archive-1" / "approachable_report.md"
    approachable_file.write_text("# approachable\n", encoding="utf-8")

    active_summary_file = tmp_dir / "runs" / "run-live-1" / "run_report_summary.json"
    active_summary_file.parent.mkdir(parents=True, exist_ok=True)
    active_summary_file.write_text('{"run_id":"run-live-1","metrics":{"total_events":10}}\n', encoding="utf-8")

    db_session.add_all(
        [
            SimulationRun(
                run_id="run-archive-1",
                run_mode="real",
                protocol_version="phase-2",
                condition_name="baseline_v2",
                season_number=3,
                run_class="standard_72h",
                carryover_agent_count=0,
                fresh_agent_count=50,
                protocol_deviation=False,
                started_at=datetime.fromisoformat("2026-04-08T01:00:00+00:00"),
                ended_at=datetime.fromisoformat("2026-04-08T03:00:00+00:00"),
            ),
            RunReportArtifact(
                run_id="run-archive-1",
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(archived_summary_file),
                status="completed",
            ),
            RunReportArtifact(
                run_id="run-archive-1",
                artifact_type="technical_report",
                artifact_format="markdown",
                artifact_path=str(technical_file),
                status="completed",
            ),
            RunReportArtifact(
                run_id="run-archive-1",
                artifact_type="approachable_report",
                artifact_format="markdown",
                artifact_path=str(approachable_file),
                status="completed",
            ),
            RunReportArtifact(
                run_id="run-live-1",
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(active_summary_file),
                status="completed",
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr(
        reports_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: (
            "run-live-1"
            if key == "SIMULATION_RUN_ID"
            else (True if key == "SIMULATION_ACTIVE" else (False if key == "SIMULATION_PAUSED" else None))
        ),
    )

    with client:
        response = client.get("/api/reports/archive/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_run_id"] == "run-live-1"
    assert payload["count"] == 1
    assert payload["stats"]["completed_runs"] == 1
    assert payload["stats"]["total_events"] == 420
    assert payload["stats"]["llm_calls"] == 88
    assert payload["stats"]["deaths"] == 4
    assert payload["stats"]["estimated_cost_usd"] == 1.2345
    assert payload["items"][0]["run_id"] == "run-archive-1"
    assert payload["items"][0]["summary"]["duration_hours"] == 2.0
    assert payload["items"][0]["run_metadata"]["condition_name"] == "baseline_v2"
    assert payload["items"][0]["artifacts"]["technical_report"]["formats"] == ["markdown"]
    assert payload["items"][0]["artifacts"]["approachable_report"]["formats"] == ["markdown"]


def test_list_archived_runs_hides_tuning_runs_by_default(reports_client, monkeypatch):
    client, db_session, tmp_dir = reports_client

    tuning_summary_file = tmp_dir / "runs" / "run-tuning-1" / "run_report_summary.json"
    tuning_summary_file.parent.mkdir(parents=True, exist_ok=True)
    tuning_summary_file.write_text(
        """
{
  "run_id": "run-tuning-1",
  "condition_name": "scarcity_canary_v1",
  "season_number": 0,
  "run_class": "special_exploratory",
  "replicate_count": 1,
  "generated_at_utc": "2026-04-08T03:30:00+00:00",
  "run_started_at": "2026-04-08T01:00:00+00:00",
  "run_ended_at": "2026-04-08T03:00:00+00:00",
  "metrics": {
    "total_events": 420,
    "llm_calls": 88,
    "deaths": 4,
    "laws_passed": 3,
    "estimated_cost_usd": 1.2345
  }
}
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    db_session.add_all(
        [
            SimulationRun(
                run_id="run-tuning-1",
                run_mode="real",
                protocol_version="phase-2",
                condition_name="scarcity_canary_v1",
                season_number=None,
                run_class="special_exploratory",
                carryover_agent_count=0,
                fresh_agent_count=50,
                protocol_deviation=True,
                deviation_reason="tuning_run",
                started_at=datetime.fromisoformat("2026-04-08T01:00:00+00:00"),
                ended_at=datetime.fromisoformat("2026-04-08T03:00:00+00:00"),
            ),
            RunReportArtifact(
                run_id="run-tuning-1",
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(tuning_summary_file),
                status="completed",
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr(
        reports_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: (False if key == "SIMULATION_ACTIVE" else (True if key == "SIMULATION_PAUSED" else None)),
    )

    with client:
        response = client.get("/api/reports/archive/runs")
        included_response = client.get("/api/reports/archive/runs?include_tuning=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["hidden_tuning_count"] == 1

    assert included_response.status_code == 200
    included_payload = included_response.json()
    assert included_payload["count"] == 1
    assert included_payload["items"][0]["run_metadata"]["tuning_run"] is True


def test_list_archived_runs_keeps_public_k_series_canaries_visible(reports_client, monkeypatch):
    client, db_session, tmp_dir = reports_client

    run_id = "real-20260517T220144Z"
    condition_name = "real_scarcity_executable_governance_20260517_canary_k11_high_floor_pressure_v1"
    summary_file = tmp_dir / "runs" / run_id / "run_report_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(
        f"""
{{
  "run_id": "{run_id}",
  "condition_name": "{condition_name}",
  "season_number": 0,
  "run_class": "special_exploratory",
  "replicate_count": 1,
  "generated_at_utc": "2026-05-18T03:30:00+00:00",
  "run_started_at": "2026-05-17T22:01:44+00:00",
  "run_ended_at": "2026-05-18T03:00:00+00:00",
  "metrics": {{
    "total_events": 100,
    "llm_calls": 20,
    "deaths": 1,
    "laws_passed": 2,
    "estimated_cost_usd": 0.5
  }}
}}
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    db_session.add_all(
        [
            SimulationRun(
                run_id=run_id,
                run_mode="real",
                protocol_version="phase-2",
                condition_name=condition_name,
                season_number=None,
                run_class="special_exploratory",
                carryover_agent_count=0,
                fresh_agent_count=50,
                protocol_deviation=True,
                deviation_reason="tuning_run",
                started_at=datetime.fromisoformat("2026-05-17T22:01:44+00:00"),
                ended_at=datetime.fromisoformat("2026-05-18T03:00:00+00:00"),
            ),
            RunReportArtifact(
                run_id=run_id,
                artifact_type="run_summary",
                artifact_format="json",
                artifact_path=str(summary_file),
                status="completed",
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr(
        reports_api.runtime_config_service,
        "get_effective_value_cached",
        lambda key: (False if key == "SIMULATION_ACTIVE" else (True if key == "SIMULATION_PAUSED" else None)),
    )

    with client:
        response = client.get("/api/reports/archive/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["hidden_tuning_count"] == 0
    assert payload["items"][0]["run_id"] == run_id
    assert payload["items"][0]["run_metadata"]["tuning_run"] is True
