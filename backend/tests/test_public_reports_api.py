from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.models import RunReportArtifact

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

    assert list_response.status_code == 200
    body = list_response.json()
    assert body["run_id"] == "run-1"
    assert body["count"] == 1
    assert body["items"][0]["artifact_type"] == "run_summary"

    assert download_response.status_code == 200
    assert '"ok":true' in download_response.text


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

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["condition_name"] == "baseline_v1"
    assert payload["count"] == 2

    assert download_response.status_code == 200
    assert "# baseline" in download_response.text


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
