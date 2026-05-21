"""Public report artifact list/download API."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import RunReportArtifact, SimulationRun
from app.services.report_artifacts import (
    ensure_artifact_path,
    load_json_artifact,
    reports_root,
    resolve_registered_artifact_path,
)
from app.services.runtime_config import runtime_config_service

router = APIRouter()
logger = logging.getLogger(__name__)

RUN_ARTIFACT_TYPES = (
    "technical_report",
    "approachable_report",
    "viewer_brief",
    "planner_report",
    "run_summary",
)
FORMATS = ("json", "markdown")
PUBLIC_CANARY_K_SERIES_RE = re.compile(r"(^|[_-])k\d+($|[_-])")


def _reports_root() -> Path:
    return reports_root()


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


def _serialize_run_metadata(row: SimulationRun | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "run_id": str(row.run_id),
        "run_mode": str(row.run_mode),
        "protocol_version": str(row.protocol_version or "").strip() or None,
        "condition_name": str(row.condition_name or "").strip() or None,
        "hypothesis_id": str(row.hypothesis_id or "").strip() or None,
        "season_id": str(row.season_id or "").strip() or None,
        "season_number": int(row.season_number) if row.season_number is not None else None,
        "parent_run_id": str(row.parent_run_id or "").strip() or None,
        "epoch_id": str(row.epoch_id or "").strip() or None,
        "run_class": str(row.run_class or "").strip() or None,
        "protocol_deviation": bool(row.protocol_deviation),
        "deviation_reason": str(row.deviation_reason or "").strip() or None,
        "tuning_run": bool(row.protocol_deviation and str(row.deviation_reason or "").strip() == "tuning_run"),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
    }


def _parse_datetime(value: Any) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_hours(started_at: Any, ended_at: Any) -> float | None:
    start_dt = _parse_datetime(started_at)
    end_dt = _parse_datetime(ended_at)
    if start_dt is None or end_dt is None or end_dt < start_dt:
        return None
    return round((end_dt - start_dt).total_seconds() / 3600, 2)


def _is_public_canary_run(row: SimulationRun | None) -> bool:
    if row is None:
        return False
    run_class = str(row.run_class or "").strip()
    if run_class != "special_exploratory":
        return False
    condition_name = str(row.condition_name or "").strip().lower()
    run_id = str(row.run_id or "").strip().lower()
    has_public_marker = "public_canary" in condition_name or "public-canary" in condition_name
    has_k_series_marker = bool(
        PUBLIC_CANARY_K_SERIES_RE.search(condition_name)
        or PUBLIC_CANARY_K_SERIES_RE.search(run_id)
    )
    return has_public_marker or has_k_series_marker


def _clean_archive_teaser_text(value: Any, *, max_length: int) -> str:
    text_value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text_value) <= max_length:
        return text_value
    truncated = text_value[: max_length + 1].rsplit(" ", 1)[0].strip()
    return f"{truncated}..." if truncated else text_value[:max_length].strip()


def _first_viewer_brief_section_paragraph(payload: dict[str, Any], heading: str) -> str:
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return ""
    normalized_heading = heading.strip().lower()
    for section in sections:
        if not isinstance(section, dict):
            continue
        if str(section.get("heading") or "").strip().lower() != normalized_heading:
            continue
        paragraphs = section.get("paragraphs")
        if not isinstance(paragraphs, list):
            return ""
        for paragraph in paragraphs:
            clean_paragraph = _clean_archive_teaser_text(paragraph, max_length=360)
            if clean_paragraph:
                return clean_paragraph
    return ""


def _viewer_brief_archive_teaser(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    headline = _first_viewer_brief_section_paragraph(payload, "Headline")
    lead = _first_viewer_brief_section_paragraph(payload, "The Lead")
    teaser: dict[str, str] = {}
    if headline:
        teaser["viewer_brief_headline"] = _clean_archive_teaser_text(headline, max_length=140)
    if lead:
        teaser["viewer_brief_lead"] = lead
    return teaser


def _fallback_archive_summary(row: RunReportArtifact) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    updated_at = row.updated_at.isoformat() if row.updated_at else None
    return {
        "run_id": str(row.run_id or "").strip(),
        "condition_name": str(metadata.get("condition_name") or "").strip() or None,
        "season_number": metadata.get("season_number"),
        "run_class": None,
        "replicate_count": int(metadata.get("replicate_count") or 1),
        "generated_at_utc": updated_at,
        "run_started_at": None,
        "run_ended_at": updated_at,
        "duration_hours": None,
        "metrics": {
            "total_events": 0,
            "llm_calls": 0,
            "deaths": 0,
            "laws_passed": 0,
            "estimated_cost_usd": 0.0,
        },
        "sort_key": row.updated_at.timestamp() if row.updated_at else 0,
        "artifact_summary_missing": True,
    }


def _load_archive_json_artifact(row: RunReportArtifact) -> dict[str, Any] | None:
    """Read archive-list JSON without regenerating stale artifacts on the request path."""
    try:
        artifact_path = resolve_registered_artifact_path(str(row.artifact_path or ""))
    except ValueError:
        return None
    if not artifact_path.exists() or not artifact_path.is_file():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Unable to parse archive artifact JSON run_id=%s type=%s path=%s: %s",
            str(row.run_id or ""),
            str(row.artifact_type or ""),
            str(artifact_path),
            exc,
        )
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_download_path(raw_path: str) -> Path:
    try:
        artifact_path = resolve_registered_artifact_path(str(raw_path or ""))
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


def _artifact_media_type(artifact_format: str, *, inline_view: bool = False) -> str:
    _ = inline_view
    return "application/json" if artifact_format == "json" else "text/markdown"


def _find_run_artifact(
    db: Session,
    *,
    run_id: str,
    artifact_type: str,
    artifact_format: str,
) -> RunReportArtifact | None:
    return (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.run_id == run_id,
            RunReportArtifact.artifact_type == artifact_type,
            RunReportArtifact.artifact_format == artifact_format,
            RunReportArtifact.status == "completed",
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .first()
    )


def _find_condition_artifact(
    db: Session,
    *,
    condition_name: str,
    artifact_format: str,
) -> RunReportArtifact | None:
    condition_fragment_a = f'%\"condition_name\":\"{condition_name}\"%'
    condition_fragment_b = f'%\"condition_name\": \"{condition_name}\"%'
    return (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.artifact_type == "condition_comparison",
            RunReportArtifact.artifact_format == artifact_format,
            RunReportArtifact.status == "completed",
            or_(
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_a),
                cast(RunReportArtifact.metadata_json, String).like(condition_fragment_b),
            ),
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .first()
    )


def _artifact_response(
    db: Session,
    row: RunReportArtifact,
    *,
    content_disposition_type: str,
) -> FileResponse:
    artifact_format = str(row.artifact_format or "").strip()
    artifact_path = ensure_artifact_path(db, row)
    if artifact_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found")
    return FileResponse(
        path=str(artifact_path),
        filename=artifact_path.name,
        media_type=_artifact_media_type(
            artifact_format,
            inline_view=content_disposition_type == "inline",
        ),
        content_disposition_type=content_disposition_type,
    )


@router.get("/archive/runs")
def list_archived_runs(
    limit: int = Query(24, ge=1, le=200),
    include_tuning: bool = Query(False),
    db: Session = Depends(get_db),
):
    simulation_active = bool(runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE"))
    simulation_paused = bool(runtime_config_service.get_effective_value_cached("SIMULATION_PAUSED"))
    active_run_id = (
        str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip() or None
        if simulation_active and not simulation_paused
        else None
    )

    summary_rows = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.artifact_type == "run_summary",
            RunReportArtifact.artifact_format == "json",
            RunReportArtifact.status == "completed",
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .all()
    )

    summary_by_run: dict[str, dict[str, Any]] = {}
    for row in summary_rows:
        clean_run_id = str(row.run_id or "").strip()
        if not clean_run_id or clean_run_id == active_run_id or clean_run_id in summary_by_run:
            continue
        payload = _load_archive_json_artifact(row)
        if not isinstance(payload, dict):
            summary_by_run[clean_run_id] = _fallback_archive_summary(row)
            continue
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        run_ended_at = payload.get("run_ended_at") or payload.get("generated_at_utc") or (
            row.updated_at.isoformat() if row.updated_at else None
        )
        raw_season_number = payload.get("season_number")
        summary_by_run[clean_run_id] = {
            "run_id": clean_run_id,
            "condition_name": str(payload.get("condition_name") or "").strip() or None,
            "season_number": (
                int(raw_season_number)
                if raw_season_number is not None and str(raw_season_number).strip() != ""
                else None
            ),
            "run_class": str(payload.get("run_class") or "").strip() or None,
            "replicate_count": int(payload.get("replicate_count") or 1),
            "generated_at_utc": payload.get("generated_at_utc"),
            "run_started_at": payload.get("run_started_at"),
            "run_ended_at": run_ended_at,
            "duration_hours": _duration_hours(payload.get("run_started_at"), payload.get("run_ended_at")),
            "metrics": {
                "total_events": int(metrics.get("total_events") or 0),
                "llm_calls": int(metrics.get("llm_calls") or 0),
                "deaths": int(metrics.get("deaths") or 0),
                "laws_passed": int(metrics.get("laws_passed") or 0),
                "estimated_cost_usd": float(metrics.get("estimated_cost_usd") or 0.0),
            },
            "sort_key": (
                (_parse_datetime(run_ended_at) or _parse_datetime(payload.get("generated_at_utc")) or row.updated_at).timestamp()
                if (_parse_datetime(run_ended_at) or _parse_datetime(payload.get("generated_at_utc")) or row.updated_at)
                else 0
            ),
        }

    run_ids = list(summary_by_run.keys())
    if not run_ids:
        return {
            "active_run_id": active_run_id,
            "count": 0,
            "stats": {
                "completed_runs": 0,
                "total_events": 0,
                "llm_calls": 0,
                "deaths": 0,
                "estimated_cost_usd": 0.0,
            },
            "items": [],
        }

    artifact_rows = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.run_id.in_(run_ids),
            RunReportArtifact.status == "completed",
            RunReportArtifact.artifact_type.in_(RUN_ARTIFACT_TYPES),
            RunReportArtifact.artifact_format.in_(FORMATS),
        )
        .order_by(RunReportArtifact.updated_at.desc(), RunReportArtifact.id.desc())
        .all()
    )
    run_rows = (
        db.query(SimulationRun)
        .filter(SimulationRun.run_id.in_(run_ids))
        .all()
    )
    run_registry = {str(row.run_id): row for row in run_rows}

    artifacts_by_run: dict[str, dict[str, dict[str, Any]]] = {}
    for row in artifact_rows:
        run_bucket = artifacts_by_run.setdefault(str(row.run_id), {})
        artifact_bucket = run_bucket.setdefault(
            str(row.artifact_type),
            {"available": True, "formats": [], "updated_at": None},
        )
        artifact_format = str(row.artifact_format or "").strip()
        if artifact_format and artifact_format not in artifact_bucket["formats"]:
            artifact_bucket["formats"].append(artifact_format)
        if artifact_bucket["updated_at"] is None and row.updated_at:
            artifact_bucket["updated_at"] = row.updated_at.isoformat()
        if str(row.artifact_type) == "viewer_brief" and artifact_format == "json":
            summary = summary_by_run.get(str(row.run_id))
            if summary is not None:
                teaser = _viewer_brief_archive_teaser(_load_archive_json_artifact(row))
                if teaser:
                    summary.update(teaser)

    hidden_tuning_count = 0
    items = []
    for run_id, summary in summary_by_run.items():
        run_row = run_registry.get(run_id)
        is_tuning = bool(
            run_row
            and bool(run_row.protocol_deviation)
            and str(run_row.deviation_reason or "").strip() == "tuning_run"
        )
        is_public_canary = _is_public_canary_run(run_row)
        if is_tuning and not is_public_canary and not include_tuning:
            hidden_tuning_count += 1
            continue
        items.append(
            {
                "run_id": run_id,
                "summary": {
                    key: value
                    for key, value in summary.items()
                    if key != "sort_key"
                },
                "run_metadata": _serialize_run_metadata(run_row),
                "artifacts": artifacts_by_run.get(run_id, {}),
            }
        )
    items.sort(
        key=lambda item: float(summary_by_run.get(item["run_id"], {}).get("sort_key") or 0),
        reverse=True,
    )
    visible_items = items[:limit]

    return {
        "active_run_id": active_run_id,
        "count": len(items),
        "hidden_tuning_count": hidden_tuning_count,
        "stats": {
            "completed_runs": len(items),
            "total_events": sum(int(item["summary"]["metrics"]["total_events"]) for item in items),
            "llm_calls": sum(int(item["summary"]["metrics"]["llm_calls"]) for item in items),
            "deaths": sum(int(item["summary"]["metrics"]["deaths"]) for item in items),
            "estimated_cost_usd": round(
                sum(float(item["summary"]["metrics"]["estimated_cost_usd"]) for item in items),
                4,
            ),
        },
        "items": visible_items,
    }


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

    row = _find_run_artifact(db, run_id=clean_run_id, artifact_type=clean_type, artifact_format=clean_format)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return _artifact_response(db, row, content_disposition_type="attachment")


@router.get("/runs/{run_id}/view")
def view_run_report(
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

    row = _find_run_artifact(db, run_id=clean_run_id, artifact_type=clean_type, artifact_format=clean_format)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return _artifact_response(db, row, content_disposition_type="inline")


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

    row = _find_condition_artifact(db, condition_name=clean_condition, artifact_format=clean_format)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return _artifact_response(db, row, content_disposition_type="attachment")


@router.get("/conditions/{condition_name}/view")
def view_condition_comparison_report(
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

    row = _find_condition_artifact(db, condition_name=clean_condition, artifact_format=clean_format)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    return _artifact_response(db, row, content_disposition_type="inline")
