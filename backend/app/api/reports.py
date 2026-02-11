"""Public report artifact list/download API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import RunReportArtifact

router = APIRouter()

RUN_ARTIFACT_TYPES = (
    "technical_report",
    "approachable_report",
    "planner_report",
    "run_summary",
)
FORMATS = ("json", "markdown")


def _reports_root() -> Path:
    return Path(__file__).resolve().parents[3] / "output" / "reports"


def _serialize_artifact(row: RunReportArtifact) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return {
        "id": int(row.id),
        "run_id": str(row.run_id),
        "artifact_type": str(row.artifact_type),
        "artifact_format": str(row.artifact_format),
        "status": str(row.status),
        "artifact_path": str(row.artifact_path),
        "template_version": str(row.template_version or "").strip() or None,
        "generator_version": str(row.generator_version or "").strip() or None,
        "metadata": metadata,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _resolve_download_path(raw_path: str) -> Path:
    artifact_path = Path(str(raw_path or "")).expanduser().resolve()
    reports_root = _reports_root().resolve()
    try:
        artifact_path.relative_to(reports_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Artifact path is outside reports root",
        )
    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact file not found",
        )
    return artifact_path


@router.get("/runs/{run_id}")
def list_run_reports(
    run_id: str,
    db: Session = Depends(get_db),
):
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run_id is required")

    rows = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.run_id == clean_run_id,
            RunReportArtifact.status == "completed",
            RunReportArtifact.artifact_type.in_(RUN_ARTIFACT_TYPES),
            RunReportArtifact.artifact_format.in_(FORMATS),
        )
        .order_by(RunReportArtifact.artifact_type.asc(), RunReportArtifact.artifact_format.asc())
        .all()
    )
    return {
        "run_id": clean_run_id,
        "count": len(rows),
        "items": [_serialize_artifact(row) for row in rows],
    }


@router.get("/runs/{run_id}/download")
def download_run_report(
    run_id: str,
    artifact_type: str = Query(...),
    artifact_format: str = Query(..., alias="format"),
    db: Session = Depends(get_db),
):
    clean_run_id = str(run_id or "").strip()
    clean_type = str(artifact_type or "").strip()
    clean_format = str(artifact_format or "").strip()
    if clean_type not in RUN_ARTIFACT_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported artifact_type")
    if clean_format not in FORMATS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported format")

    row = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.run_id == clean_run_id,
            RunReportArtifact.artifact_type == clean_type,
            RunReportArtifact.artifact_format == clean_format,
            RunReportArtifact.status == "completed",
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    artifact_path = _resolve_download_path(str(row.artifact_path))
    media_type = "application/json" if clean_format == "json" else "text/markdown; charset=utf-8"
    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        media_type=media_type,
    )


@router.get("/conditions/{condition_name}")
def list_condition_comparison_reports(
    condition_name: str,
    db: Session = Depends(get_db),
):
    clean_condition = str(condition_name or "").strip().lower()
    if not clean_condition:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="condition_name is required")

    condition_fragment_a = f'%\"condition_name\":\"{clean_condition}\"%'
    condition_fragment_b = f'%\"condition_name\": \"{clean_condition}\"%'
    rows = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.artifact_type == "condition_comparison",
            RunReportArtifact.artifact_format.in_(FORMATS),
            RunReportArtifact.status == "completed",
            or_(
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_a),
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_b),
            ),
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .all()
    )

    return {
        "condition_name": clean_condition,
        "count": len(rows),
        "items": [_serialize_artifact(row) for row in rows],
    }


@router.get("/conditions/{condition_name}/download")
def download_condition_comparison_report(
    condition_name: str,
    artifact_format: str = Query(..., alias="format"),
    db: Session = Depends(get_db),
):
    clean_condition = str(condition_name or "").strip().lower()
    clean_format = str(artifact_format or "").strip()
    if not clean_condition:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="condition_name is required")
    if clean_format not in FORMATS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported format")

    condition_fragment_a = f'%\"condition_name\":\"{clean_condition}\"%'
    condition_fragment_b = f'%\"condition_name\": \"{clean_condition}\"%'
    row = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.artifact_type == "condition_comparison",
            RunReportArtifact.artifact_format == clean_format,
            RunReportArtifact.status == "completed",
            or_(
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_a),
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_b),
            ),
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    artifact_path = _resolve_download_path(str(row.artifact_path))
    media_type = "application/json" if clean_format == "json" else "text/markdown; charset=utf-8"
    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        media_type=media_type,
    )
