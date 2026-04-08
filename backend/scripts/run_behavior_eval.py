#!/usr/bin/env python3
"""Run a short Emergence behavior eval using existing admin controls and reports."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import ensure_utc
from app.models.models import Agent, AgentInventory, Event, GlobalResources
from app.services.condition_reports import (
    CONFLICT_EVENT_TYPES,
    COOPERATION_EVENT_TYPES,
    generate_and_record_condition_comparison,
    generate_and_record_run_summary,
)
from app.services.emergence_metrics import compute_emergence_metrics
from app.services.law_effects import active_survival_reserve_laws
from app.services.runtime_config import runtime_config_service


INTERACTION_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "trade",
}

ACTION_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "work",
    "trade",
    "idle",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "vote_enforcement",
}

MEANINGFUL_INTERESTINGNESS_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "trade",
    "proposal_resolved",
    "law_passed",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "vote_enforcement",
    "reserve_aid",
    "reserve_shortfall",
}

POST_LAW_WINDOW_SECONDS = 300
POST_LAW_NON_GOVERNANCE_EVENT_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "trade",
    "work",
    "agent_revived",
    "agent_died",
    "became_dormant",
    "starvation_warning",
    "world_event",
    "crisis_event",
    "crisis",
    "reserve_aid",
    "reserve_shortfall",
} | set(COOPERATION_EVENT_TYPES) | set(CONFLICT_EVENT_TYPES)


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ModePreset:
    name: str
    smoke_seconds: int
    batch_seconds: int
    batch_runs: int
    smoke_condition: str
    batch_condition: str
    batch_run_class: str
    batch_min_runtime_seconds: int
    day_length_minutes: int | None
    description: str


MODE_PRESETS: dict[str, ModePreset] = {
    "control": ModePreset(
        name="control",
        smoke_seconds=240,
        batch_seconds=360,
        batch_runs=3,
        smoke_condition="behavior_eval_smoke_v1",
        batch_condition="behavior_eval_control_v1",
        batch_run_class="standard_72h",
        batch_min_runtime_seconds=0,
        day_length_minutes=None,
        description="Short reset-backed replicate batch for repeatable early behavior checks.",
    ),
    "interestingness": ModePreset(
        name="interestingness",
        smoke_seconds=240,
        batch_seconds=1800,
        batch_runs=1,
        smoke_condition="behavior_eval_smoke_v1",
        batch_condition="behavior_eval_interestingness_v1",
        batch_run_class="standard_72h",
        batch_min_runtime_seconds=900,
        day_length_minutes=20,
        description="Longer exploratory pass tuned for richer social/governance emergence.",
    ),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_to_dt(value: str | None) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_entropy(counts: list[int]) -> float:
    total = sum(max(0, int(count)) for count in counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        share = float(count) / float(total)
        entropy -= share * math.log2(share)
    return entropy


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or "").strip().lower())
    return cleaned.strip("-") or "behavior-eval"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _technical_report_path(run_id: str) -> Path:
    return _repo_root() / "output" / "reports" / "runs" / _slug(run_id) / "technical_report.json"


def _run_report_dir(run_id: str) -> Path:
    return _repo_root() / "output" / "reports" / "runs" / _slug(run_id)


def _load_technical_report(run_id: str) -> dict[str, Any] | None:
    path = _technical_report_path(run_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_runtime_settings(*, keys: list[str]) -> dict[str, Any]:
    db = SessionLocal()
    try:
        effective = runtime_config_service.get_effective(db)
        return {key: effective.get(key) for key in keys}
    finally:
        db.close()


def _build_first_cycle_reserve_trace(
    reserve_event_rows: list[dict[str, Any]],
    *,
    trace_window_seconds: int = 1,
) -> dict[str, Any]:
    if not reserve_event_rows:
        return {
            "first_reserve_event_at": None,
            "trace_window_seconds": int(trace_window_seconds),
            "first_cycle_trace": [],
        }

    sorted_rows = sorted(
        reserve_event_rows,
        key=lambda row: (
            row.get("created_at") or datetime.max.replace(tzinfo=timezone.utc),
            int(row.get("id") or 0),
        ),
    )
    first_ts = sorted_rows[0].get("created_at")
    if not isinstance(first_ts, datetime):
        return {
            "first_reserve_event_at": None,
            "trace_window_seconds": int(trace_window_seconds),
            "first_cycle_trace": [],
        }

    trace_deadline = first_ts + timedelta(seconds=max(0, int(trace_window_seconds)))
    trace_rows: list[dict[str, Any]] = []
    for row in sorted_rows:
        created_at = row.get("created_at")
        if not isinstance(created_at, datetime) or created_at > trace_deadline:
            break
        trace_rows.append(
            {
                "event_type": str(row.get("event_type") or ""),
                "created_at": created_at.astimezone(timezone.utc).isoformat(),
                "agent_id": int(row.get("agent_id")) if row.get("agent_id") is not None else None,
                "agent_number": int(row.get("agent_number")) if row.get("agent_number") is not None else None,
                "display_name": str(row.get("display_name") or "") or None,
                "description": str(row.get("description") or "") or None,
                "status_before": row.get("status_before"),
                "support_mode": row.get("support_mode"),
                "aid_granted": row.get("aid_granted"),
                "pre_food": row.get("pre_food"),
                "pre_energy": row.get("pre_energy"),
                "food_deficit": row.get("food_deficit"),
                "energy_deficit": row.get("energy_deficit"),
                "reserve_pool_food_before": row.get("reserve_pool_food_before"),
                "reserve_pool_energy_before": row.get("reserve_pool_energy_before"),
                "reserve_pool_food_after": row.get("reserve_pool_food_after"),
                "reserve_pool_energy_after": row.get("reserve_pool_energy_after"),
            }
        )

    return {
        "first_reserve_event_at": first_ts.astimezone(timezone.utc).isoformat(),
        "trace_window_seconds": int(trace_window_seconds),
        "first_cycle_trace": trace_rows,
    }


def _event_matches_run_scope(event_row: Event, *, run_id: str, run_agent_ids: set[int]) -> bool:
    metadata = event_row.event_metadata if isinstance(event_row.event_metadata, dict) else {}
    runtime = metadata.get("runtime") if isinstance(metadata, dict) else {}
    event_run_id = str((runtime or {}).get("run_id") or "").strip()
    if event_run_id == str(run_id).strip():
        return True
    if event_row.agent_id is not None and int(event_row.agent_id) in run_agent_ids:
        return True
    return False


def _write_behavior_eval_run_snapshot(*, run_id: str, payload: dict[str, Any]) -> dict[str, str]:
    outdir = _run_report_dir(run_id)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "behavior_eval_snapshot.json"
    md_path = outdir / "behavior_eval_snapshot.md"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reserve = (payload.get("reserve_readiness_diagnostics") or {})
    reserve_events = reserve.get("reserve_event_counts") or {}
    trace = reserve.get("first_cycle_trace") or []
    lines = [
        f"# Behavior Eval Snapshot {run_id}",
        "",
        f"- Run ID: {run_id}",
        f"- Condition: {payload.get('condition_name')}",
        f"- Runtime seconds: {((payload.get('derived_metrics') or {}).get('runtime_seconds'))}",
    ]
    if reserve:
        lines.extend(
            [
                f"- Reserve laws active: {int(reserve.get('active_reserve_law_count') or 0)}",
                (
                    "- Reserve events: "
                    f"reserve_aid={int(reserve_events.get('reserve_aid', 0) or 0)}, "
                    f"reserve_shortfall={int(reserve_events.get('reserve_shortfall', 0) or 0)}, "
                    f"became_dormant={int(reserve_events.get('became_dormant', 0) or 0)}"
                ),
                (
                    "- Final reserve: "
                    f"food={float(reserve.get('reserve_pool_food') or 0.0):.2f}, "
                    f"energy={float(reserve.get('reserve_pool_energy') or 0.0):.2f}, "
                    f"dormant_agents={int(reserve.get('dormant_agents') or 0)}"
                ),
                f"- First reserve event at: {reserve.get('first_reserve_event_at')}",
                f"- First-cycle trace rows: {len(trace)}",
            ]
        )
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}


class AdminClient:
    def __init__(self, *, api_base: str, token: str, actor: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.actor = actor
        self.client = httpx.Client(
            base_url=self.api_base,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Admin-User": actor,
            },
        )

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected payload from {path}: {payload!r}")
        return payload

    def status(self) -> dict[str, Any]:
        return self.request("GET", "/api/admin/status")

    def patch_config(self, updates: dict[str, Any], *, reason: str) -> dict[str, Any]:
        return self.request("PATCH", "/api/admin/config", json={"updates": updates, "reason": reason})

    def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/admin/control/run/start", json=payload)

    def stop_run(self, *, reason: str, clear_run_id: bool = True) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/admin/control/run/stop",
            json={"reason": reason, "clear_run_id": clear_run_id},
        )

    def run_metrics(self, *, run_id: str) -> dict[str, Any]:
        return self.request("GET", "/api/admin/run/metrics", params={"run_id": run_id})

    def reset_dev_world(self, *, reason: str) -> dict[str, Any]:
        return self.request("POST", "/api/admin/control/run/reset-dev", json={"reason": reason})


def _start_run_with_retry(
    admin: AdminClient,
    *,
    payload: dict[str, Any],
    attempts: int = 5,
    sleep_seconds: int = 10,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        try:
            return admin.start_run(payload)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is None or status_code < 500 or attempt >= int(attempts):
                raise
            last_error = exc
            time.sleep(max(1, int(sleep_seconds)))
    if last_error is not None:
        raise last_error
    raise RuntimeError("run start retry exhausted without response")


def _batch_post_reset_profile_defaults(profile: str) -> dict[str, float | None]:
    if profile == "reserve_stress_v1":
        return {
            "activation": "after_reset",
            "agent_food": 0.75,
            "agent_energy": 3.0,
            "agent_materials": None,
            "common_pool_food": 5.0,
            "common_pool_energy": 25.0,
            "common_pool_materials": None,
        }
    if profile == "reserve_stress_v2":
        return {
            "activation": "after_first_reserve_law",
            "agent_food": 0.10,
            "agent_energy": 0.10,
            "agent_materials": None,
            "common_pool_food": 1.50,
            "common_pool_energy": 1.50,
            "common_pool_materials": None,
        }
    raise ValueError(f"Unsupported post-reset profile: {profile}")


def _resolve_batch_post_reset_tuning(args: argparse.Namespace) -> dict[str, Any] | None:
    profile_name = str(getattr(args, "batch_post_reset_profile", "") or "").strip()
    explicit = {
        "agent_food": getattr(args, "batch_post_reset_agent_food", None),
        "agent_energy": getattr(args, "batch_post_reset_agent_energy", None),
        "agent_materials": getattr(args, "batch_post_reset_agent_materials", None),
        "common_pool_food": getattr(args, "batch_post_reset_common_pool_food", None),
        "common_pool_energy": getattr(args, "batch_post_reset_common_pool_energy", None),
        "common_pool_materials": getattr(args, "batch_post_reset_common_pool_materials", None),
    }
    if not profile_name and all(value is None for value in explicit.values()):
        return None

    resolved = dict(explicit)
    if profile_name:
        defaults = _batch_post_reset_profile_defaults(profile_name)
        for key, value in defaults.items():
            if resolved.get(key) is None:
                resolved[key] = value

    return {
        "profile": profile_name or "custom",
        "activation": str(resolved.get("activation") or "after_reset"),
        "agent_food": (float(resolved["agent_food"]) if resolved["agent_food"] is not None else None),
        "agent_energy": (float(resolved["agent_energy"]) if resolved["agent_energy"] is not None else None),
        "agent_materials": (float(resolved["agent_materials"]) if resolved["agent_materials"] is not None else None),
        "common_pool_food": (float(resolved["common_pool_food"]) if resolved["common_pool_food"] is not None else None),
        "common_pool_energy": (float(resolved["common_pool_energy"]) if resolved["common_pool_energy"] is not None else None),
        "common_pool_materials": (
            float(resolved["common_pool_materials"]) if resolved["common_pool_materials"] is not None else None
        ),
    }


def _build_tuning_result_stub(*, tuning: dict[str, Any], reason: str) -> dict[str, Any]:
    agent_targets = {}
    for resource_type, key in (
        ("food", "agent_food"),
        ("energy", "agent_energy"),
        ("materials", "agent_materials"),
    ):
        value = tuning.get(key)
        if value is not None:
            agent_targets[resource_type] = float(value)

    pool_targets = {}
    for resource_type, key in (
        ("food", "common_pool_food"),
        ("energy", "common_pool_energy"),
        ("materials", "common_pool_materials"),
    ):
        value = tuning.get(key)
        if value is not None:
            pool_targets[resource_type] = float(value)

    return {
        "applied": False,
        "reason": reason,
        "profile": str(tuning.get("profile") or "custom"),
        "activation": str(tuning.get("activation") or "after_reset"),
        "agent_resource_targets": agent_targets,
        "common_pool_targets": pool_targets,
    }


def _reserve_stress_runtime_overrides(tuning: dict[str, Any] | None) -> dict[str, Any]:
    if not tuning:
        return {}
    if str(tuning.get("profile") or "") != "reserve_stress_v2":
        return {}
    # Give the post-law stressed cycle time to land before the provider-failure
    # guardrail sees another burst of parse retries and checkpoint traffic.
    return {
        "AGENT_LOOP_DELAY_SECONDS": 90,
        "LLM_ACTION_PARSE_RETRY_ATTEMPTS": 0,
        "LLM_ACTION_MAX_TOKENS": 220,
    }


def _apply_batch_post_reset_tuning(*, tuning: dict[str, Any], reason: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        agent_updates: dict[str, float] = {}
        for resource_type, key in (
            ("food", "agent_food"),
            ("energy", "agent_energy"),
            ("materials", "agent_materials"),
        ):
            value = tuning.get(key)
            if value is None:
                continue
            db.execute(
                text(
                    """
                    UPDATE agent_inventory
                    SET quantity = :quantity
                    WHERE resource_type = :resource_type
                    """
                ),
                {"resource_type": resource_type, "quantity": Decimal(str(value))},
            )
            agent_updates[resource_type] = float(value)

        pool_updates: dict[str, float] = {}
        for resource_type, key in (
            ("food", "common_pool_food"),
            ("energy", "common_pool_energy"),
            ("materials", "common_pool_materials"),
        ):
            value = tuning.get(key)
            if value is None:
                continue
            db.execute(
                text(
                    """
                    UPDATE global_resources
                    SET in_common_pool = :quantity,
                        total_amount = GREATEST(total_amount, :quantity)
                    WHERE resource_type = :resource_type
                    """
                ),
                {"resource_type": resource_type, "quantity": Decimal(str(value))},
            )
            pool_updates[resource_type] = float(value)

        db.commit()
        return {
            "applied": True,
            "reason": reason,
            "profile": str(tuning.get("profile") or "custom"),
            "activation": str(tuning.get("activation") or "after_reset"),
            "agent_resource_targets": agent_updates,
            "common_pool_targets": pool_updates,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _reserve_law_activation_state(*, run_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        started_at, _ = _run_window_for(db, run_id=run_id)
        reserve_laws = [
            law
            for law in active_survival_reserve_laws(db)
            if law.passed_at is not None and law.passed_at >= started_at
        ]
        first_passed_at = min((law.passed_at for law in reserve_laws if law.passed_at is not None), default=None)
        return {
            "active_reserve_law_count": int(len(reserve_laws)),
            "first_reserve_law_passed_at": first_passed_at.isoformat() if first_passed_at is not None else None,
        }
    finally:
        db.close()


def _run_window_for(db, *, run_id: str) -> tuple[datetime, datetime]:
    row = db.execute(
        text(
            """
            SELECT started_at, ended_at
            FROM simulation_runs
            WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id},
    ).first()

    started_at = None
    ended_at = None
    if row:
        started_at = row.started_at
        ended_at = row.ended_at

    if started_at is None:
        started_at = db.execute(
            text("SELECT MIN(created_at) FROM llm_usage WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
    if started_at is None:
        started_at = _utc_now()

    if ended_at is None:
        ended_at = db.execute(
            text("SELECT MAX(created_at) FROM llm_usage WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
    if ended_at is None:
        ended_at = _utc_now()
    if ended_at < started_at:
        ended_at = started_at
    return started_at, ended_at


def _event_counts_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> dict[str, int]:
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
    return {str(row.event_type): int(row.count or 0) for row in rows if str(row.event_type or "").strip()}


def _distinct_event_agents_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> int:
    run_fragment = f'%"{run_id}"%'
    value = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT e.agent_id)
            FROM events e
            WHERE e.created_at >= :started_at
              AND e.created_at <= :ended_at
              AND e.agent_id IS NOT NULL
              AND (
                e.agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
                OR CAST(e.event_metadata AS TEXT) LIKE :run_fragment
              )
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).scalar()
    return int(value or 0)


def _proposal_diagnostics_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> dict[str, Any]:
    run_fragment = f'%"{run_id}"%'
    summary_row = db.execute(
        text(
            """
            WITH scoped_events AS (
              SELECT e.*
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
            ),
            first_proposal AS (
              SELECT MIN(e.created_at) AS first_proposal_at
              FROM scoped_events e
              WHERE e.event_type = 'create_proposal'
            )
            SELECT
              COUNT(*) FILTER (
                WHERE e.event_type = 'create_proposal'
              ) AS proposal_actions,
              COUNT(*) FILTER (
                WHERE e.event_type = 'create_proposal'
                  AND COALESCE(e.event_metadata -> 'runtime' ->> 'mode', '') = 'checkpoint'
              ) AS checkpoint_proposal_actions,
              COUNT(*) FILTER (
                WHERE e.event_type = 'create_proposal'
                  AND COALESCE(e.event_metadata -> 'runtime' ->> 'checkpoint_reason', '') LIKE 'interrupt_%'
              ) AS interrupt_proposal_actions,
              COUNT(*) FILTER (
                WHERE e.event_type = 'invalid_action'
                  AND (e.event_metadata -> 'action' ->> 'action') = 'create_proposal'
              ) AS invalid_create_proposal_attempts,
              COUNT(DISTINCT CASE
                WHEN e.event_type = 'create_proposal'
                THEN e.agent_id
                ELSE NULL
              END) AS proposal_author_agents,
              COUNT(DISTINCT CASE
                WHEN e.event_type = 'invalid_action'
                  AND (e.event_metadata -> 'action' ->> 'action') = 'create_proposal'
                THEN e.agent_id
                ELSE NULL
              END) AS invalid_proposal_attempt_agents,
              COUNT(*) FILTER (
                WHERE e.event_type IN ('forum_post', 'forum_reply')
                  AND (fp.first_proposal_at IS NULL OR e.created_at < fp.first_proposal_at)
              ) AS forum_actions_before_first_proposal,
              COUNT(DISTINCT CASE
                WHEN e.event_type IN ('forum_post', 'forum_reply')
                  AND (fp.first_proposal_at IS NULL OR e.created_at < fp.first_proposal_at)
                THEN e.agent_id
                ELSE NULL
              END) AS forum_authors_before_first_proposal,
              MIN(EXTRACT(EPOCH FROM (fp.first_proposal_at - :started_at))) AS seconds_to_first_proposal
            FROM scoped_events e
            CROSS JOIN first_proposal fp
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).first()

    invalid_reason_rows = db.execute(
        text(
            """
            SELECT
              COALESCE(NULLIF(e.event_metadata ->> 'reason', ''), 'unknown') AS reason,
              COUNT(*) AS count
            FROM events e
            WHERE e.created_at >= :started_at
              AND e.created_at <= :ended_at
              AND e.event_type = 'invalid_action'
              AND (e.event_metadata -> 'action' ->> 'action') = 'create_proposal'
              AND (
                e.agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
                OR CAST(e.event_metadata AS TEXT) LIKE :run_fragment
              )
            GROUP BY COALESCE(NULLIF(e.event_metadata ->> 'reason', ''), 'unknown')
            ORDER BY COUNT(*) DESC, reason ASC
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).fetchall()

    proposal_type_rows = db.execute(
        text(
            """
            SELECT
              COALESCE(NULLIF(e.event_metadata -> 'action' ->> 'proposal_type', ''), 'other') AS proposal_type,
              COUNT(*) AS count
            FROM events e
            WHERE e.created_at >= :started_at
              AND e.created_at <= :ended_at
              AND e.event_type = 'create_proposal'
              AND (
                e.agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
                OR CAST(e.event_metadata AS TEXT) LIKE :run_fragment
              )
            GROUP BY COALESCE(NULLIF(e.event_metadata -> 'action' ->> 'proposal_type', ''), 'other')
            ORDER BY COUNT(*) DESC, proposal_type ASC
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).fetchall()

    seconds_to_first_proposal = None
    if summary_row and summary_row.seconds_to_first_proposal is not None:
        seconds_to_first_proposal = int(max(0, float(summary_row.seconds_to_first_proposal or 0)))

    diagnostics = {
        "proposal_actions": int((summary_row.proposal_actions if summary_row else 0) or 0),
        "checkpoint_proposal_actions": int((summary_row.checkpoint_proposal_actions if summary_row else 0) or 0),
        "interrupt_proposal_actions": int((summary_row.interrupt_proposal_actions if summary_row else 0) or 0),
        "invalid_create_proposal_attempts": int((summary_row.invalid_create_proposal_attempts if summary_row else 0) or 0),
        "proposal_author_agents": int((summary_row.proposal_author_agents if summary_row else 0) or 0),
        "invalid_proposal_attempt_agents": int((summary_row.invalid_proposal_attempt_agents if summary_row else 0) or 0),
        "forum_actions_before_first_proposal": int((summary_row.forum_actions_before_first_proposal if summary_row else 0) or 0),
        "forum_authors_before_first_proposal": int((summary_row.forum_authors_before_first_proposal if summary_row else 0) or 0),
        "seconds_to_first_proposal": seconds_to_first_proposal,
        "invalid_create_proposal_reasons": {
            str(row.reason): int(row.count or 0)
            for row in invalid_reason_rows
            if str(row.reason or "").strip()
        },
        "proposal_types": {
            str(row.proposal_type): int(row.count or 0)
            for row in proposal_type_rows
            if str(row.proposal_type or "").strip()
        },
    }
    return diagnostics


def _vote_diagnostics_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> dict[str, Any]:
    run_fragment = f'%"{run_id}"%'
    summary_row = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE (e.event_metadata -> 'runtime' ->> 'checkpoint_reason') = 'interrupt_proposal_deadline'
              ) AS proposal_deadline_interrupt_actions,
              COUNT(*) FILTER (
                WHERE e.event_type = 'vote'
              ) AS vote_actions,
              COUNT(*) FILTER (
                WHERE e.event_type = 'invalid_action'
                  AND (e.event_metadata -> 'action' ->> 'action') = 'vote'
              ) AS invalid_vote_attempts,
              COUNT(*) FILTER (
                WHERE (e.event_metadata -> 'runtime' ->> 'checkpoint_reason') = 'interrupt_proposal_deadline'
                  AND e.event_type = 'vote'
              ) AS vote_actions_from_deadline_interrupt,
              COUNT(*) FILTER (
                WHERE (e.event_metadata -> 'runtime' ->> 'checkpoint_reason') = 'interrupt_proposal_deadline'
                  AND e.event_type = 'invalid_action'
                  AND (e.event_metadata -> 'action' ->> 'action') = 'vote'
              ) AS invalid_vote_attempts_from_deadline_interrupt,
              COUNT(*) FILTER (
                WHERE (e.event_metadata -> 'runtime' ->> 'checkpoint_reason') = 'interrupt_proposal_deadline'
                  AND e.event_type NOT IN ('vote', 'invalid_action')
              ) AS non_vote_actions_from_deadline_interrupt,
              COUNT(DISTINCT CASE
                WHEN (e.event_metadata -> 'runtime' ->> 'checkpoint_reason') = 'interrupt_proposal_deadline'
                THEN e.agent_id
                ELSE NULL
              END) AS agents_with_deadline_interrupt
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
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).first()

    reason_rows = db.execute(
        text(
            """
            SELECT
              COALESCE(NULLIF(e.event_metadata ->> 'reason', ''), 'unknown') AS reason,
              COUNT(*) AS count
            FROM events e
            WHERE e.created_at >= :started_at
              AND e.created_at <= :ended_at
              AND e.event_type = 'invalid_action'
              AND (e.event_metadata -> 'action' ->> 'action') = 'vote'
              AND (
                e.agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
                OR CAST(e.event_metadata AS TEXT) LIKE :run_fragment
              )
            GROUP BY COALESCE(NULLIF(e.event_metadata ->> 'reason', ''), 'unknown')
            ORDER BY COUNT(*) DESC, reason ASC
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).fetchall()

    diagnostics = {
        "proposal_deadline_interrupt_actions": int((summary_row.proposal_deadline_interrupt_actions if summary_row else 0) or 0),
        "vote_actions": int((summary_row.vote_actions if summary_row else 0) or 0),
        "invalid_vote_attempts": int((summary_row.invalid_vote_attempts if summary_row else 0) or 0),
        "vote_actions_from_deadline_interrupt": int((summary_row.vote_actions_from_deadline_interrupt if summary_row else 0) or 0),
        "invalid_vote_attempts_from_deadline_interrupt": int((summary_row.invalid_vote_attempts_from_deadline_interrupt if summary_row else 0) or 0),
        "non_vote_actions_from_deadline_interrupt": int((summary_row.non_vote_actions_from_deadline_interrupt if summary_row else 0) or 0),
        "agents_with_deadline_interrupt": int((summary_row.agents_with_deadline_interrupt if summary_row else 0) or 0),
        "invalid_vote_reasons": {
            str(row.reason): int(row.count or 0)
            for row in reason_rows
            if str(row.reason or "").strip()
        },
    }
    return diagnostics


def _law_effect_diagnostics_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> dict[str, Any]:
    run_fragment = f'%"{run_id}"%'
    law_rows = db.execute(
        text(
            """
            SELECT
              l.id AS law_id,
              l.proposal_id AS proposal_id,
              l.title AS title,
              l.passed_at AS passed_at,
              COALESCE(p.votes_for, 0) AS votes_for,
              COALESCE(p.votes_against, 0) AS votes_against,
              COALESCE(p.votes_abstain, 0) AS votes_abstain
            FROM laws l
            LEFT JOIN proposals p ON p.id = l.proposal_id
            WHERE l.passed_at >= :started_at
              AND l.passed_at <= :ended_at
              AND (
                p.created_at >= :started_at
                OR p.author_agent_id IN (
                    SELECT DISTINCT u.agent_id
                    FROM llm_usage u
                    WHERE u.run_id = :run_id
                      AND u.agent_id IS NOT NULL
                )
              )
            ORDER BY l.passed_at ASC, l.id ASC
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    ).mappings().all()

    scoped_events = db.execute(
        text(
            """
            SELECT
              e.id,
              e.agent_id,
              e.event_type,
              e.created_at
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
            ORDER BY e.created_at ASC, e.id ASC
            """
        ),
        {
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "run_fragment": run_fragment,
        },
    ).mappings().all()

    per_law: list[dict[str, Any]] = []
    for law_row in law_rows:
        passed_at = law_row.get("passed_at")
        if passed_at is None:
            continue
        window_end = min(ended_at, passed_at + timedelta(seconds=POST_LAW_WINDOW_SECONDS))
        follow_on_events = [
            event
            for event in scoped_events
            if event.get("created_at") is not None
            and event["created_at"] > passed_at
            and event["created_at"] <= window_end
        ]
        counts = Counter(
            str(event.get("event_type") or "")
            for event in follow_on_events
            if str(event.get("event_type") or "").strip()
        )
        per_law.append(
            {
                "law_id": int(law_row.get("law_id") or 0),
                "proposal_id": int(law_row.get("proposal_id") or 0),
                "title": str(law_row.get("title") or ""),
                "passed_at": passed_at.isoformat(),
                "votes_for": int(law_row.get("votes_for") or 0),
                "votes_against": int(law_row.get("votes_against") or 0),
                "votes_abstain": int(law_row.get("votes_abstain") or 0),
                "window_seconds_observed": int(max(0.0, float((window_end - passed_at).total_seconds()))),
                "follow_on_total_events": int(len(follow_on_events)),
                "follow_on_meaningful_events": int(
                    sum(
                        count
                        for event_type, count in counts.items()
                        if event_type in MEANINGFUL_INTERESTINGNESS_EVENT_TYPES
                        or event_type in POST_LAW_NON_GOVERNANCE_EVENT_TYPES
                    )
                ),
                "follow_on_non_governance_events": int(
                    sum(count for event_type, count in counts.items() if event_type in POST_LAW_NON_GOVERNANCE_EVENT_TYPES)
                ),
                "follow_on_forum_actions": int(counts.get("forum_post", 0) + counts.get("forum_reply", 0)),
                "follow_on_trade_actions": int(counts.get("trade", 0)),
                "follow_on_work_actions": int(counts.get("work", 0)),
                "follow_on_conflict_events": int(sum(counts.get(event_type, 0) for event_type in CONFLICT_EVENT_TYPES)),
                "follow_on_cooperation_events": int(sum(counts.get(event_type, 0) for event_type in COOPERATION_EVENT_TYPES)),
                "follow_on_proposal_actions": int(counts.get("create_proposal", 0)),
                "follow_on_vote_actions": int(counts.get("vote", 0)),
                "follow_on_unique_event_agents": int(
                    len({int(event["agent_id"]) for event in follow_on_events if event.get("agent_id") is not None})
                ),
            }
        )

    first_law = per_law[0] if per_law else {}
    seconds_to_first_law = None
    seconds_remaining_after_first_law = None
    if law_rows:
        first_passed_at = law_rows[0].get("passed_at")
        if first_passed_at is not None:
            seconds_to_first_law = int(max(0.0, float((first_passed_at - started_at).total_seconds())))
            seconds_remaining_after_first_law = int(max(0.0, float((ended_at - first_passed_at).total_seconds())))

    return {
        "laws_passed": int(len(per_law)),
        "window_seconds": int(POST_LAW_WINDOW_SECONDS),
        "seconds_to_first_law": seconds_to_first_law,
        "seconds_remaining_after_first_law": seconds_remaining_after_first_law,
        "passed_law_titles": [str(item.get("title") or "") for item in per_law if str(item.get("title") or "").strip()],
        "laws_with_any_follow_on_activity": int(sum(1 for item in per_law if int(item.get("follow_on_total_events") or 0) > 0)),
        "laws_with_non_governance_follow_on_activity": int(
            sum(1 for item in per_law if int(item.get("follow_on_non_governance_events") or 0) > 0)
        ),
        "follow_on_total_events_after_first_law": int(first_law.get("follow_on_total_events") or 0),
        "follow_on_meaningful_events_after_first_law": int(first_law.get("follow_on_meaningful_events") or 0),
        "follow_on_non_governance_events_after_first_law": int(first_law.get("follow_on_non_governance_events") or 0),
        "follow_on_forum_actions_after_first_law": int(first_law.get("follow_on_forum_actions") or 0),
        "follow_on_trade_actions_after_first_law": int(first_law.get("follow_on_trade_actions") or 0),
        "follow_on_work_actions_after_first_law": int(first_law.get("follow_on_work_actions") or 0),
        "follow_on_conflict_events_after_first_law": int(first_law.get("follow_on_conflict_events") or 0),
        "follow_on_cooperation_events_after_first_law": int(first_law.get("follow_on_cooperation_events") or 0),
        "follow_on_proposal_actions_after_first_law": int(first_law.get("follow_on_proposal_actions") or 0),
        "follow_on_vote_actions_after_first_law": int(first_law.get("follow_on_vote_actions") or 0),
        "follow_on_unique_event_agents_after_first_law": int(first_law.get("follow_on_unique_event_agents") or 0),
        "per_law": per_law,
    }


def _reserve_readiness_diagnostics_for_run(db, *, run_id: str, started_at: datetime, ended_at: datetime) -> dict[str, Any]:
    run_agent_rows = db.execute(
        text(
            """
            SELECT DISTINCT u.agent_id
            FROM llm_usage u
            WHERE u.run_id = :run_id
              AND u.agent_id IS NOT NULL
            ORDER BY u.agent_id ASC
            """
        ),
        {"run_id": run_id},
    ).fetchall()
    run_agent_ids = [int(row.agent_id) for row in run_agent_rows if row.agent_id is not None]

    inventory_rows = []
    if run_agent_ids:
        inventory_map: dict[int, dict[str, Any]] = {}
        for row in (
            db.query(Agent)
            .filter(Agent.id.in_(run_agent_ids))
            .order_by(Agent.agent_number.asc())
            .all()
        ):
            inventory_map[int(row.id)] = {
                "agent_id": int(row.id),
                "agent_number": int(row.agent_number or 0),
                "status": str(row.status or ""),
                "starvation_cycles": int(row.starvation_cycles or 0),
                "food": Decimal("0"),
                "energy": Decimal("0"),
            }

        for row in (
            db.query(AgentInventory)
            .filter(
                AgentInventory.agent_id.in_(run_agent_ids),
                AgentInventory.resource_type.in_(("food", "energy")),
            )
            .all()
        ):
            agent_inventory = inventory_map.get(int(row.agent_id or 0))
            if not agent_inventory:
                continue
            agent_inventory[str(row.resource_type)] = Decimal(str(row.quantity or 0))

        inventory_rows = list(inventory_map.values())

    reserve_laws = active_survival_reserve_laws(db)
    reserve_pool_rows = db.query(GlobalResources).filter(GlobalResources.resource_type.in_(("food", "energy"))).all()
    reserve_pools = {
        str(row.resource_type): float(row.in_common_pool or 0)
        for row in reserve_pool_rows
    }

    run_agent_id_set = set(run_agent_ids)
    scoped_reserve_events: list[tuple[Event, str | None, int | None]] = []
    for event_row, display_name, agent_number in (
        db.query(Event, Agent.display_name, Agent.agent_number)
        .outerjoin(Agent, Agent.id == Event.agent_id)
        .filter(
            Event.created_at >= started_at,
            Event.created_at <= ended_at,
            Event.event_type.in_(
                [
                    "reserve_aid",
                    "reserve_shortfall",
                    "became_dormant",
                    "starvation_warning",
                    "agent_revived",
                ]
            ),
        )
        .order_by(Event.created_at.asc(), Event.id.asc())
        .all()
    ):
        if not _event_matches_run_scope(event_row, run_id=run_id, run_agent_ids=run_agent_id_set):
            continue
        scoped_reserve_events.append((event_row, display_name, agent_number))

    reserve_event_counts = dict(
        Counter(
            str(event_row.event_type or "")
            for event_row, _display_name, _agent_number in scoped_reserve_events
            if str(event_row.event_type or "").strip() in {
                "reserve_aid",
                "reserve_shortfall",
                "became_dormant",
                "starvation_warning",
                "agent_died",
            }
        )
    )

    reserve_trace_rows = []
    for event_row, display_name, agent_number in scoped_reserve_events:
        metadata = event_row.event_metadata or {}
        reserve_trace_rows.append(
            {
                "id": int(event_row.id),
                "created_at": ensure_utc(event_row.created_at) if event_row.created_at is not None else None,
                "event_type": str(event_row.event_type or ""),
                "agent_id": int(event_row.agent_id) if event_row.agent_id is not None else None,
                "agent_number": int(agent_number) if agent_number is not None else None,
                "display_name": str(display_name or "") or None,
                "description": str(event_row.description or "") or None,
                "status_before": metadata.get("status_before"),
                "support_mode": metadata.get("support_mode"),
                "aid_granted": metadata.get("aid_granted"),
                "pre_food": metadata.get("pre_food"),
                "pre_energy": metadata.get("pre_energy"),
                "food_deficit": metadata.get("food_deficit"),
                "energy_deficit": metadata.get("energy_deficit"),
                "reserve_pool_food_before": metadata.get("reserve_pool_food_before"),
                "reserve_pool_energy_before": metadata.get("reserve_pool_energy_before"),
                "reserve_pool_food_after": metadata.get("reserve_pool_food_after"),
                "reserve_pool_energy_after": metadata.get("reserve_pool_energy_after"),
            }
        )
    reserve_trace = _build_first_cycle_reserve_trace(reserve_trace_rows)

    min_food = None
    min_energy = None
    agents_below_active_survival_threshold = 0
    agents_below_dormant_survival_threshold = 0
    agents_near_active_survival_threshold = 0
    dormant_agents = 0
    starving_agents = 0

    for row in inventory_rows:
        food = float(row.get("food") or 0)
        energy = float(row.get("energy") or 0)
        min_food = food if min_food is None else min(min_food, food)
        min_energy = energy if min_energy is None else min(min_energy, energy)
        if food < 1.0 or energy < 1.0:
            agents_below_active_survival_threshold += 1
        if food < 0.25 or energy < 0.25:
            agents_below_dormant_survival_threshold += 1
        if food < 2.0 or energy < 2.0:
            agents_near_active_survival_threshold += 1
        if str(row.get("status") or "") == "dormant":
            dormant_agents += 1
        if int(row.get("starvation_cycles") or 0) > 0:
            starving_agents += 1

    return {
        "run_agent_count": int(len(run_agent_ids)),
        "active_reserve_law_count": int(len(reserve_laws)),
        "active_reserve_law_titles": [
            str(law.title or "")
            for law in reserve_laws
            if str(law.title or "").strip()
        ],
        "reserve_pool_food": float(reserve_pools.get("food", 0.0)),
        "reserve_pool_energy": float(reserve_pools.get("energy", 0.0)),
        "min_agent_food": (round(float(min_food), 2) if min_food is not None else None),
        "min_agent_energy": (round(float(min_energy), 2) if min_energy is not None else None),
        "agents_near_active_survival_threshold": int(agents_near_active_survival_threshold),
        "agents_below_active_survival_threshold": int(agents_below_active_survival_threshold),
        "agents_below_dormant_survival_threshold": int(agents_below_dormant_survival_threshold),
        "dormant_agents": int(dormant_agents),
        "agents_with_starvation_cycles": int(starving_agents),
        "reserve_event_counts": reserve_event_counts,
        "first_reserve_event_at": reserve_trace.get("first_reserve_event_at"),
        "trace_window_seconds": int(reserve_trace.get("trace_window_seconds") or 0),
        "first_cycle_trace": reserve_trace.get("first_cycle_trace") or [],
        "no_reserve_demand_signal": bool(
            int(agents_below_active_survival_threshold) == 0
            and int(dormant_agents) == 0
            and int(starving_agents) == 0
            and int(reserve_event_counts.get("reserve_aid", 0)) == 0
            and int(reserve_event_counts.get("reserve_shortfall", 0)) == 0
            and int(reserve_event_counts.get("became_dormant", 0)) == 0
            and int(reserve_event_counts.get("starvation_warning", 0)) == 0
            and int(reserve_event_counts.get("agent_died", 0)) == 0
        ),
    }


def _summarize_run(*, run_id: str, condition_name: str | None, season_number: int | None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        run_summary = generate_and_record_run_summary(
            db,
            run_id=run_id,
            condition_name=condition_name,
            season_number=season_number,
        )
        payload = dict(run_summary.get("payload") or {})
        artifacts = dict(run_summary.get("artifacts") or {})

        started_at, ended_at = _run_window_for(db, run_id=run_id)
        event_counts = _event_counts_for_run(db, run_id=run_id, started_at=started_at, ended_at=ended_at)
        emergence = compute_emergence_metrics(
            db,
            window_start=started_at,
            window_end=ended_at,
        )
        distinct_agents = _distinct_event_agents_for_run(
            db,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        proposal_diagnostics = _proposal_diagnostics_for_run(
            db,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        vote_diagnostics = _vote_diagnostics_for_run(
            db,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        law_effect_diagnostics = _law_effect_diagnostics_for_run(
            db,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        reserve_readiness_diagnostics = _reserve_readiness_diagnostics_for_run(
            db,
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    action_counter = Counter({key: value for key, value in event_counts.items() if key in ACTION_EVENT_TYPES})
    interaction_events = sum(event_counts.get(name, 0) for name in INTERACTION_EVENT_TYPES)
    unique_action_types = len([key for key, value in action_counter.items() if int(value) > 0])
    action_entropy_bits = round(_safe_entropy(list(action_counter.values())), 4)
    run_started_at = _iso_to_dt(payload.get("run_started_at")) or started_at
    run_ended_at = _iso_to_dt(payload.get("run_ended_at")) or ended_at
    run_seconds = max(
        0.0,
        float((run_ended_at - run_started_at).total_seconds()),
    )

    derived = {
        "interaction_events": int(interaction_events),
        "distinct_event_agents": int(distinct_agents),
        "unique_action_types": int(unique_action_types),
        "action_entropy_bits": float(action_entropy_bits),
        "event_counts": dict(sorted(event_counts.items())),
        "runtime_seconds": int(run_seconds),
    }
    return {
        "run_id": run_id,
        "condition_name": condition_name,
        "season_number": season_number,
        "technical_report": _load_technical_report(run_id),
        "run_summary": payload,
        "run_summary_artifacts": artifacts,
        "emergence_metrics": emergence,
        "derived_metrics": derived,
        "proposal_diagnostics": proposal_diagnostics,
        "vote_diagnostics": vote_diagnostics,
        "law_effect_diagnostics": law_effect_diagnostics,
        "reserve_readiness_diagnostics": reserve_readiness_diagnostics,
    }


def _evaluate_smoke(summary: dict[str, Any], run_metrics: dict[str, Any]) -> list[CriterionResult]:
    technical = summary.get("technical_report") or {}
    run_summary = summary.get("run_summary") or {}
    metrics = run_summary.get("metrics") or {}
    technical_activity = technical.get("activity") or {}
    derived = summary.get("derived_metrics") or {}

    llm_calls = int(metrics.get("llm_calls") or 0)
    total_events = int(technical_activity.get("total_events") or metrics.get("total_events") or 0)
    interaction_events = int(
        (technical_activity.get("forum_actions") or 0)
        + (technical_activity.get("trade_actions") or 0)
        + (technical_activity.get("cooperation_events") or 0)
        or (derived.get("interaction_events") or 0)
    )
    governance_actions = int(technical_activity.get("proposal_actions") or metrics.get("proposal_actions") or 0) + int(
        technical_activity.get("vote_actions") or metrics.get("vote_actions") or 0
    )

    return [
        CriterionResult(
            name="llm_activity",
            passed=llm_calls >= 5,
            detail=f"llm_calls={llm_calls} threshold=5",
        ),
        CriterionResult(
            name="event_volume",
            passed=total_events >= 40,
            detail=f"total_events={total_events} threshold=40",
        ),
        CriterionResult(
            name="interaction_signal",
            passed=interaction_events >= 3,
            detail=f"interaction_events={interaction_events} threshold=3",
        ),
        CriterionResult(
            name="governance_signal",
            passed=(governance_actions >= 1),
            detail=(
                f"proposal_actions={int(technical_activity.get('proposal_actions') or metrics.get('proposal_actions') or 0)} "
                f"vote_actions={int(technical_activity.get('vote_actions') or metrics.get('vote_actions') or 0)}"
            ),
        ),
    ]


def _evaluate_controlled_run(summary: dict[str, Any]) -> dict[str, CriterionResult]:
    technical = summary.get("technical_report") or {}
    run_summary = summary.get("run_summary") or {}
    metrics = run_summary.get("metrics") or {}
    technical_activity = technical.get("activity") or {}

    total_events = int(technical_activity.get("total_events") or metrics.get("total_events") or 0)
    forum_actions = int(technical_activity.get("forum_actions") or metrics.get("forum_actions") or 0)
    trade_actions = int(technical_activity.get("trade_actions") or 0)
    interaction_events = forum_actions + trade_actions
    inequality_gini = float(technical.get("inequality_gini_current") or 0.0)
    conflict_events = int(technical_activity.get("conflict_events") or metrics.get("conflict_events") or 0)
    governance_actions = int(technical_activity.get("proposal_actions") or metrics.get("proposal_actions") or 0) + int(
        technical_activity.get("vote_actions") or metrics.get("vote_actions") or 0
    )
    cooperation_events = int(technical_activity.get("cooperation_events") or metrics.get("cooperation_events") or 0)
    checkpoint_actions = int(technical_activity.get("checkpoint_actions") or 0)

    return {
        "interaction": CriterionResult(
            name="interaction",
            passed=((interaction_events + cooperation_events) >= 6),
            detail=f"forum_plus_trade={interaction_events} cooperation_events={cooperation_events} combined_threshold=6",
        ),
        "competition": CriterionResult(
            name="competition",
            passed=(conflict_events >= 1) or (inequality_gini >= 0.007),
            detail=f"conflict_events={conflict_events} threshold=1 OR inequality_gini={inequality_gini:.4f} threshold=0.007",
        ),
        "governance": CriterionResult(
            name="governance",
            passed=(governance_actions >= 1),
            detail=f"governance_actions={governance_actions} threshold=1",
        ),
        "emergent_behavior": CriterionResult(
            name="emergent_behavior",
            passed=(checkpoint_actions >= 40 and total_events >= 50 and cooperation_events >= 3),
            detail=(
                f"checkpoint_actions={checkpoint_actions} threshold=40; "
                f"total_events={total_events} threshold=50; "
                f"cooperation_events={cooperation_events} threshold=3"
            ),
        ),
    }


def _evaluate_interestingness_run(summary: dict[str, Any]) -> dict[str, CriterionResult]:
    technical = summary.get("technical_report") or {}
    run_summary = summary.get("run_summary") or {}
    metrics = run_summary.get("metrics") or {}
    technical_activity = technical.get("activity") or {}
    key_moments = technical.get("key_moments") or []
    derived = summary.get("derived_metrics") or {}
    event_counts = derived.get("event_counts") or {}

    total_events = int(technical_activity.get("total_events") or metrics.get("total_events") or 0)
    forum_actions = int(technical_activity.get("forum_actions") or metrics.get("forum_actions") or 0)
    trade_actions = int(technical_activity.get("trade_actions") or 0)
    proposal_actions = int(technical_activity.get("proposal_actions") or metrics.get("proposal_actions") or 0)
    vote_actions = int(technical_activity.get("vote_actions") or metrics.get("vote_actions") or 0)
    laws_passed = int(technical_activity.get("laws_passed") or metrics.get("laws_passed") or 0)
    cooperation_events = int(technical_activity.get("cooperation_events") or metrics.get("cooperation_events") or 0)
    conflict_events = int(technical_activity.get("conflict_events") or metrics.get("conflict_events") or 0)
    checkpoint_actions = int(technical_activity.get("checkpoint_actions") or 0)
    inequality_gini = float(technical.get("inequality_gini_current") or 0.0)
    unique_moment_types = len({str(item.get("event_type") or "").strip() for item in key_moments if str(item.get("event_type") or "").strip()})
    meaningful_action_types = len(
        [
            key
            for key, value in event_counts.items()
            if int(value or 0) > 0 and key in MEANINGFUL_INTERESTINGNESS_EVENT_TYPES
        ]
    )

    return {
        "interaction": CriterionResult(
            name="interaction",
            passed=((forum_actions + trade_actions + cooperation_events) >= 8),
            detail=(
                f"forum_actions={forum_actions} trade_actions={trade_actions} "
                f"cooperation_events={cooperation_events} combined_threshold=8"
            ),
        ),
        "competition": CriterionResult(
            name="competition",
            passed=(conflict_events >= 1) or (trade_actions >= 1) or (inequality_gini >= 0.009),
            detail=(
                f"conflict_events={conflict_events} threshold=1 OR trade_actions={trade_actions} threshold=1 "
                f"OR inequality_gini={inequality_gini:.4f} threshold=0.009"
            ),
        ),
        "governance": CriterionResult(
            name="governance",
            passed=(vote_actions >= 1) or (laws_passed >= 1),
            detail=(
                f"vote_actions={vote_actions} threshold=1 OR laws_passed={laws_passed} threshold=1; "
                f"proposal_actions={proposal_actions}"
            ),
        ),
        "emergent_behavior": CriterionResult(
            name="emergent_behavior",
            passed=(
                checkpoint_actions >= 40
                and total_events >= 80
                and unique_moment_types >= 3
                and meaningful_action_types >= 3
            ),
            detail=(
                f"checkpoint_actions={checkpoint_actions} threshold=40; "
                f"total_events={total_events} threshold=80; "
                f"unique_key_moment_types={unique_moment_types} threshold=3; "
                f"meaningful_action_types={meaningful_action_types} threshold=3"
            ),
        ),
    }


def _category_pass_counts(results: list[dict[str, CriterionResult]]) -> dict[str, int]:
    counts: dict[str, int] = Counter()
    for result in results:
        for key, item in result.items():
            if item.passed:
                counts[key] += 1
    return dict(counts)


def _batch_success_control(results: list[dict[str, CriterionResult]], comparison_payload: dict[str, Any]) -> list[CriterionResult]:
    counts = _category_pass_counts(results)
    total_runs = len(results)
    replicate_count = int(comparison_payload.get("replicate_count") or 0)
    threshold_met = bool(comparison_payload.get("meets_replicate_threshold"))

    return [
        CriterionResult(
            name="interaction",
            passed=int(counts.get("interaction", 0)) >= total_runs,
            detail=f"passes={int(counts.get('interaction', 0))}/{total_runs} required={total_runs}",
        ),
        CriterionResult(
            name="competition",
            passed=int(counts.get("competition", 0)) >= 2,
            detail=f"passes={int(counts.get('competition', 0))}/{total_runs} required=2",
        ),
        CriterionResult(
            name="governance",
            passed=int(counts.get("governance", 0)) >= 2,
            detail=f"passes={int(counts.get('governance', 0))}/{total_runs} required=2",
        ),
        CriterionResult(
            name="emergent_behavior",
            passed=int(counts.get("emergent_behavior", 0)) >= total_runs,
            detail=f"passes={int(counts.get('emergent_behavior', 0))}/{total_runs} required={total_runs}",
        ),
        CriterionResult(
            name="replicate_gate",
            passed=threshold_met and replicate_count >= 3,
            detail=f"replicate_count={replicate_count} threshold=3 meets_threshold={threshold_met}",
        ),
    ]


def _batch_success_interestingness(
    results: list[dict[str, CriterionResult]],
    comparison_payload: dict[str, Any] | None = None,
) -> list[CriterionResult]:
    counts = _category_pass_counts(results)
    total_runs = max(1, len(results))
    comparison_payload = comparison_payload or {}
    return [
        CriterionResult(
            name="interaction",
            passed=int(counts.get("interaction", 0)) >= 1,
            detail=f"passes={int(counts.get('interaction', 0))}/{total_runs} required>=1",
        ),
        CriterionResult(
            name="competition",
            passed=int(counts.get("competition", 0)) >= 1,
            detail=f"passes={int(counts.get('competition', 0))}/{total_runs} required>=1",
        ),
        CriterionResult(
            name="governance",
            passed=int(counts.get("governance", 0)) >= 1,
            detail=f"passes={int(counts.get('governance', 0))}/{total_runs} required>=1",
        ),
        CriterionResult(
            name="emergent_behavior",
            passed=int(counts.get("emergent_behavior", 0)) >= 1,
            detail=f"passes={int(counts.get('emergent_behavior', 0))}/{total_runs} required>=1",
        ),
        CriterionResult(
            name="interestingness_run_count",
            passed=total_runs >= 1,
            detail=f"run_count={total_runs} required>=1",
        ),
        CriterionResult(
            name="replicate_gate",
            passed=True,
            detail=(
                "interestingness mode does not require replicate threshold; "
                f"comparison_replicates={int(comparison_payload.get('replicate_count') or 0)}"
            ),
        ),
    ]


def _write_eval_artifacts(*, outdir: Path, payload: dict[str, Any]) -> dict[str, str]:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "behavior_eval_results.json"
    md_path = outdir / "behavior_eval_results.md"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    smoke = payload.get("smoke") or {}
    batch = payload.get("batch") or {}
    lines = [
        "# Behavior Eval Results",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Mode: {payload.get('mode')}",
        f"- API base: {payload.get('api_base')}",
        f"- Smoke run: {((smoke.get('run') or {}).get('run_id'))}",
        f"- Batch condition: {batch.get('condition_name')}",
        "",
        "## Smoke",
        "",
    ]
    for item in smoke.get("criteria") or []:
        lines.append(f"- {'PASS' if item.get('passed') else 'FAIL'} {item.get('name')}: {item.get('detail')}")

    lines.extend(["", "## Batch Runs", ""])
    for run in batch.get("runs") or []:
        lines.append(f"### {run.get('run_id')}")
        lines.append("")
        post_reset_tuning = run.get("post_reset_tuning") or {}
        if post_reset_tuning:
            lines.append(
                "- Batch tuning: "
                f"profile={post_reset_tuning.get('profile')}, "
                f"activation={post_reset_tuning.get('activation')}, "
                f"applied={bool(post_reset_tuning.get('applied'))}, "
                f"agent_resource_targets={post_reset_tuning.get('agent_resource_targets')}, "
                f"common_pool_targets={post_reset_tuning.get('common_pool_targets')}"
            )
            if post_reset_tuning.get("activation_observed_at_utc"):
                lines.append(
                    "- Batch tuning trigger: "
                    f"activation_observed_at_utc={post_reset_tuning.get('activation_observed_at_utc')}, "
                    f"trigger_reserve_law_count={post_reset_tuning.get('trigger_reserve_law_count')}, "
                    f"first_reserve_law_passed_at={post_reset_tuning.get('trigger_first_reserve_law_passed_at')}"
                )
        for category, result in (run.get("criteria") or {}).items():
            lines.append(f"- {'PASS' if result.get('passed') else 'FAIL'} {category}: {result.get('detail')}")
        proposal_diagnostics = ((run.get("summary") or {}).get("proposal_diagnostics") or {})
        if proposal_diagnostics:
            seconds_to_first_proposal = proposal_diagnostics.get("seconds_to_first_proposal")
            seconds_text = "none"
            if seconds_to_first_proposal is not None:
                seconds_text = str(int(seconds_to_first_proposal))
            lines.append(
                "- Proposal diagnostics: "
                f"proposal_actions={int(proposal_diagnostics.get('proposal_actions') or 0)}, "
                f"invalid_create_proposal_attempts={int(proposal_diagnostics.get('invalid_create_proposal_attempts') or 0)}, "
                f"proposal_author_agents={int(proposal_diagnostics.get('proposal_author_agents') or 0)}, "
                f"forum_actions_before_first_proposal={int(proposal_diagnostics.get('forum_actions_before_first_proposal') or 0)}, "
                f"seconds_to_first_proposal={seconds_text}"
            )
        vote_diagnostics = ((run.get("summary") or {}).get("vote_diagnostics") or {})
        if vote_diagnostics:
            lines.append(
                "- Vote diagnostics: "
                f"deadline_interrupt_actions={int(vote_diagnostics.get('proposal_deadline_interrupt_actions') or 0)}, "
                f"vote_actions={int(vote_diagnostics.get('vote_actions') or 0)}, "
                f"invalid_vote_attempts={int(vote_diagnostics.get('invalid_vote_attempts') or 0)}, "
                f"non_vote_actions_from_deadline_interrupt={int(vote_diagnostics.get('non_vote_actions_from_deadline_interrupt') or 0)}"
            )
        law_effect_diagnostics = ((run.get("summary") or {}).get("law_effect_diagnostics") or {})
        if law_effect_diagnostics:
            lines.append(
                "- Law effects: "
                f"laws_passed={int(law_effect_diagnostics.get('laws_passed') or 0)}, "
                f"seconds_to_first_law={law_effect_diagnostics.get('seconds_to_first_law')}, "
                f"follow_on_non_governance_events_after_first_law={int(law_effect_diagnostics.get('follow_on_non_governance_events_after_first_law') or 0)}, "
                f"laws_with_non_governance_follow_on_activity={int(law_effect_diagnostics.get('laws_with_non_governance_follow_on_activity') or 0)}"
            )
        reserve_readiness = ((run.get("summary") or {}).get("reserve_readiness_diagnostics") or {})
        if reserve_readiness:
            reserve_events = reserve_readiness.get("reserve_event_counts") or {}
            lines.append(
                "- Reserve readiness: "
                f"active_reserve_law_count={int(reserve_readiness.get('active_reserve_law_count') or 0)}, "
                f"reserve_pool_food={float(reserve_readiness.get('reserve_pool_food') or 0.0):.2f}, "
                f"reserve_pool_energy={float(reserve_readiness.get('reserve_pool_energy') or 0.0):.2f}, "
                f"min_agent_food={reserve_readiness.get('min_agent_food')}, "
                f"min_agent_energy={reserve_readiness.get('min_agent_energy')}, "
                f"agents_below_active_survival_threshold={int(reserve_readiness.get('agents_below_active_survival_threshold') or 0)}, "
                f"reserve_aid={int(reserve_events.get('reserve_aid', 0) or 0)}, "
                f"reserve_shortfall={int(reserve_events.get('reserve_shortfall', 0) or 0)}, "
                f"no_reserve_demand_signal={bool(reserve_readiness.get('no_reserve_demand_signal'))}"
            )
        lines.append("")

    lines.extend(["## Batch Gates", ""])
    for item in batch.get("batch_criteria") or []:
        lines.append(f"- {'PASS' if item.get('passed') else 'FAIL'} {item.get('name')}: {item.get('detail')}")

    comparison = batch.get("condition_comparison") or {}
    lines.extend(
        [
            "",
            "## Condition Comparison",
            "",
            f"- Replicate count: {comparison.get('replicate_count')}",
            f"- Threshold met: {comparison.get('meets_replicate_threshold')}",
            f"- Selected run class: {comparison.get('selected_run_class')}",
            f"- Selected duration bucket: {comparison.get('selected_duration_bucket_hours')}",
        ]
    )
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _criterion_dict(item: CriterionResult) -> dict[str, Any]:
    return asdict(item)


def _smoke_ready(payload: dict[str, Any] | None = None, *, run_metrics: dict[str, Any] | None = None, elapsed_seconds: float | None = None) -> bool:
    del elapsed_seconds
    payload = run_metrics if run_metrics is not None else payload or {}
    llm = payload.get("llm") or {}
    activity = payload.get("activity") or {}
    governance = payload.get("governance") or {}
    combined = int(activity.get("forum_actions") or 0) + int(governance.get("proposals_created") or 0) + int(
        governance.get("votes_cast") or 0
    )
    return int(llm.get("calls") or 0) >= 5 and combined >= 3


def _control_ready(payload: dict[str, Any] | None = None, *, run_metrics: dict[str, Any] | None = None, elapsed_seconds: float | None = None) -> bool:
    del elapsed_seconds
    payload = run_metrics if run_metrics is not None else payload or {}
    llm = payload.get("llm") or {}
    activity = payload.get("activity") or {}
    governance = payload.get("governance") or {}
    combined = int(activity.get("forum_actions") or 0) + int(governance.get("proposals_created") or 0) + int(
        governance.get("votes_cast") or 0
    )
    return int(llm.get("calls") or 0) >= 8 and combined >= 5


def _interestingness_ready(
    payload: dict[str, Any] | None = None,
    *,
    run_metrics: dict[str, Any] | None = None,
    elapsed_seconds: float | None = None,
) -> bool:
    del elapsed_seconds
    payload = run_metrics if run_metrics is not None else payload or {}
    llm = payload.get("llm") or {}
    activity = payload.get("activity") or {}
    governance = payload.get("governance") or {}

    llm_calls = int(llm.get("calls") or 0)
    checkpoint_actions = int(activity.get("checkpoint_actions") or 0)
    forum_actions = int(activity.get("forum_actions") or 0)
    proposal_actions = int(governance.get("proposals_created") or 0)
    vote_actions = int(governance.get("votes_cast") or 0)
    combined_social = forum_actions + proposal_actions + vote_actions
    governance_actions = proposal_actions + vote_actions

    return (
        llm_calls >= 30
        and checkpoint_actions >= 40
        and combined_social >= 10
        and governance_actions >= 3
        and vote_actions >= 1
    )


def _reserve_profile_post_law_min_runtime_seconds(
    *,
    tuning: dict[str, Any] | None,
    day_length_minutes: int | None,
    poll_seconds: int,
) -> int:
    if not tuning:
        return 0
    if str(tuning.get("profile") or "") != "reserve_stress_v2":
        return 0
    if str(tuning.get("activation") or "") != "after_first_reserve_law":
        return 0
    # Leave enough wall-clock time for one full survival cycle after staged
    # scarcity is applied, plus one poll interval so the harness can observe it.
    cycle_seconds = max(300, int(day_length_minutes or 0) * 60)
    return cycle_seconds + max(1, int(poll_seconds))


def _run_until(
    admin: AdminClient,
    *,
    run_id: str,
    timeout_seconds: int,
    poll_seconds: int,
    min_runtime_seconds: int = 0,
    predicate,
    on_poll=None,
) -> dict[str, Any]:
    started = time.time()
    snapshots: list[dict[str, Any]] = []
    while True:
        run_metrics = admin.run_metrics(run_id=run_id)
        snapshots.append(run_metrics)
        elapsed = time.time() - started
        if on_poll is not None:
            on_poll(run_metrics=run_metrics, elapsed_seconds=elapsed, snapshots=snapshots)
        if elapsed >= float(min_runtime_seconds) and predicate(run_metrics=run_metrics, elapsed_seconds=elapsed):
            return {"reason": "criteria_met", "snapshots": snapshots}
        if elapsed >= float(timeout_seconds):
            return {"reason": "timeout", "snapshots": snapshots}
        time.sleep(max(1, int(poll_seconds)))


def _resolve_mode_preset(
    *,
    mode: str,
    smoke_seconds: int | None,
    batch_seconds: int | None,
    batch_runs: int | None,
    smoke_condition: str | None,
    condition: str | None,
    run_class: str | None,
    day_length_minutes: int | None,
) -> dict[str, Any]:
    preset = MODE_PRESETS[mode]
    return {
        "preset": preset,
        "smoke_seconds": int(smoke_seconds or preset.smoke_seconds),
        "batch_seconds": int(batch_seconds or preset.batch_seconds),
        "batch_runs": int(batch_runs or preset.batch_runs),
        "smoke_condition": str(smoke_condition or preset.smoke_condition),
        "condition": str(condition or preset.batch_condition),
        "run_class": str(run_class or preset.batch_run_class),
        "batch_min_runtime_seconds": int(preset.batch_min_runtime_seconds),
        "day_length_minutes": (
            int(day_length_minutes)
            if day_length_minutes is not None
            else (int(preset.day_length_minutes) if preset.day_length_minutes is not None else None)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a short behavior eval plan.")
    parser.add_argument("--mode", choices=tuple(MODE_PRESETS.keys()), default="control")
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--admin-token", default=(os.environ.get("ADMIN_API_TOKEN") or settings.ADMIN_API_TOKEN))
    parser.add_argument("--actor", default="codex-behavior-eval")
    parser.add_argument("--smoke-seconds", type=int, default=None)
    parser.add_argument("--batch-seconds", type=int, default=None)
    parser.add_argument("--batch-runs", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--smoke-condition", default=None)
    parser.add_argument(
        "--run-class",
        choices=("standard_72h", "deep_96h", "special_exploratory"),
        default=None,
    )
    parser.add_argument("--proposal-voting-hours", type=float, default=0.10)
    parser.add_argument("--proposal-resolution-seconds", type=int, default=60)
    parser.add_argument("--enforcement-resolution-seconds", type=int, default=60)
    parser.add_argument("--day-length-minutes", type=int, default=None)
    parser.add_argument(
        "--batch-post-reset-profile",
        choices=("reserve_stress_v1", "reserve_stress_v2"),
        default="",
        help="Optional batch-only scarcity profile applied either after reset or after the first reserve law passes.",
    )
    parser.add_argument("--batch-post-reset-agent-food", type=float, default=None)
    parser.add_argument("--batch-post-reset-agent-energy", type=float, default=None)
    parser.add_argument("--batch-post-reset-agent-materials", type=float, default=None)
    parser.add_argument("--batch-post-reset-common-pool-food", type=float, default=None)
    parser.add_argument("--batch-post-reset-common-pool-energy", type=float, default=None)
    parser.add_argument("--batch-post-reset-common-pool-materials", type=float, default=None)
    parser.add_argument("--run-prefix", default=f"behavior-eval-{_utc_now().strftime('%Y%m%dT%H%M%SZ').lower()}")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    resolved = _resolve_mode_preset(
        mode=str(args.mode),
        smoke_seconds=args.smoke_seconds,
        batch_seconds=args.batch_seconds,
        batch_runs=args.batch_runs,
        smoke_condition=args.smoke_condition,
        condition=args.condition,
        run_class=args.run_class,
        day_length_minutes=args.day_length_minutes,
    )
    preset: ModePreset = resolved["preset"]

    if not str(args.admin_token or "").strip():
        raise SystemExit("ADMIN_API_TOKEN is required")
    if int(resolved["batch_runs"]) < 1:
        raise SystemExit("--batch-runs must be >= 1")

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if str(args.output_dir or "").strip()
        else (_repo_root() / "output" / "evals" / _slug(args.run_prefix))
    )
    batch_post_reset_tuning = _resolve_batch_post_reset_tuning(args)

    admin = AdminClient(api_base=str(args.api_base), token=str(args.admin_token), actor=str(args.actor))
    try:
        status = admin.status()
        runtime_override_keys = [
            "AGENT_LOOP_DELAY_SECONDS",
            "DAY_LENGTH_MINUTES",
            "PROPOSAL_VOTING_HOURS",
            "PROPOSAL_RESOLUTION_INTERVAL_SECONDS",
            "ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS",
            "LLM_ACTION_PARSE_RETRY_ATTEMPTS",
            "LLM_ACTION_MAX_TOKENS",
        ]
        runtime_before = _read_runtime_settings(keys=runtime_override_keys)
        runtime_restored = False
        restore_result: dict[str, Any] | None = None
        runtime_updates = {
            "AGENT_LOOP_DELAY_SECONDS": 60,
            "PROPOSAL_VOTING_HOURS": float(args.proposal_voting_hours),
            "PROPOSAL_RESOLUTION_INTERVAL_SECONDS": int(args.proposal_resolution_seconds),
            "ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS": int(args.enforcement_resolution_seconds),
            "LLM_ACTION_PARSE_RETRY_ATTEMPTS": 2,
            "LLM_ACTION_MAX_TOKENS": 350,
        }
        if resolved["day_length_minutes"] is not None:
            runtime_updates["DAY_LENGTH_MINUTES"] = int(resolved["day_length_minutes"])
        runtime_updates.update(_reserve_stress_runtime_overrides(batch_post_reset_tuning))
        config_result = admin.patch_config(runtime_updates, reason="behavior_eval_runtime_overrides")

        try:
            smoke_run_id = f"{args.run_prefix}-smoke"[:64]
            smoke_start = _start_run_with_retry(
                admin,
                payload={
                    "mode": "test",
                    "run_id": smoke_run_id,
                    "condition_name": str(resolved["smoke_condition"]),
                    "protocol_version": "protocol_v1",
                    "hypothesis_id": "behavior_eval_smoke",
                    "run_class": "standard_72h",
                    "reset_world": True,
                    "reason": "behavior_eval_smoke_start",
                },
            )

            smoke_wait = _run_until(
                admin,
                run_id=smoke_run_id,
                timeout_seconds=int(resolved["smoke_seconds"]),
                poll_seconds=int(args.poll_seconds),
                predicate=_smoke_ready,
            )
            smoke_metrics = smoke_wait["snapshots"][-1]
            smoke_stop = admin.stop_run(reason="behavior_eval_smoke_stop", clear_run_id=True)
            smoke_summary = _summarize_run(
                run_id=smoke_run_id,
                condition_name=str(resolved["smoke_condition"]),
                season_number=None,
            )
            smoke_summary["behavior_eval_snapshot_artifacts"] = _write_behavior_eval_run_snapshot(
                run_id=smoke_run_id,
                payload=smoke_summary,
            )
            smoke_criteria = _evaluate_smoke(smoke_summary, smoke_metrics)
            time.sleep(10)

            batch_runs: list[dict[str, Any]] = []
            batch_results: list[dict[str, CriterionResult]] = []
            for index in range(1, int(resolved["batch_runs"]) + 1):
                run_id = f"{args.run_prefix}-b{index}"[:64]
                reserve_post_law_min_runtime_seconds = _reserve_profile_post_law_min_runtime_seconds(
                    tuning=batch_post_reset_tuning,
                    day_length_minutes=resolved.get("day_length_minutes"),
                    poll_seconds=int(args.poll_seconds),
                )
                reserve_post_law_runtime_gate_seconds = 0
                batch_payload = {
                    "mode": "test",
                    "run_id": run_id,
                    "condition_name": str(resolved["condition"]),
                    "protocol_version": "protocol_v1",
                    "hypothesis_id": ("behavior_eval_control" if str(args.mode) == "control" else "behavior_eval_interestingness"),
                    "run_class": str(resolved["run_class"]),
                    "reset_world": True,
                    "reason": f"behavior_eval_batch_start_{index}",
                }
                post_reset_tuning_result = None
                post_reset_tuning_activation = (
                    str((batch_post_reset_tuning or {}).get("activation") or "after_reset")
                    if batch_post_reset_tuning
                    else ""
                )
                if batch_post_reset_tuning and post_reset_tuning_activation == "after_reset":
                    admin.reset_dev_world(reason=f"behavior_eval_batch_reset_{index}")
                    post_reset_tuning_result = _apply_batch_post_reset_tuning(
                        tuning=batch_post_reset_tuning,
                        reason=f"behavior_eval_batch_post_reset_tuning_{index}",
                    )
                    batch_payload["reset_world"] = False
                elif batch_post_reset_tuning:
                    post_reset_tuning_result = _build_tuning_result_stub(
                        tuning=batch_post_reset_tuning,
                        reason=f"behavior_eval_batch_post_reset_tuning_{index}",
                    )
                _start_run_with_retry(admin, payload=batch_payload)

                def _batch_poll_hook(
                    *,
                    run_metrics: dict[str, Any],
                    elapsed_seconds: float,
                    snapshots: list[dict[str, Any]],
                ) -> None:
                    del run_metrics, snapshots
                    nonlocal post_reset_tuning_result, reserve_post_law_runtime_gate_seconds
                    if not batch_post_reset_tuning or not post_reset_tuning_result:
                        return
                    if str(post_reset_tuning_result.get("activation") or "") != "after_first_reserve_law":
                        return
                    if bool(post_reset_tuning_result.get("applied")):
                        return

                    reserve_law_state = _reserve_law_activation_state(run_id=run_id)
                    if int(reserve_law_state.get("active_reserve_law_count") or 0) < 1:
                        return

                    applied_result = _apply_batch_post_reset_tuning(
                        tuning=batch_post_reset_tuning,
                        reason=f"behavior_eval_batch_post_reset_tuning_{index}",
                    )
                    applied_result["activation_observed_at_utc"] = _utc_now().isoformat()
                    applied_result["trigger_reserve_law_count"] = int(
                        reserve_law_state.get("active_reserve_law_count") or 0
                    )
                    applied_result["trigger_first_reserve_law_passed_at"] = reserve_law_state.get(
                        "first_reserve_law_passed_at"
                    )
                    if reserve_post_law_min_runtime_seconds > 0:
                        reserve_post_law_runtime_gate_seconds = int(elapsed_seconds) + int(
                            reserve_post_law_min_runtime_seconds
                        )
                    post_reset_tuning_result = applied_result

                def _batch_ready(*, run_metrics: dict[str, Any], elapsed_seconds: float) -> bool:
                    if elapsed_seconds < float(
                        max(
                            int(resolved["batch_min_runtime_seconds"]) if str(args.mode) == "interestingness" else 0,
                            reserve_post_law_runtime_gate_seconds,
                        )
                    ):
                        return False
                    return (
                        _control_ready(run_metrics)
                        if str(args.mode) == "control"
                        else _interestingness_ready(run_metrics)
                    )

                wait_result = _run_until(
                    admin,
                    run_id=run_id,
                    timeout_seconds=int(resolved["batch_seconds"]),
                    poll_seconds=int(args.poll_seconds),
                    min_runtime_seconds=0,
                    predicate=_batch_ready,
                    on_poll=_batch_poll_hook if batch_post_reset_tuning else None,
                )
                admin.stop_run(reason=f"behavior_eval_batch_stop_{index}", clear_run_id=True)
                summary = _summarize_run(run_id=run_id, condition_name=str(resolved["condition"]), season_number=None)
                summary["behavior_eval_snapshot_artifacts"] = _write_behavior_eval_run_snapshot(
                    run_id=run_id,
                    payload=summary,
                )
                criteria = (
                    _evaluate_controlled_run(summary)
                    if str(args.mode) == "control"
                    else _evaluate_interestingness_run(summary)
                )
                batch_results.append(criteria)
                batch_runs.append(
                    {
                        "run_id": run_id,
                        "wait_result": {
                            "reason": str(wait_result.get("reason") or ""),
                            "last_snapshot": wait_result["snapshots"][-1],
                            "snapshot_count": len(wait_result["snapshots"]),
                        },
                        "post_reset_tuning": post_reset_tuning_result,
                        "criteria": {key: _criterion_dict(value) for key, value in criteria.items()},
                        "summary": summary,
                    }
                )

            db = SessionLocal()
            try:
                comparison = generate_and_record_condition_comparison(
                    db,
                    condition_name=str(resolved["condition"]),
                    min_replicates=3,
                    season_number=None,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

            comparison_payload = dict(comparison.get("payload") or {})
            comparison_artifacts = dict(comparison.get("artifacts") or {})
            batch_criteria = (
                _batch_success_control(batch_results, comparison_payload)
                if str(args.mode) == "control"
                else _batch_success_interestingness(batch_results, comparison_payload)
            )

            restore_result = admin.patch_config(runtime_before, reason="behavior_eval_restore_runtime")
            runtime_restored = True

            payload = {
                "generated_at_utc": _utc_now().isoformat(),
                "mode": str(args.mode),
                "mode_description": preset.description,
                "api_base": str(args.api_base),
                "initial_status": status,
                "config_patch": config_result,
                "config_restore": restore_result,
                "runtime_overrides": runtime_updates,
                "batch_post_reset_tuning": batch_post_reset_tuning,
                "smoke": {
                    "start": smoke_start,
                    "wait_result": {
                        "reason": str(smoke_wait.get("reason") or ""),
                        "last_snapshot": smoke_metrics,
                        "snapshot_count": len(smoke_wait["snapshots"]),
                    },
                    "stop": smoke_stop,
                    "run": smoke_summary,
                    "criteria": [_criterion_dict(item) for item in smoke_criteria],
                },
                "batch": {
                    "condition_name": str(resolved["condition"]),
                    "run_class": str(resolved["run_class"]),
                    "runs": batch_runs,
                    "batch_criteria": [_criterion_dict(item) for item in batch_criteria],
                    "condition_comparison": comparison_payload,
                    "condition_comparison_artifacts": comparison_artifacts,
                },
            }
            artifacts = _write_eval_artifacts(outdir=output_dir, payload=payload)
            payload["eval_artifacts"] = artifacts
            Path(artifacts["json"]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        finally:
            if not runtime_restored:
                try:
                    admin.patch_config(runtime_before, reason="behavior_eval_restore_runtime")
                except Exception:
                    pass
    finally:
        admin.close()


if __name__ == "__main__":
    raise SystemExit(main())
