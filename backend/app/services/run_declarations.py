"""Declared run framing used by public report generation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from app.models.models import SimulationRun


@dataclass(frozen=True)
class RunDeclaration:
    declared_question: str
    watch_for: str | None = None
    claim_boundary: str | None = None
    source: str = "static_schedule"


RUN_DECLARATIONS: tuple[dict[str, str], ...] = (
    {
        "run_id": "real-20260517T220144Z",
        "condition_name": "real_scarcity_executable_governance_20260517_canary_k11_high_floor_pressure_v1",
        "declared_question": "Can the public run pipeline produce visible survival, governance, and post-run evidence?",
        "watch_for": "This was a pipeline canary; the key outcome is whether viewers can understand what happened after the run.",
        "claim_boundary": "Exploratory public canary; not finished research.",
    },
    {
        "run_id": "real-20260519T063000Z",
        "condition_name": "real_scarcity_viewer_wrapper_20260519_canary_k12_high_floor_pressure_v1",
        "declared_question": "Do the new viewer/story/evidence changes make a live run easier to follow?",
        "watch_for": "Watch proposal discussion readability, pile-on reduction, and whether post-run story surfaces identify meaningful moments without work-event noise.",
        "claim_boundary": "Exploratory public canary; non-claim-bearing.",
    },
)


QUESTION_KEYS = ("declared_question", "declaredQuestion", "question")
WATCH_KEYS = ("watch_for", "watchFor", "what_to_watch_for", "whatToWatchFor")
BOUNDARY_KEYS = ("claim_boundary", "claimBoundary")


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _extract_json_field(raw_text: str, keys: tuple[str, ...]) -> str:
    clean = str(raw_text or "").strip()
    if not clean:
        return ""
    try:
        parsed = json.loads(clean)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        for key in keys:
            value = _clean_text(parsed.get(key))
            if value:
                return value

    for key in keys:
        pattern = rf"{re.escape(key)}\s*[:=]\s*[\"']?(.+?)(?:[\"']?\s*(?:,|$)|\n)"
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            value = _clean_text(match.group(1))
            if value:
                return value
    return ""


def _declaration_from_run_row(run_row: SimulationRun | None) -> RunDeclaration | None:
    if run_row is None:
        return None
    candidate_fields = [
        getattr(run_row, "start_reason", None),
        getattr(run_row, "end_reason", None),
        getattr(run_row, "deviation_reason", None),
    ]
    for raw_text in candidate_fields:
        declared_question = _extract_json_field(str(raw_text or ""), QUESTION_KEYS)
        if declared_question:
            return RunDeclaration(
                declared_question=declared_question,
                watch_for=_extract_json_field(str(raw_text or ""), WATCH_KEYS) or None,
                claim_boundary=_extract_json_field(str(raw_text or ""), BOUNDARY_KEYS) or None,
                source="simulation_run_metadata",
            )
    return None


def resolve_run_declaration(
    *,
    run_id: str,
    condition_name: str | None = None,
    run_row: SimulationRun | None = None,
) -> RunDeclaration | None:
    """Resolve declared public framing without inferring it from metrics."""

    from_row = _declaration_from_run_row(run_row)
    if from_row is not None:
        return from_row

    clean_run_id = _clean_text(run_id)
    clean_condition = _clean_text(condition_name).lower()
    for item in RUN_DECLARATIONS:
        if clean_run_id and clean_run_id == item.get("run_id"):
            return RunDeclaration(
                declared_question=item["declared_question"],
                watch_for=item.get("watch_for") or None,
                claim_boundary=item.get("claim_boundary") or None,
                source="static_schedule",
            )
        if clean_condition and clean_condition == _clean_text(item.get("condition_name")).lower():
            return RunDeclaration(
                declared_question=item["declared_question"],
                watch_for=item.get("watch_for") or None,
                claim_boundary=item.get("claim_boundary") or None,
                source="static_schedule",
            )
    return None
