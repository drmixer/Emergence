"""Run summary export and condition comparison helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import statistics
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.models import SimulationRun

UNKNOWN_CONDITION = "unknown"

CORE_METRICS = (
    ("llm_calls", "LLM Calls"),
    ("estimated_cost_usd", "Estimated Cost (USD)"),
    ("total_events", "Total Events"),
    ("proposal_actions", "Proposal Actions"),
    ("vote_actions", "Vote Actions"),
    ("laws_passed", "Laws Passed"),
    ("deaths", "Deaths"),
    ("conflict_events", "Conflict Events"),
    ("cooperation_events", "Cooperation Events"),
)

CONFLICT_EVENT_TYPES = {
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "vote_enforcement",
    "enforcement_initiated",
    "agent_sanctioned",
    "resources_seized",
    "agent_exiled",
}
COOPERATION_EVENT_TYPES = {
    "trade",
    "direct_message",
    "forum_reply",
    "forum_post",
    "agent_revived",
}


def _coerce_run_id(run_id: str) -> str:
    clean = str(run_id or "").strip()
    if not clean:
        raise ValueError("run_id is required")
    return clean


def _coerce_condition_name(condition_name: str | None) -> str:
    clean = str(condition_name or "").strip().lower()
    return clean or UNKNOWN_CONDITION


def _resolve_run_registry_row(db: Session, *, run_id: str) -> SimulationRun | None:
    return db.query(SimulationRun).filter(SimulationRun.run_id == str(run_id)).first()


def _resolve_run_window(db: Session, *, run_id: str, run_row: SimulationRun | None) -> tuple[Any, Any]:
    def _coerce_datetime(value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        text_value = str(value or "").strip()
        if not text_value:
            return None
        try:
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    if run_row is not None and run_row.started_at is not None:
        started_at = run_row.started_at
    else:
        started_at = db.execute(
            text("SELECT MIN(created_at) FROM llm_usage WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
    started_at = _coerce_datetime(started_at)

    if started_at is None:
        started_at = now_utc() - timedelta(hours=24)

    if run_row is not None and run_row.ended_at is not None:
        ended_at = run_row.ended_at
    else:
        ended_at = db.execute(
            text("SELECT MAX(created_at) FROM llm_usage WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
    ended_at = _coerce_datetime(ended_at)

    if ended_at is None:
        ended_at = now_utc()
    if ended_at < started_at:
        ended_at = started_at
    return started_at, ended_at


def _event_counts_for_run(db: Session, *, run_id: str, started_at: Any, ended_at: Any) -> dict[str, int]:
    run_fragment = f'%"{run_id}"%'
    rows = db.execute(
        text(
            """
            SELECT e.event_type, COUNT(*) AS count
            FROM events e
            WHERE e.created_at >= :started_at
              AND e.created_at <= :ended_at
              AND (
                e.agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
                OR CAST(e.event_metadata AS TEXT) LIKE :run_fragment
              )
            GROUP BY e.event_type
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).fetchall()

    return {
        str(row.event_type or ""): int(row.count or 0)
        for row in rows
        if str(row.event_type or "")
    }


def _llm_totals_for_run(db: Session, *, run_id: str, started_at: Any, ended_at: Any) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE run_id = :run_id
              AND created_at >= :started_at
              AND created_at <= :ended_at
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    ).first()

    return {
        "calls": int((row.calls if row else 0) or 0),
        "success_calls": int((row.success_calls if row else 0) or 0),
        "fallback_calls": int((row.fallback_calls if row else 0) or 0),
        "total_tokens": int((row.total_tokens if row else 0) or 0),
        "estimated_cost_usd": float((row.estimated_cost_usd if row else 0.0) or 0.0),
    }


def _replicate_context(
    db: Session,
    *,
    run_id: str,
    condition_name: str,
) -> tuple[int, int]:
    if condition_name == UNKNOWN_CONDITION:
        return 1, 1

    rows = (
        db.query(SimulationRun)
        .filter(SimulationRun.condition_name == condition_name)
        .order_by(SimulationRun.started_at.asc(), SimulationRun.id.asc())
        .all()
    )
    if not rows:
        return 1, 1

    replicate_count = len(rows)
    for idx, row in enumerate(rows, start=1):
        if str(row.run_id or "").strip() == run_id:
            return idx, replicate_count
    return 1, replicate_count


def generate_run_report_summary(
    db: Session,
    *,
    run_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any]:
    clean_run_id = _coerce_run_id(run_id)
    run_row = _resolve_run_registry_row(db, run_id=clean_run_id)

    resolved_condition = (
        _coerce_condition_name(condition_name)
        if condition_name is not None
        else _coerce_condition_name(run_row.condition_name if run_row else None)
    )
    resolved_season_number = (
        int(season_number)
        if season_number is not None and int(season_number) > 0
        else (int(run_row.season_number) if run_row and run_row.season_number else None)
    )

    started_at, ended_at = _resolve_run_window(db, run_id=clean_run_id, run_row=run_row)
    llm = _llm_totals_for_run(db, run_id=clean_run_id, started_at=started_at, ended_at=ended_at)
    events = _event_counts_for_run(db, run_id=clean_run_id, started_at=started_at, ended_at=ended_at)

    replicate_index, replicate_count = _replicate_context(
        db,
        run_id=clean_run_id,
        condition_name=resolved_condition,
    )

    metrics = {
        "llm_calls": int(llm["calls"]),
        "success_calls": int(llm["success_calls"]),
        "fallback_calls": int(llm["fallback_calls"]),
        "total_tokens": int(llm["total_tokens"]),
        "estimated_cost_usd": float(llm["estimated_cost_usd"]),
        "total_events": int(sum(events.values())),
        "proposal_actions": int(events.get("create_proposal", 0)),
        "vote_actions": int(events.get("vote", 0)),
        "forum_actions": int(events.get("forum_post", 0) + events.get("forum_reply", 0)),
        "laws_passed": int(events.get("law_passed", 0)),
        "deaths": int(events.get("agent_died", 0)),
        "conflict_events": int(sum(events.get(name, 0) for name in CONFLICT_EVENT_TYPES)),
        "cooperation_events": int(sum(events.get(name, 0) for name in COOPERATION_EVENT_TYPES)),
    }

    caveats = [
        "Run summary uses run_id-scoped llm_usage and event windows.",
        "Comparative claims require >=3 replicates per condition.",
    ]
    if run_row is None:
        caveats.append("No simulation_runs registry row found; condition/season metadata may be incomplete.")

    return {
        "run_id": clean_run_id,
        "generated_at_utc": now_utc().isoformat(),
        "condition_name": resolved_condition,
        "season_number": resolved_season_number,
        "replicate_index": int(replicate_index),
        "replicate_count": int(replicate_count),
        "run_started_at": started_at.isoformat() if started_at else None,
        "run_ended_at": ended_at.isoformat() if ended_at else None,
        "metrics": metrics,
        "caveats": caveats,
    }


def render_run_report_markdown(payload: dict[str, Any]) -> str:
    metrics = payload.get("metrics") if isinstance(payload, dict) else {}
    rows = [
        f"# Run {payload.get('run_id')} Summary",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Condition: {payload.get('condition_name')}",
        f"- Replicate index: {payload.get('replicate_index')}",
        f"- Replicate count: {payload.get('replicate_count')}",
        f"- Season number: {payload.get('season_number')}",
        f"- Run window (UTC): {payload.get('run_started_at')} -> {payload.get('run_ended_at')}",
        "",
        "## Metric Table",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, label in CORE_METRICS:
        value = metrics.get(key) if isinstance(metrics, dict) else 0
        if isinstance(value, float):
            display = f"{value:.6f}"
        else:
            display = f"{int(value or 0):,}"
        rows.append(f"| {label} | {display} |")

    rows.extend(["", "## Caveats"])
    for caveat in payload.get("caveats") or []:
        rows.append(f"- {str(caveat)}")
    return "\n".join(rows).strip() + "\n"


def compare_condition_runs(
    db: Session,
    *,
    condition_name: str,
    min_replicates: int = 3,
    season_number: int | None = None,
) -> dict[str, Any]:
    clean_condition = _coerce_condition_name(condition_name)
    if clean_condition == UNKNOWN_CONDITION:
        raise ValueError("condition_name is required")

    query = db.query(SimulationRun).filter(SimulationRun.condition_name == clean_condition)
    if season_number is not None and int(season_number) > 0:
        query = query.filter(SimulationRun.season_number == int(season_number))

    runs = query.order_by(SimulationRun.started_at.asc(), SimulationRun.id.asc()).all()
    run_ids = [str(row.run_id or "").strip() for row in runs if str(row.run_id or "").strip()]

    run_summaries = [
        generate_run_report_summary(
            db,
            run_id=run_id,
            condition_name=clean_condition,
            season_number=(int(season_number) if season_number else None),
        )
        for run_id in run_ids
    ]

    metrics_by_key: dict[str, list[float]] = defaultdict(list)
    for summary in run_summaries:
        metrics = summary.get("metrics") if isinstance(summary, dict) else {}
        for key, _label in CORE_METRICS:
            metrics_by_key[key].append(float(metrics.get(key) or 0.0))

    aggregates: list[dict[str, Any]] = []
    for key, label in CORE_METRICS:
        values = metrics_by_key.get(key, [])
        if not values:
            aggregates.append(
                {
                    "metric_key": key,
                    "metric_label": label,
                    "median": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "spread": 0.0,
                }
            )
            continue
        metric_min = min(values)
        metric_max = max(values)
        aggregates.append(
            {
                "metric_key": key,
                "metric_label": label,
                "median": float(statistics.median(values)),
                "min": float(metric_min),
                "max": float(metric_max),
                "spread": float(metric_max - metric_min),
            }
        )

    comparison = {
        "generated_at_utc": now_utc().isoformat(),
        "condition_name": clean_condition,
        "season_number": (int(season_number) if season_number else None),
        "min_replicates_required": int(min_replicates),
        "replicate_count": len(run_summaries),
        "meets_replicate_threshold": (len(run_summaries) >= int(min_replicates)),
        "run_ids": run_ids,
        "core_metric_aggregates": aggregates,
        "run_summaries": run_summaries,
        "caveats": [
            "Comparative output is observational unless replicate threshold is met.",
            "Spread is max-min across included replicates.",
        ],
    }
    return comparison


def render_condition_comparison_markdown(payload: dict[str, Any]) -> str:
    rows = [
        f"# Condition Comparison: {payload.get('condition_name')}",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Replicate count: {payload.get('replicate_count')}",
        f"- Minimum replicates required: {payload.get('min_replicates_required')}",
        f"- Threshold met: {'yes' if payload.get('meets_replicate_threshold') else 'no'}",
        "",
        "## Core Metric Aggregates (Median + Spread)",
        "",
        "| Metric | Median | Min | Max | Spread |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in payload.get("core_metric_aggregates") or []:
        rows.append(
            "| "
            + f"{item.get('metric_label')} | "
            + f"{float(item.get('median') or 0.0):.6f} | "
            + f"{float(item.get('min') or 0.0):.6f} | "
            + f"{float(item.get('max') or 0.0):.6f} | "
            + f"{float(item.get('spread') or 0.0):.6f} |"
        )

    rows.extend(["", "## Included Runs"])
    for run_id in payload.get("run_ids") or []:
        rows.append(f"- {run_id}")
    rows.extend(["", "## Caveats"])
    for caveat in payload.get("caveats") or []:
        rows.append(f"- {str(caveat)}")
    return "\n".join(rows).strip() + "\n"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in str(value or "").strip().lower()).strip("-") or "unknown"


def write_json_markdown_artifacts(
    *,
    outdir: Path,
    basename: str,
    payload: dict[str, Any],
    markdown: str,
) -> dict[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / f"{basename}.json"
    md_path = outdir / f"{basename}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def write_run_summary_artifacts(payload: dict[str, Any]) -> dict[str, str]:
    run_id = str(payload.get("run_id") or "").strip()
    outdir = _repo_root() / "output" / "reports" / "runs" / _safe_slug(run_id)
    return write_json_markdown_artifacts(
        outdir=outdir,
        basename="run_report_summary",
        payload=payload,
        markdown=render_run_report_markdown(payload),
    )


def write_condition_comparison_artifacts(payload: dict[str, Any]) -> dict[str, str]:
    condition = _safe_slug(str(payload.get("condition_name") or "unknown"))
    outdir = _repo_root() / "output" / "reports" / "conditions" / condition
    return write_json_markdown_artifacts(
        outdir=outdir,
        basename="condition_comparison",
        payload=payload,
        markdown=render_condition_comparison_markdown(payload),
    )
