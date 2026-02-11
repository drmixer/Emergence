"""Run-scoped research report generation and artifact registry management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any

from sqlalchemy import String, cast, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import ensure_utc, now_utc
from app.models.models import AdminConfigChange, ArchiveArticle, RunReportArtifact, SimulationRun
from app.services.condition_reports import (
    RUN_CLASS_SPECIAL_EXPLORATORY,
    UNKNOWN_CONDITION as CONDITION_UNKNOWN,
    evaluate_run_claim_readiness,
    generate_and_record_condition_comparison,
    generate_and_record_run_summary,
)
from app.services.emergence_metrics import COOPERATION_EVENT_TYPES, CONFLICT_EVENT_TYPES
from app.services.runtime_config import runtime_config_service

logger = logging.getLogger(__name__)

REPORT_GENERATOR_VERSION = "run-report-v1"
REPORT_TEMPLATE_VERSION = "run-report-v1"

CONTENT_TYPE_TECHNICAL = "technical_report"
CONTENT_TYPE_APPROACHABLE = "approachable_article"

STATUS_OBSERVATIONAL = "observational"
STATUS_REPLICATED = "replicated"

EVIDENCE_FULL = "full"
EVIDENCE_PARTIAL = "partial"

UNKNOWN_CONDITION = "unknown"

MANAGED_TAG_PREFIXES = (
    "run_id:",
    "season:",
    "condition:",
    "topic:",
    "status:",
    "evidence:",
)

DEFAULT_CONDITION_CANDIDATES = (
    "baseline_v1",
    "carryover_v1",
    "provider_mix_shift_v1",
)

_RUN_REPORT_STATUS_LOCK = Lock()
_RUN_REPORT_PIPELINE_STATUS: dict[str, Any] = {
    "closeout": {
        "last_attempted_at": None,
        "last_status": "idle",
        "last_run_id": None,
        "last_error": None,
    },
    "backfill": {
        "last_attempted_at": None,
        "last_status": "idle",
        "last_generated": [],
        "last_skipped": [],
        "last_errors": [],
        "last_error": None,
    },
}


@dataclass
class RunBundleResult:
    run_id: str
    status_label: str
    evidence_completeness: str
    replicate_count: int
    condition_name: str
    season_number: int | None
    artifact_paths: dict[str, str]
    technical_article_id: int | None
    approachable_article_id: int | None


def _mark_pipeline_status(channel: str, **updates: Any) -> None:
    now_iso = now_utc().isoformat()
    with _RUN_REPORT_STATUS_LOCK:
        payload = _RUN_REPORT_PIPELINE_STATUS.setdefault(channel, {})
        payload["last_attempted_at"] = now_iso
        payload.update(updates)


def get_run_report_pipeline_status() -> dict[str, Any]:
    with _RUN_REPORT_STATUS_LOCK:
        return json.loads(json.dumps(_RUN_REPORT_PIPELINE_STATUS))


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    den = float(denominator or 0)
    if den <= 0:
        return 0.0
    return float(numerator or 0) / den


def _gini(values: list[float]) -> float:
    xs = [max(0.0, float(value)) for value in values]
    if not xs:
        return 0.0
    xs.sort()
    total = sum(xs)
    if total <= 0:
        return 0.0
    n = len(xs)
    weighted = 0.0
    for idx, value in enumerate(xs, start=1):
        weighted += idx * value
    return (2.0 * weighted) / (n * total) - (n + 1.0) / n


def _coerce_run_id(raw_value: str) -> str:
    clean = str(raw_value or "").strip()
    if not clean:
        raise ValueError("run_id is required")
    if len(clean) > 64:
        raise ValueError("run_id must be <= 64 chars")
    if not re.match(r"^[A-Za-z0-9:_-]+$", clean):
        raise ValueError("run_id must match [A-Za-z0-9:_-]+")
    return clean


def _slug_fragment(raw_value: str, *, fallback: str = "run") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(raw_value or "").strip().lower()).strip("-")
    return normalized or fallback


def normalize_report_tags(raw_tags: list[str] | tuple[str, ...] | None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags or []:
        tag = str(raw_tag or "").strip().lower()
        if not tag:
            continue
        if ":" in tag:
            prefix, suffix = tag.split(":", 1)
            prefix = prefix.strip()
            suffix = suffix.strip()
            if not prefix or not suffix:
                continue
            tag = f"{prefix}:{suffix}"
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped


def _clean_condition_name(raw_condition: str | None) -> str:
    clean = _slug_fragment(str(raw_condition or "").strip(), fallback=UNKNOWN_CONDITION)
    if clean == "run":
        return UNKNOWN_CONDITION
    return clean


def _clean_season_number(raw_season_number: int | None) -> int | None:
    if raw_season_number is None:
        return None
    try:
        value = int(raw_season_number)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _merge_generated_tags(*, existing_tags: list[str], generated_tags: list[str]) -> list[str]:
    retained = [
        tag
        for tag in normalize_report_tags(existing_tags)
        if not any(tag.startswith(prefix) for prefix in MANAGED_TAG_PREFIXES)
    ]
    return normalize_report_tags([*retained, *generated_tags])


def build_required_report_tags(
    *,
    run_id: str,
    condition_name: str,
    season_number: int | None,
    status_label: str,
    evidence_completeness: str,
    topic_tags: list[str] | None = None,
) -> list[str]:
    normalized_topics = []
    for topic in topic_tags or []:
        clean_topic = _slug_fragment(topic, fallback="")
        if clean_topic:
            normalized_topics.append(f"topic:{clean_topic}")

    season_tag = f"season:{int(season_number)}" if season_number else "season:unknown"
    condition_tag = f"condition:{_clean_condition_name(condition_name)}"
    return normalize_report_tags(
        [
            f"run_id:{run_id}",
            season_tag,
            condition_tag,
            *normalized_topics,
            f"status:{status_label}",
            f"evidence:{evidence_completeness}",
        ]
    )


def _base_evidence_links(run_id: str) -> list[dict[str, str]]:
    safe_run_id = str(run_id).strip()
    return [
        {"label": "Run Detail", "href": f"/runs/{safe_run_id}"},
        {
            "label": "Run Evidence API",
            "href": f"/api/analytics/runs/{safe_run_id}?hours_fallback=72&trace_limit=16&min_salience=55",
        },
        {"label": "Run Usage Snapshot", "href": f"/api/analytics/usage/daily?run_id={safe_run_id}"},
    ]


def _normalize_links(raw_links: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_links or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        href = str(item.get("href") or "").strip()
        if not label or not href:
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"label": label, "href": href})
    return deduped


def _build_claim_block(*, claim: str, evidence_links: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_links = _normalize_links(evidence_links)
    if not normalized_links:
        raise ValueError("claim blocks must include at least one evidence link")
    return {
        "claim": str(claim or "").strip(),
        "evidence_links": normalized_links,
    }


def _claims_to_section(
    *,
    heading: str,
    claims: list[dict[str, Any]],
    extra_references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    claim_blocks = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("claim") or "").strip()
        links = _normalize_links(claim.get("evidence_links"))
        if not claim_text or not links:
            continue
        claim_blocks.append({"claim": claim_text, "evidence_links": links})

    if not claim_blocks:
        raise ValueError("sections require at least one claim block")

    references = _normalize_links(
        [
            *[link for block in claim_blocks for link in (block.get("evidence_links") or [])],
            *(extra_references or []),
        ]
    )
    return {
        "heading": heading,
        "paragraphs": [str(block["claim"]) for block in claim_blocks],
        "claim_blocks": claim_blocks,
        "references": references,
        "template_version": REPORT_TEMPLATE_VERSION,
    }


def _reference_for_event(event: dict[str, Any], *, label_prefix: str) -> dict[str, str] | None:
    event_id = int(event.get("event_id") or 0)
    if event_id <= 0:
        return None
    return {"label": f"{label_prefix} Event #{event_id}", "href": f"/api/events/{event_id}"}


def _select_topic_tags(snapshot: dict[str, Any]) -> list[str]:
    topics = set()
    activity = snapshot.get("activity") if isinstance(snapshot, dict) else {}
    llm = snapshot.get("llm") if isinstance(snapshot, dict) else {}

    if int((activity or {}).get("proposal_actions") or 0) > 0 or int((activity or {}).get("vote_actions") or 0) > 0:
        topics.add("governance")
    if int((activity or {}).get("deaths") or 0) > 0:
        topics.add("survival")
    if int((activity or {}).get("conflict_events") or 0) > 0:
        topics.add("conflict")
    if int((activity or {}).get("trade_actions") or 0) > 0 or float((llm or {}).get("estimated_cost_usd") or 0.0) > 0:
        topics.add("economy")

    if not topics:
        topics.add("governance")
    return sorted(topics)


def _evaluate_evidence_completeness(snapshot: dict[str, Any]) -> str:
    llm = snapshot.get("llm") if isinstance(snapshot, dict) else {}
    activity = snapshot.get("activity") if isinstance(snapshot, dict) else {}
    moments = snapshot.get("key_moments") if isinstance(snapshot, dict) else []
    by_provider = llm.get("by_provider") if isinstance(llm, dict) else []
    if (
        int((llm or {}).get("calls") or 0) > 0
        and int((activity or {}).get("total_events") or 0) > 0
        and len(moments or []) > 0
        and len(by_provider or []) > 0
    ):
        return EVIDENCE_FULL
    return EVIDENCE_PARTIAL


def _resolve_status_label(*, condition_name: str, replicate_count: int, run_class: str | None = None) -> str:
    if str(run_class or "").strip().lower() == RUN_CLASS_SPECIAL_EXPLORATORY:
        return STATUS_OBSERVATIONAL
    if _clean_condition_name(condition_name) != UNKNOWN_CONDITION and int(replicate_count) >= 3:
        return STATUS_REPLICATED
    return STATUS_OBSERVATIONAL


def _resolve_run_claim_gate(db: Session, *, run_id: str) -> dict[str, Any] | None:
    try:
        return evaluate_run_claim_readiness(db, run_id=run_id, min_replicates=3)
    except Exception:
        return None


def _count_condition_replicates(db: Session, *, condition_name: str, run_id: str) -> tuple[int, str | None, dict[str, Any] | None]:
    clean_condition = _clean_condition_name(condition_name)
    claim_gate = _resolve_run_claim_gate(db, run_id=run_id)
    if claim_gate is not None:
        gate_condition = _clean_condition_name(str(claim_gate.get("condition_name") or UNKNOWN_CONDITION))
        gate_run_class = str(claim_gate.get("run_class") or "").strip().lower() or None
        if gate_condition == clean_condition:
            return max(1, int(claim_gate.get("replicate_count") or 1)), gate_run_class, claim_gate

    if clean_condition == UNKNOWN_CONDITION:
        return 1, None, claim_gate

    condition_fragment = f'%\"condition:{clean_condition}\"%'
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT evidence_run_id
                FROM archive_articles
                WHERE content_type = :content_type
                  AND evidence_run_id IS NOT NULL
                  AND CAST(tags AS TEXT) LIKE :condition_fragment
                """
            ),
            {
                "content_type": CONTENT_TYPE_TECHNICAL,
                "condition_fragment": condition_fragment,
            },
        ).fetchall()
    except Exception:
        return 1, None, claim_gate
    run_ids = {str(row.evidence_run_id or "").strip() for row in rows if str(row.evidence_run_id or "").strip()}
    run_ids.add(run_id)
    return max(1, len(run_ids)), None, claim_gate


def _resolve_run_window(db: Session, *, run_id: str, fallback_hours: int = 72) -> tuple[Any, Any, str]:
    now_value = now_utc()
    json_run_id = json.dumps(run_id)
    run_start_change = (
        db.query(AdminConfigChange)
        .filter(
            AdminConfigChange.key == "SIMULATION_RUN_ID",
            cast(AdminConfigChange.new_value, String) == json_run_id,
        )
        .order_by(AdminConfigChange.created_at.asc(), AdminConfigChange.id.asc())
        .first()
    )

    llm_row = db.execute(
        text(
            """
            SELECT MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
            FROM llm_usage
            WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id},
    ).first()
    event_row = db.execute(
        text(
            """
            SELECT MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
            FROM events
            WHERE (event_metadata -> 'runtime' ->> 'run_id') = :run_id
            """
        ),
        {"run_id": run_id},
    ).first()

    start_candidates = [
        ensure_utc(run_start_change.created_at) if run_start_change and run_start_change.created_at else None,
        ensure_utc(llm_row.first_seen) if llm_row and llm_row.first_seen else None,
        ensure_utc(event_row.first_seen) if event_row and event_row.first_seen else None,
    ]
    start_candidates = [candidate for candidate in start_candidates if candidate is not None]

    fallback_start = now_value - timedelta(hours=max(1, int(fallback_hours or 72)))
    run_started_at = min(start_candidates) if start_candidates else fallback_start

    end_candidates = [
        ensure_utc(llm_row.last_seen) if llm_row and llm_row.last_seen else None,
        ensure_utc(event_row.last_seen) if event_row and event_row.last_seen else None,
    ]
    end_candidates = [candidate for candidate in end_candidates if candidate is not None]
    run_ended_at = max(end_candidates) if end_candidates else now_value

    source = "fallback_window"
    if run_start_change and run_start_change.created_at:
        source = "admin_config_change"
    elif llm_row and llm_row.first_seen:
        source = "llm_usage_first_seen"
    elif event_row and event_row.first_seen:
        source = "event_metadata_runtime_run_id"

    return run_started_at, max(run_ended_at, run_started_at), source


def _collect_run_snapshot(db: Session, *, run_id: str) -> dict[str, Any]:
    run_row = db.query(SimulationRun).filter(SimulationRun.run_id == str(run_id)).first()
    run_started_at, run_ended_at, source = _resolve_run_window(db, run_id=run_id)

    llm_totals = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
              COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
              COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id},
    ).first()

    provider_rows = db.execute(
        text(
            """
            SELECT
              provider,
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE run_id = :run_id
            GROUP BY provider
            ORDER BY calls DESC, provider ASC
            """
        ),
        {"run_id": run_id},
    ).fetchall()

    model_rows = db.execute(
        text(
            """
            SELECT
              provider,
              COALESCE(resolved_model_name, model_name) AS model_name,
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE run_id = :run_id
            GROUP BY provider, COALESCE(resolved_model_name, model_name)
            ORDER BY calls DESC, provider ASC, model_name ASC
            """
        ),
        {"run_id": run_id},
    ).fetchall()

    scoped_event_rows = db.execute(
        text(
            """
            SELECT e.event_type, COUNT(*) AS count
            FROM events e
            WHERE e.created_at >= :since_ts
              AND (
                (e.event_metadata -> 'runtime' ->> 'run_id') = :run_id
                OR e.agent_id IN (
                  SELECT DISTINCT u.agent_id
                  FROM llm_usage u
                  WHERE u.agent_id IS NOT NULL
                    AND u.run_id = :run_id
                    AND u.created_at >= :since_ts
                )
              )
            GROUP BY e.event_type
            """
        ),
        {"run_id": run_id, "since_ts": run_started_at},
    ).fetchall()
    event_counts = {
        str(row.event_type or ""): int(row.count or 0)
        for row in scoped_event_rows
        if str(row.event_type or "")
    }
    runtime_mode_counts = db.execute(
        text(
            """
            SELECT
              COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'checkpoint' THEN 1 ELSE 0 END), 0) AS checkpoint_actions,
              COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'deterministic_fallback' THEN 1 ELSE 0 END), 0) AS deterministic_actions
            FROM events e
            WHERE e.created_at >= :since_ts
              AND (
                (e.event_metadata -> 'runtime' ->> 'run_id') = :run_id
                OR e.agent_id IN (
                  SELECT DISTINCT u.agent_id
                  FROM llm_usage u
                  WHERE u.agent_id IS NOT NULL
                    AND u.run_id = :run_id
                    AND u.created_at >= :since_ts
                )
              )
            """
        ),
        {"run_id": run_id, "since_ts": run_started_at},
    ).first()

    key_moment_rows = db.execute(
        text(
            """
            SELECT
              e.id,
              e.event_type,
              e.description,
              e.created_at
            FROM events e
            WHERE e.created_at >= :since_ts
              AND (
                (e.event_metadata -> 'runtime' ->> 'run_id') = :run_id
                OR e.agent_id IN (
                  SELECT DISTINCT u.agent_id
                  FROM llm_usage u
                  WHERE u.agent_id IS NOT NULL
                    AND u.run_id = :run_id
                    AND u.created_at >= :since_ts
                )
              )
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 16
            """
        ),
        {"run_id": run_id, "since_ts": run_started_at},
    ).fetchall()

    key_moments = []
    for row in reversed(key_moment_rows):
        event_id = int((row.id if row else 0) or 0)
        if event_id <= 0:
            continue
        key_moments.append(
            {
                "event_id": event_id,
                "event_type": str((row.event_type if row else "") or ""),
                "description": str((row.description if row else "") or "").strip(),
                "created_at": row.created_at.isoformat() if row and row.created_at else None,
            }
        )

    wealth_rows = db.execute(
        text(
            """
            SELECT
              ai.agent_id,
              COALESCE(SUM(ai.quantity), 0) AS total_qty
            FROM agent_inventory ai
            JOIN agents a ON a.id = ai.agent_id
            WHERE a.status <> 'dead'
              AND ai.resource_type IN ('food', 'energy', 'materials')
            GROUP BY ai.agent_id
            """
        )
    ).fetchall()
    wealth_values = [float(row.total_qty or 0.0) for row in wealth_rows]

    calls = int((llm_totals.calls if llm_totals else 0) or 0)
    total_events = int(sum(event_counts.values()))
    verification_state = "verified" if calls > 0 and total_events > 0 and key_moments else "partial"
    if calls <= 0:
        verification_state = "unverified"

    llm_payload = {
        "calls": calls,
        "success_calls": int((llm_totals.success_calls if llm_totals else 0) or 0),
        "fallback_calls": int((llm_totals.fallback_calls if llm_totals else 0) or 0),
        "prompt_tokens": int((llm_totals.prompt_tokens if llm_totals else 0) or 0),
        "completion_tokens": int((llm_totals.completion_tokens if llm_totals else 0) or 0),
        "total_tokens": int((llm_totals.total_tokens if llm_totals else 0) or 0),
        "estimated_cost_usd": float((llm_totals.estimated_cost_usd if llm_totals else 0.0) or 0.0),
        "success_rate": _safe_ratio(
            int((llm_totals.success_calls if llm_totals else 0) or 0),
            calls,
        ),
        "fallback_rate": _safe_ratio(
            int((llm_totals.fallback_calls if llm_totals else 0) or 0),
            calls,
        ),
        "by_provider": [
            {
                "provider": str(row.provider or ""),
                "calls": int(row.calls or 0),
                "success_calls": int(row.success_calls or 0),
                "fallback_calls": int(row.fallback_calls or 0),
                "total_tokens": int(row.total_tokens or 0),
                "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
            }
            for row in provider_rows
        ],
        "by_model": [
            {
                "provider": str(row.provider or ""),
                "model_name": str(row.model_name or ""),
                "calls": int(row.calls or 0),
                "success_calls": int(row.success_calls or 0),
                "fallback_calls": int(row.fallback_calls or 0),
                "total_tokens": int(row.total_tokens or 0),
                "estimated_cost_usd": float(row.estimated_cost_usd or 0.0),
            }
            for row in model_rows
        ],
    }

    activity_payload = {
        "total_events": total_events,
        "checkpoint_actions": int((runtime_mode_counts.checkpoint_actions if runtime_mode_counts else 0) or 0),
        "deterministic_actions": int((runtime_mode_counts.deterministic_actions if runtime_mode_counts else 0) or 0),
        "proposal_actions": int(event_counts.get("create_proposal", 0)),
        "vote_actions": int(event_counts.get("vote", 0)),
        "forum_actions": int(event_counts.get("forum_post", 0) + event_counts.get("forum_reply", 0)),
        "laws_passed": int(event_counts.get("law_passed", 0)),
        "deaths": int(event_counts.get("agent_died", 0)),
        "trade_actions": int(event_counts.get("trade", 0)),
        "conflict_events": int(sum(event_counts.get(event_type, 0) for event_type in CONFLICT_EVENT_TYPES)),
        "cooperation_events": int(sum(event_counts.get(event_type, 0) for event_type in COOPERATION_EVENT_TYPES)),
    }

    return {
        "run_id": run_id,
        "generated_at_utc": now_utc().isoformat(),
        "run_started_at": run_started_at.isoformat() if run_started_at else None,
        "run_ended_at": run_ended_at.isoformat() if run_ended_at else None,
        "run_class": (str(run_row.run_class).strip() if run_row and run_row.run_class else None),
        "condition_name": (str(run_row.condition_name).strip() if run_row and run_row.condition_name else None),
        "season_number": (int(run_row.season_number) if run_row and run_row.season_number else None),
        "verification_state": verification_state,
        "verification_source": source,
        "llm": llm_payload,
        "activity": activity_payload,
        "inequality_gini_current": _gini(wealth_values),
        "key_moments": key_moments,
        "evidence_links": _base_evidence_links(run_id),
    }


def _technical_markdown(payload: dict[str, Any]) -> str:
    llm = payload.get("llm") if isinstance(payload, dict) else {}
    activity = payload.get("activity") if isinstance(payload, dict) else {}
    rows = [
        f"# Run {payload.get('run_id')} Technical Report",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Run window (UTC): {payload.get('run_started_at')} -> {payload.get('run_ended_at')}",
        f"- Verification: {payload.get('verification_state')} ({payload.get('verification_source')})",
        f"- Status label: {payload.get('status_label')}",
        f"- Evidence completeness: {payload.get('evidence_completeness')}",
        f"- Condition: {payload.get('condition_name')}",
        f"- Replicate count for condition: {payload.get('replicate_count')}",
        "",
        "## LLM Totals",
        f"- Calls: {int((llm or {}).get('calls') or 0):,}",
        f"- Success calls: {int((llm or {}).get('success_calls') or 0):,}",
        f"- Fallback calls: {int((llm or {}).get('fallback_calls') or 0):,}",
        f"- Total tokens: {int((llm or {}).get('total_tokens') or 0):,}",
        f"- Estimated cost (USD): {float((llm or {}).get('estimated_cost_usd') or 0.0):.6f}",
        "",
        "## Activity Metrics",
        f"- Total events: {int((activity or {}).get('total_events') or 0):,}",
        f"- Proposals created: {int((activity or {}).get('proposal_actions') or 0):,}",
        f"- Votes cast: {int((activity or {}).get('vote_actions') or 0):,}",
        f"- Laws passed: {int((activity or {}).get('laws_passed') or 0):,}",
        f"- Forum actions: {int((activity or {}).get('forum_actions') or 0):,}",
        f"- Death events: {int((activity or {}).get('deaths') or 0):,}",
        f"- Cooperation events: {int((activity or {}).get('cooperation_events') or 0):,}",
        f"- Conflict events: {int((activity or {}).get('conflict_events') or 0):,}",
        f"- Inequality gini (current world snapshot): {float(payload.get('inequality_gini_current') or 0.0):.4f}",
        "",
        "## Provider Breakdown",
    ]
    for row in llm.get("by_provider") or []:
        rows.append(
            "- "
            + f"{row.get('provider')}: calls={int(row.get('calls') or 0)}, "
            + f"success={int(row.get('success_calls') or 0)}, "
            + f"fallback={int(row.get('fallback_calls') or 0)}, "
            + f"cost_usd={float(row.get('estimated_cost_usd') or 0.0):.6f}"
        )
    rows.extend(["", "## Model Breakdown"])
    for row in llm.get("by_model") or []:
        rows.append(
            "- "
            + f"{row.get('provider')}/{row.get('model_name')}: calls={int(row.get('calls') or 0)}, "
            + f"success={int(row.get('success_calls') or 0)}, "
            + f"fallback={int(row.get('fallback_calls') or 0)}, "
            + f"cost_usd={float(row.get('estimated_cost_usd') or 0.0):.6f}"
        )
    rows.extend(["", "## Caveats"])
    for caveat in payload.get("caveats") or []:
        rows.append(f"- {str(caveat)}")
    rows.extend(["", "## Evidence Links"])
    for link in payload.get("evidence_links") or []:
        rows.append(f"- [{link.get('label')}]({link.get('href')})")
    return "\n".join(rows).strip() + "\n"


def _story_markdown(payload: dict[str, Any]) -> str:
    rows = [
        f"# Run {payload.get('run_id')} Story Report",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Status label: {payload.get('status_label')}",
        f"- Evidence completeness: {payload.get('evidence_completeness')}",
        f"- Condition: {payload.get('condition_name')}",
        "",
    ]
    for section in payload.get("sections") or []:
        heading = str(section.get("heading") or "").strip()
        if not heading:
            continue
        rows.append(f"## {heading}")
        rows.append("")
        for paragraph in section.get("paragraphs") or []:
            rows.append(f"- Claim: {str(paragraph).strip()}")
        references = section.get("references") or []
        if references:
            rows.append("")
            rows.append("Evidence:")
            for reference in references:
                rows.append(f"- [{reference.get('label')}]({reference.get('href')})")
        rows.append("")
    return "\n".join(rows).strip() + "\n"


def _planner_markdown(payload: dict[str, Any]) -> str:
    recommendation = payload.get("recommended_next_condition") or {}
    rows = [
        f"# Run {payload.get('run_id')} Next-Run Plan",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Current condition: {payload.get('condition_name')}",
        f"- Replicate count: {payload.get('replicate_count')}",
        "",
        "## Delta vs Previous Comparable Run",
    ]
    for line in payload.get("delta_summary_lines") or []:
        rows.append(f"- {str(line)}")
    rows.extend(["", "## Candidate Conditions"])
    for item in payload.get("candidate_conditions") or []:
        rows.append(f"- {str(item)}")
    rows.extend(
        [
            "",
            "## Recommendation",
            f"- Condition: {recommendation.get('condition')}",
            f"- Rationale: {recommendation.get('rationale')}",
            f"- Risk notes: {recommendation.get('risk_notes')}",
            "",
            "## Caveats",
        ]
    )
    for caveat in payload.get("caveats") or []:
        rows.append(f"- {str(caveat)}")
    return "\n".join(rows).strip() + "\n"


def _collect_previous_run_snapshot(db: Session, *, run_id: str) -> dict[str, Any] | None:
    previous = db.execute(
        text(
            """
            SELECT run_id, MAX(created_at) AS last_seen
            FROM llm_usage
            WHERE run_id IS NOT NULL
              AND run_id <> ''
              AND run_id <> :run_id
            GROUP BY run_id
            ORDER BY last_seen DESC
            LIMIT 1
            """
        ),
        {"run_id": run_id},
    ).first()
    previous_run_id = str((previous.run_id if previous else "") or "").strip()
    if not previous_run_id:
        return None
    return _collect_run_snapshot(db, run_id=previous_run_id)


def _build_story_sections(
    *,
    snapshot: dict[str, Any],
    status_label: str,
    condition_name: str,
    replicate_count: int,
) -> list[dict[str, Any]]:
    run_id = str(snapshot.get("run_id") or "")
    activity = snapshot.get("activity") if isinstance(snapshot, dict) else {}
    llm = snapshot.get("llm") if isinstance(snapshot, dict) else {}
    evidence_links = _base_evidence_links(run_id)
    key_moments = list(snapshot.get("key_moments") or [])
    first_moment = key_moments[0] if key_moments else {}

    sections = [
        _claims_to_section(
            heading="What Happened",
            claims=[
                _build_claim_block(
                    claim=(
                        f"In this simulation run, we observed {int((activity or {}).get('total_events') or 0):,} "
                        f"scoped events and {int((llm or {}).get('calls') or 0):,} LLM calls."
                    ),
                    evidence_links=evidence_links,
                ),
                _build_claim_block(
                    claim=(
                        f"Governance activity included {int((activity or {}).get('proposal_actions') or 0):,} "
                        f"proposals, {int((activity or {}).get('vote_actions') or 0):,} votes, and "
                        f"{int((activity or {}).get('laws_passed') or 0):,} passed laws."
                    ),
                    evidence_links=evidence_links,
                ),
            ],
        ),
        _claims_to_section(
            heading="Major Moments",
            claims=[
                _build_claim_block(
                    claim=(
                        f"Representative moment: {str(first_moment.get('event_type') or 'event')} - "
                        f"{str(first_moment.get('description') or 'No description available.')}"
                    ),
                    evidence_links=[
                        *evidence_links,
                        _reference_for_event(first_moment, label_prefix="Major Moment"),
                    ],
                ),
                _build_claim_block(
                    claim=(
                        f"Conflict/cooperation balance in this run was "
                        f"{int((activity or {}).get('conflict_events') or 0)} conflict events vs "
                        f"{int((activity or {}).get('cooperation_events') or 0)} cooperation events."
                    ),
                    evidence_links=evidence_links,
                ),
            ],
            extra_references=[_reference_for_event(event, label_prefix="Moment") for event in key_moments[:5]],
        ),
    ]

    run_class = str(snapshot.get("run_class") or "").strip().lower()
    if run_class == RUN_CLASS_SPECIAL_EXPLORATORY:
        claim_text = (
            "This run is labeled special_exploratory; comparative baseline claims remain gated unless "
            "separately replicated under non-exploratory conditions."
        )
    elif status_label == STATUS_REPLICATED:
        claim_text = (
            f"Across {replicate_count} replicates for condition `{condition_name}`, this run can be used for "
            "comparative condition summaries."
        )
    else:
        claim_text = (
            f"Condition `{condition_name}` currently has {replicate_count} replicate(s); comparative claims stay "
            "gated until the replicate threshold (>=3) is met."
        )

    sections.extend(
        [
            _claims_to_section(
                heading="Why It Matters (Within This Simulation)",
                claims=[
                    _build_claim_block(claim=claim_text, evidence_links=evidence_links),
                    _build_claim_block(
                        claim=(
                            "This report is an observational simulation artifact under explicit assumptions, "
                            "not direct evidence of real-world social behavior."
                        ),
                        evidence_links=evidence_links,
                    ),
                ],
            ),
            _claims_to_section(
                heading="Limitations and Claim Boundaries",
                claims=[
                    _build_claim_block(
                        claim=(
                            "This story report should not be interpreted as generalized causal proof beyond "
                            "the tested simulation condition."
                        ),
                        evidence_links=evidence_links,
                    ),
                    _build_claim_block(
                        claim=(
                            "All nontrivial claims in this report include evidence links so findings remain "
                            "traceable to run-level telemetry."
                        ),
                        evidence_links=evidence_links,
                    ),
                ],
            ),
        ]
    )
    return sections


def _build_technical_payload(
    *,
    snapshot: dict[str, Any],
    status_label: str,
    evidence_completeness: str,
    condition_name: str,
    season_number: int | None,
    replicate_count: int,
) -> dict[str, Any]:
    caveats = [
        "Observations are simulation-scoped and assumption-dependent.",
        "Comparative claims are gated until condition replicate count >= 3.",
        "Inequality metric is a current-world snapshot, not a perfect per-run isolate.",
    ]
    if str(snapshot.get("run_class") or "").strip().lower() == RUN_CLASS_SPECIAL_EXPLORATORY:
        caveats.append(
            "Run class is special_exploratory; outputs are exploratory and excluded from baseline condition synthesis by default."
        )

    return {
        **snapshot,
        "template_version": REPORT_TEMPLATE_VERSION,
        "generator_version": REPORT_GENERATOR_VERSION,
        "status_label": status_label,
        "evidence_completeness": evidence_completeness,
        "condition_name": condition_name,
        "season_number": season_number,
        "replicate_count": replicate_count,
        "caveats": caveats,
    }


def _build_story_payload(
    *,
    snapshot: dict[str, Any],
    status_label: str,
    evidence_completeness: str,
    condition_name: str,
    season_number: int | None,
    replicate_count: int,
) -> dict[str, Any]:
    return {
        "run_id": snapshot.get("run_id"),
        "generated_at_utc": snapshot.get("generated_at_utc"),
        "status_label": status_label,
        "evidence_completeness": evidence_completeness,
        "condition_name": condition_name,
        "season_number": season_number,
        "replicate_count": replicate_count,
        "sections": _build_story_sections(
            snapshot=snapshot,
            status_label=status_label,
            condition_name=condition_name,
            replicate_count=replicate_count,
        ),
    }


def _build_planner_payload(
    *,
    current_snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    condition_name: str,
    replicate_count: int,
) -> dict[str, Any]:
    current_llm = current_snapshot.get("llm") if isinstance(current_snapshot, dict) else {}
    current_activity = current_snapshot.get("activity") if isinstance(current_snapshot, dict) else {}

    lines: list[str] = []
    if previous_snapshot:
        previous_llm = previous_snapshot.get("llm") if isinstance(previous_snapshot, dict) else {}
        previous_activity = previous_snapshot.get("activity") if isinstance(previous_snapshot, dict) else {}
        lines.append(
            f"LLM calls delta: {int((current_llm or {}).get('calls') or 0) - int((previous_llm or {}).get('calls') or 0):+d}"
        )
        lines.append(
            f"Total events delta: {int((current_activity or {}).get('total_events') or 0) - int((previous_activity or {}).get('total_events') or 0):+d}"
        )
        lines.append(
            "Estimated cost delta (USD): "
            + f"{float((current_llm or {}).get('estimated_cost_usd') or 0.0) - float((previous_llm or {}).get('estimated_cost_usd') or 0.0):+.6f}"
        )
    else:
        lines.append("No prior comparable run found for automatic delta.")

    fallback_rate = float((current_llm or {}).get("fallback_rate") or 0.0)
    deaths = int((current_activity or {}).get("deaths") or 0)
    if fallback_rate >= 0.20:
        recommendation = {
            "condition": "provider_reliability_hardening_v1",
            "rationale": "Fallback rate is elevated; prioritize reliability control condition.",
            "risk_notes": "May reduce novelty while stabilizing throughput.",
        }
    elif deaths >= 10:
        recommendation = {
            "condition": "survival_floor_adjustment_v1",
            "rationale": "Death pressure is high; test a bounded survival-floor intervention.",
            "risk_notes": "Could mask scarcity dynamics if too aggressive.",
        }
    else:
        recommendation = {
            "condition": "baseline_replicate_v1",
            "rationale": "Current reliability profile is stable; prioritize another baseline replicate.",
            "risk_notes": "Incremental insight unless contrasted with one-variable variant.",
        }

    return {
        "run_id": current_snapshot.get("run_id"),
        "generated_at_utc": current_snapshot.get("generated_at_utc"),
        "condition_name": condition_name,
        "replicate_count": int(replicate_count),
        "delta_summary_lines": lines,
        "candidate_conditions": list(DEFAULT_CONDITION_CANDIDATES),
        "recommended_next_condition": recommendation,
        "caveats": [
            "Recommendation is heuristic and should be operator-reviewed.",
            "Replicate gate for comparative claims remains enforced independently.",
        ],
    }


def _artifact_dir_for_run(run_id: str) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    safe_run_id = _slug_fragment(run_id, fallback="run")
    outdir = repo_root / "output" / "reports" / "runs" / safe_run_id
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def _record_artifact(
    db: Session,
    *,
    run_id: str,
    artifact_type: str,
    artifact_format: str,
    artifact_path: Path,
    metadata_json: dict[str, Any] | None = None,
) -> RunReportArtifact:
    row = (
        db.query(RunReportArtifact)
        .filter(
            RunReportArtifact.run_id == run_id,
            RunReportArtifact.artifact_type == artifact_type,
            RunReportArtifact.artifact_format == artifact_format,
        )
        .first()
    )
    payload = metadata_json or {}
    if row is None:
        row = RunReportArtifact(
            run_id=run_id,
            artifact_type=artifact_type,
            artifact_format=artifact_format,
            artifact_path=str(artifact_path),
            status="completed",
            template_version=REPORT_TEMPLATE_VERSION,
            generator_version=REPORT_GENERATOR_VERSION,
            metadata_json=payload,
            error_message=None,
        )
        db.add(row)
    else:
        row.artifact_path = str(artifact_path)
        row.status = "completed"
        row.template_version = REPORT_TEMPLATE_VERSION
        row.generator_version = REPORT_GENERATOR_VERSION
        row.metadata_json = payload
        row.error_message = None
    return row


def _deterministic_article_slug(*, run_id: str, content_type: str) -> str:
    base = _slug_fragment(run_id, fallback="run")
    suffix = "technical-report" if content_type == CONTENT_TYPE_TECHNICAL else "field-story"
    return f"run-{base}-{suffix}"[:160]


def _normalize_linked_record_ids(raw_value: Any) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    if not isinstance(raw_value, list):
        return []
    for item in raw_value:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _upsert_generated_article(
    db: Session,
    *,
    run_id: str,
    actor_id: str,
    content_type: str,
    title: str,
    summary: str,
    sections: list[dict[str, Any]],
    status_label: str,
    evidence_completeness: str,
    tags: list[str],
) -> ArchiveArticle:
    slug = _deterministic_article_slug(run_id=run_id, content_type=content_type)
    article = (
        db.query(ArchiveArticle)
        .filter(
            ArchiveArticle.evidence_run_id == run_id,
            ArchiveArticle.content_type == content_type,
        )
        .order_by(ArchiveArticle.updated_at.desc(), ArchiveArticle.id.desc())
        .first()
    )
    if article is None:
        article = db.query(ArchiveArticle).filter(ArchiveArticle.slug == slug).first()

    if article is None:
        article = ArchiveArticle(
            slug=slug,
            title=title,
            summary=summary,
            sections=sections,
            content_type=content_type,
            status_label=status_label,
            evidence_completeness=evidence_completeness,
            tags=tags,
            linked_record_ids=[],
            evidence_run_id=run_id,
            status="draft",
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(article)
    else:
        existing_tags = article.tags if isinstance(article.tags, list) else []
        article.title = title
        article.summary = summary
        article.sections = sections
        article.content_type = content_type
        article.status_label = status_label
        article.evidence_completeness = evidence_completeness
        article.tags = _merge_generated_tags(existing_tags=existing_tags, generated_tags=tags)
        article.evidence_run_id = run_id
        article.updated_by = actor_id
        if not article.slug:
            article.slug = slug

    return article


def _append_cross_link_reference(sections: list[dict[str, Any]], *, label: str, href: str) -> list[dict[str, Any]]:
    if not isinstance(sections, list) or not sections:
        return sections
    normalized_sections: list[dict[str, Any]] = []
    for section in sections:
        normalized_sections.append(dict(section) if isinstance(section, dict) else {})
    target = normalized_sections[-1]
    references = target.get("references")
    refs = references if isinstance(references, list) else []
    normalized = _normalize_links(
        [
            *refs,
            {"label": str(label).strip(), "href": str(href).strip()},
        ]
    )
    target["references"] = normalized
    normalized_sections[-1] = target
    return normalized_sections


def generate_run_technical_artifact(
    db: Session,
    *,
    run_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any]:
    clean_run_id = _coerce_run_id(run_id)
    clean_condition = _clean_condition_name(condition_name)
    clean_season_number = _clean_season_number(season_number)

    snapshot = _collect_run_snapshot(db, run_id=clean_run_id)
    replicate_count, run_class, claim_gate = _count_condition_replicates(
        db,
        condition_name=clean_condition,
        run_id=clean_run_id,
    )
    evidence_completeness = _evaluate_evidence_completeness(snapshot)
    status_label = _resolve_status_label(
        condition_name=clean_condition,
        replicate_count=replicate_count,
        run_class=run_class,
    )
    topic_tags = _select_topic_tags(snapshot)

    payload = _build_technical_payload(
        snapshot=snapshot,
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        condition_name=clean_condition,
        season_number=clean_season_number,
        replicate_count=replicate_count,
    )
    if claim_gate:
        payload["claim_gate"] = claim_gate
        if int(len(claim_gate.get("excluded_run_ids") or [])) > 0:
            payload.setdefault("caveats", []).append(
                f"Replicate gate excluded {int(len(claim_gate.get('excluded_run_ids') or []))} run(s) by run_class/duration."
            )
    payload["tags"] = build_required_report_tags(
        run_id=clean_run_id,
        condition_name=clean_condition,
        season_number=clean_season_number,
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        topic_tags=topic_tags,
    )

    outdir = _artifact_dir_for_run(clean_run_id)
    json_path = outdir / "technical_report.json"
    markdown_path = outdir / "technical_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_technical_markdown(payload), encoding="utf-8")

    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="technical_report",
        artifact_format="json",
        artifact_path=json_path,
        metadata_json={
            "run_id": clean_run_id,
            "condition_name": clean_condition,
            "season_number": clean_season_number,
            "status_label": status_label,
            "evidence_completeness": evidence_completeness,
            "claim_gate": claim_gate,
        },
    )
    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="technical_report",
        artifact_format="markdown",
        artifact_path=markdown_path,
        metadata_json={"run_id": clean_run_id},
    )
    return payload


def generate_run_story_artifact(
    db: Session,
    *,
    run_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any]:
    clean_run_id = _coerce_run_id(run_id)
    clean_condition = _clean_condition_name(condition_name)
    clean_season_number = _clean_season_number(season_number)

    snapshot = _collect_run_snapshot(db, run_id=clean_run_id)
    replicate_count, run_class, claim_gate = _count_condition_replicates(
        db,
        condition_name=clean_condition,
        run_id=clean_run_id,
    )
    evidence_completeness = _evaluate_evidence_completeness(snapshot)
    status_label = _resolve_status_label(
        condition_name=clean_condition,
        replicate_count=replicate_count,
        run_class=run_class,
    )

    payload = _build_story_payload(
        snapshot=snapshot,
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        condition_name=clean_condition,
        season_number=clean_season_number,
        replicate_count=replicate_count,
    )
    if claim_gate:
        payload["claim_gate"] = claim_gate
    outdir = _artifact_dir_for_run(clean_run_id)
    json_path = outdir / "approachable_report.json"
    markdown_path = outdir / "approachable_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_story_markdown(payload), encoding="utf-8")

    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="approachable_report",
        artifact_format="json",
        artifact_path=json_path,
        metadata_json={
            "run_id": clean_run_id,
            "condition_name": clean_condition,
            "season_number": clean_season_number,
            "status_label": status_label,
            "evidence_completeness": evidence_completeness,
            "claim_gate": claim_gate,
        },
    )
    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="approachable_report",
        artifact_format="markdown",
        artifact_path=markdown_path,
        metadata_json={"run_id": clean_run_id},
    )
    return payload


def generate_next_run_plan_artifact(
    db: Session,
    *,
    run_id: str,
    condition_name: str | None = None,
) -> dict[str, Any]:
    clean_run_id = _coerce_run_id(run_id)
    clean_condition = _clean_condition_name(condition_name)
    current_snapshot = _collect_run_snapshot(db, run_id=clean_run_id)
    previous_snapshot = _collect_previous_run_snapshot(db, run_id=clean_run_id)
    replicate_count, _run_class, claim_gate = _count_condition_replicates(
        db,
        condition_name=clean_condition,
        run_id=clean_run_id,
    )

    payload = _build_planner_payload(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        condition_name=clean_condition,
        replicate_count=replicate_count,
    )
    if claim_gate:
        payload["claim_gate"] = claim_gate
    outdir = _artifact_dir_for_run(clean_run_id)
    json_path = outdir / "next_run_plan.json"
    markdown_path = outdir / "next_run_plan.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(_planner_markdown(payload), encoding="utf-8")

    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="planner_report",
        artifact_format="json",
        artifact_path=json_path,
        metadata_json={
            "run_id": clean_run_id,
            "condition_name": clean_condition,
            "replicate_count": replicate_count,
            "claim_gate": claim_gate,
        },
    )
    _record_artifact(
        db,
        run_id=clean_run_id,
        artifact_type="planner_report",
        artifact_format="markdown",
        artifact_path=markdown_path,
        metadata_json={"run_id": clean_run_id},
    )
    return payload


def rebuild_run_bundle(
    db: Session,
    *,
    run_id: str,
    actor_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> RunBundleResult:
    clean_run_id = _coerce_run_id(run_id)
    clean_condition = _clean_condition_name(condition_name)
    clean_season_number = _clean_season_number(season_number)

    technical_payload = generate_run_technical_artifact(
        db,
        run_id=clean_run_id,
        condition_name=clean_condition,
        season_number=clean_season_number,
    )
    story_payload = generate_run_story_artifact(
        db,
        run_id=clean_run_id,
        condition_name=clean_condition,
        season_number=clean_season_number,
    )
    planner_payload = generate_next_run_plan_artifact(
        db,
        run_id=clean_run_id,
        condition_name=clean_condition,
    )

    status_label = str(technical_payload.get("status_label") or STATUS_OBSERVATIONAL)
    evidence_completeness = str(technical_payload.get("evidence_completeness") or EVIDENCE_PARTIAL)
    replicate_count = int(technical_payload.get("replicate_count") or 1)
    tags = list(technical_payload.get("tags") or [])

    technical_article = _upsert_generated_article(
        db,
        run_id=clean_run_id,
        actor_id=actor_id,
        content_type=CONTENT_TYPE_TECHNICAL,
        title=f"Run {clean_run_id} Technical Report",
        summary=(
            f"Technical packet for run {clean_run_id}: provider/model reliability, activity metrics, "
            f"and caveats with explicit provenance links."
        ),
        sections=[
            {
                "heading": "Run Metadata and Verification",
                "paragraphs": [
                    f"Run ID: {clean_run_id}",
                    f"Status label: {status_label}",
                    f"Evidence completeness: {evidence_completeness}",
                    f"Condition: {clean_condition}",
                    f"Replicate count (condition): {replicate_count}",
                ],
                "references": technical_payload.get("evidence_links") or _base_evidence_links(clean_run_id),
            },
            {
                "heading": "Provider and Model Reliability",
                "paragraphs": [
                    f"{row.get('provider')} | calls={row.get('calls')} | success={row.get('success_calls')} | fallback={row.get('fallback_calls')} | cost_usd={float(row.get('estimated_cost_usd') or 0.0):.6f}"
                    for row in (technical_payload.get("llm") or {}).get("by_provider", [])
                ]
                or ["No provider usage rows were found for this run."],
                "references": technical_payload.get("evidence_links") or _base_evidence_links(clean_run_id),
            },
            {
                "heading": "Core Metrics and Caveats",
                "paragraphs": [
                    f"Total events: {int((technical_payload.get('activity') or {}).get('total_events') or 0)}",
                    f"Proposals: {int((technical_payload.get('activity') or {}).get('proposal_actions') or 0)}, votes: {int((technical_payload.get('activity') or {}).get('vote_actions') or 0)}, laws passed: {int((technical_payload.get('activity') or {}).get('laws_passed') or 0)}",
                    f"Conflict/cooperation: {int((technical_payload.get('activity') or {}).get('conflict_events') or 0)} / {int((technical_payload.get('activity') or {}).get('cooperation_events') or 0)}",
                    f"Inequality gini (current world snapshot): {float(technical_payload.get('inequality_gini_current') or 0.0):.4f}",
                    "Caveat: comparative claims are blocked unless replicate count >= 3 for the same condition.",
                ],
                "references": technical_payload.get("evidence_links") or _base_evidence_links(clean_run_id),
            },
        ],
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        tags=tags,
    )

    story_article = _upsert_generated_article(
        db,
        run_id=clean_run_id,
        actor_id=actor_id,
        content_type=CONTENT_TYPE_APPROACHABLE,
        title=f"Run {clean_run_id} Field Story",
        summary=(
            f"Approachable narrative summary for run {clean_run_id}, with evidence links and explicit "
            "claim boundaries."
        ),
        sections=story_payload.get("sections") or [],
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        tags=tags,
    )

    db.flush()
    if technical_article.id and story_article.id:
        technical_article.linked_record_ids = _normalize_linked_record_ids(
            [*(_normalize_linked_record_ids(technical_article.linked_record_ids)), int(story_article.id)]
        )
        story_article.linked_record_ids = _normalize_linked_record_ids(
            [*(_normalize_linked_record_ids(story_article.linked_record_ids)), int(technical_article.id)]
        )
        technical_article.sections = _append_cross_link_reference(
            list(technical_article.sections or []),
            label="Approachable companion story",
            href=f"/articles/{story_article.slug}",
        )
        story_article.sections = _append_cross_link_reference(
            list(story_article.sections or []),
            label="Technical companion report",
            href=f"/articles/{technical_article.slug}",
        )

    run_dir = _artifact_dir_for_run(clean_run_id)
    artifact_paths = {
        "technical_report_json": str(run_dir / "technical_report.json"),
        "technical_report_markdown": str(run_dir / "technical_report.md"),
        "approachable_report_json": str(run_dir / "approachable_report.json"),
        "approachable_report_markdown": str(run_dir / "approachable_report.md"),
        "planner_report_json": str(run_dir / "next_run_plan.json"),
        "planner_report_markdown": str(run_dir / "next_run_plan.md"),
    }

    _ = planner_payload  # planner payload is persisted to artifacts and returned by paths/registry.
    return RunBundleResult(
        run_id=clean_run_id,
        status_label=status_label,
        evidence_completeness=evidence_completeness,
        replicate_count=replicate_count,
        condition_name=clean_condition,
        season_number=clean_season_number,
        artifact_paths=artifact_paths,
        technical_article_id=int(technical_article.id) if technical_article.id else None,
        approachable_article_id=int(story_article.id) if story_article.id else None,
    )


def _bundle_complete(db: Session, *, run_id: str) -> bool:
    count = int(
        db.execute(
            text(
                """
                SELECT COUNT(DISTINCT artifact_type) AS artifact_type_count
                FROM run_report_artifacts
                WHERE run_id = :run_id
                  AND status = 'completed'
                """
            ),
            {"run_id": run_id},
        ).scalar()
        or 0
    )
    return count >= 3


def generate_run_bundle_for_run_id(
    *,
    run_id: str,
    actor_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = rebuild_run_bundle(
            db,
            run_id=run_id,
            actor_id=actor_id,
            condition_name=condition_name,
            season_number=season_number,
        )
        db.commit()
        return {
            "run_id": result.run_id,
            "status_label": result.status_label,
            "evidence_completeness": result.evidence_completeness,
            "replicate_count": result.replicate_count,
            "condition_name": result.condition_name,
            "season_number": result.season_number,
            "artifact_paths": result.artifact_paths,
            "technical_article_id": result.technical_article_id,
            "approachable_article_id": result.approachable_article_id,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def maybe_generate_run_closeout_bundle(
    *,
    run_id: str | None,
    actor_id: str,
    condition_name: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any] | None:
    if not bool(getattr(settings, "RUN_REPORT_BUNDLE_ENABLED", True)):
        _mark_pipeline_status("closeout", last_status="disabled")
        return None

    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        _mark_pipeline_status("closeout", last_status="skipped", last_run_id=None, last_error="missing_run_id")
        return None

    _mark_pipeline_status("closeout", last_status="started", last_run_id=clean_run_id, last_error=None)
    try:
        result = generate_run_bundle_for_run_id(
            run_id=clean_run_id,
            actor_id=actor_id,
            condition_name=condition_name,
            season_number=season_number,
        )
        try:
            db = SessionLocal()
            try:
                summary_result = generate_and_record_run_summary(
                    db,
                    run_id=clean_run_id,
                    condition_name=condition_name,
                    season_number=season_number,
                )
                summary_payload = summary_result.get("payload") or {}
                resolved_condition = str(summary_payload.get("condition_name") or "").strip()
                condition_comparison = None
                if resolved_condition and resolved_condition != CONDITION_UNKNOWN:
                    condition_comparison = generate_and_record_condition_comparison(
                        db,
                        condition_name=resolved_condition,
                        min_replicates=3,
                        season_number=season_number,
                    )
                db.commit()
                result["viewer_reports"] = {
                    "run_summary": summary_result,
                    "condition_comparison": condition_comparison,
                }
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.exception("Failed to generate viewer report artifacts for run_id=%s", clean_run_id)
            result["viewer_reports"] = {
                "status": "failed",
                "error": str(exc),
            }
        result["status"] = "generated"
        _mark_pipeline_status("closeout", last_status="generated", last_run_id=clean_run_id, last_error=None)
        return result
    except Exception as exc:
        logger.exception("Failed to generate run closeout bundle for run_id=%s", clean_run_id)
        _mark_pipeline_status("closeout", last_status="failed", last_run_id=clean_run_id, last_error=str(exc))
        return {
            "run_id": clean_run_id,
            "status": "failed",
            "error": str(exc),
        }


async def maybe_generate_scheduled_run_report_backfill() -> dict[str, Any] | None:
    if not bool(getattr(settings, "RUN_REPORT_BACKFILL_ENABLED", True)):
        _mark_pipeline_status("backfill", last_status="disabled")
        return None

    lookback_hours = max(24, int(getattr(settings, "RUN_REPORT_BACKFILL_LOOKBACK_HOURS", 7 * 24) or 7 * 24))
    max_runs = max(1, int(getattr(settings, "RUN_REPORT_BACKFILL_MAX_RUNS_PER_PASS", 3) or 3))
    actor_id = str(getattr(settings, "RUN_REPORT_BACKFILL_ACTOR", "report-backfill-bot") or "report-backfill-bot").strip()

    active_run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip()
    simulation_active = bool(runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE"))
    simulation_paused = bool(runtime_config_service.get_effective_value_cached("SIMULATION_PAUSED"))
    cutoff_ts = now_utc() - timedelta(hours=lookback_hours)

    db = SessionLocal()
    _mark_pipeline_status("backfill", last_status="started", last_error=None)
    try:
        candidate_rows = db.execute(
            text(
                """
                SELECT run_id, MAX(created_at) AS last_seen
                FROM llm_usage
                WHERE run_id IS NOT NULL
                  AND run_id <> ''
                  AND created_at >= :cutoff_ts
                GROUP BY run_id
                ORDER BY last_seen DESC
                LIMIT 50
                """
            ),
            {"cutoff_ts": cutoff_ts},
        ).fetchall()

        generated: list[str] = []
        skipped: list[str] = []
        errors: list[dict[str, str]] = []
        for row in candidate_rows:
            run_id = str((row.run_id if row else "") or "").strip()
            if not run_id:
                continue
            if simulation_active and not simulation_paused and run_id == active_run_id:
                skipped.append(run_id)
                continue
            try:
                if _bundle_complete(db, run_id=run_id):
                    skipped.append(run_id)
                    continue
                rebuild_run_bundle(
                    db,
                    run_id=run_id,
                    actor_id=actor_id,
                )
                summary_result = generate_and_record_run_summary(
                    db,
                    run_id=run_id,
                )
                summary_payload = summary_result.get("payload") or {}
                resolved_condition = str(summary_payload.get("condition_name") or "").strip()
                if resolved_condition and resolved_condition != CONDITION_UNKNOWN:
                    generate_and_record_condition_comparison(
                        db,
                        condition_name=resolved_condition,
                        min_replicates=3,
                    )
                db.commit()
                generated.append(run_id)
            except Exception as exc:
                db.rollback()
                errors.append({"run_id": run_id, "error": str(exc)})
            if len(generated) >= max_runs:
                break

        if not generated and not errors:
            _mark_pipeline_status(
                "backfill",
                last_status="idle",
                last_generated=[],
                last_skipped=skipped,
                last_errors=[],
                last_error=None,
            )
            return None
        _mark_pipeline_status(
            "backfill",
            last_status=("failed" if errors and not generated else "generated"),
            last_generated=generated,
            last_skipped=skipped,
            last_errors=errors,
            last_error=(errors[0]["error"] if errors else None),
        )
        return {
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
        }
    finally:
        db.close()
