"""Helpers for durable run-report artifact access."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import RunReportArtifact
from app.services.condition_reports import (
    UNKNOWN_CONDITION,
    generate_and_record_condition_comparison,
    generate_and_record_run_summary,
)
from app.services.run_reports import rebuild_run_bundle

logger = logging.getLogger(__name__)

REPORT_REBUILD_ACTOR_ID = "report-artifact-rebuilder"


def reports_root() -> Path:
    return Path(__file__).resolve().parents[3] / "output" / "reports"


def resolve_registered_artifact_path(raw_path: str) -> Path:
    artifact_path = Path(str(raw_path or "")).expanduser().resolve()
    root = reports_root().resolve()
    try:
        artifact_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact path is outside reports root") from exc
    return artifact_path


def _regenerate_artifact(db: Session, row: RunReportArtifact) -> RunReportArtifact | None:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    artifact_type = str(row.artifact_type or "").strip()

    try:
        if artifact_type in {"technical_report", "approachable_report", "planner_report"}:
            rebuild_run_bundle(
                db,
                run_id=str(row.run_id or "").strip(),
                actor_id=REPORT_REBUILD_ACTOR_ID,
                condition_name=metadata.get("condition_name"),
                season_number=metadata.get("season_number"),
            )
        elif artifact_type == "run_summary":
            generate_and_record_run_summary(
                db,
                run_id=str(row.run_id or "").strip(),
                condition_name=metadata.get("condition_name"),
                season_number=metadata.get("season_number"),
            )
        elif artifact_type == "condition_comparison":
            condition_name = str(metadata.get("condition_name") or "").strip()
            if not condition_name or condition_name == UNKNOWN_CONDITION:
                return None
            generate_and_record_condition_comparison(
                db,
                condition_name=condition_name,
                season_number=metadata.get("season_number"),
            )
        else:
            return None
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Failed to regenerate artifact run_id=%s type=%s format=%s: %s",
            str(row.run_id or ""),
            artifact_type,
            str(row.artifact_format or ""),
            exc,
        )
        return None

    return db.query(RunReportArtifact).filter(RunReportArtifact.id == row.id).first()


def ensure_artifact_path(db: Session, row: RunReportArtifact) -> Path | None:
    try:
        artifact_path = resolve_registered_artifact_path(str(row.artifact_path or ""))
    except ValueError:
        return None

    if artifact_path.exists() and artifact_path.is_file():
        return artifact_path

    refreshed = _regenerate_artifact(db, row)
    if refreshed is None:
        return None

    try:
        artifact_path = resolve_registered_artifact_path(str(refreshed.artifact_path or ""))
    except ValueError:
        return None

    if artifact_path.exists() and artifact_path.is_file():
        return artifact_path
    return None


def load_json_artifact(db: Session, row: RunReportArtifact) -> dict[str, Any] | None:
    artifact_path = ensure_artifact_path(db, row)
    if artifact_path is None:
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Unable to parse artifact JSON run_id=%s type=%s path=%s: %s",
            str(row.run_id or ""),
            str(row.artifact_type or ""),
            str(artifact_path),
            exc,
        )
        return None
    return payload if isinstance(payload, dict) else None
