"""Internal admin/ops API (private, token-protected)."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
import subprocess
import sys
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, text
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminActor, require_admin_auth
from app.core.config import settings
from app.core.database import get_db
from app.core.time import now_utc
from app.models.models import AdminConfigChange
from app.services.kpi_rollups import get_recent_rollups
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget

router = APIRouter()


class ConfigPatchRequest(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=500)


class ModeChangeRequest(BaseModel):
    mode: str = Field(..., pattern="^(test|real)$")
    reason: str | None = Field(default=None, max_length=500)


class ControlRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RunStartRequest(BaseModel):
    mode: str = Field(..., pattern="^(test|real)$")
    run_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9:_-]*$")
    reset_world: bool = Field(default=False)
    reason: str | None = Field(default=None, max_length=500)


class RunStopRequest(BaseModel):
    clear_run_id: bool = Field(default=False)
    reason: str | None = Field(default=None, max_length=500)


def _assert_writes_enabled() -> None:
    if not bool(getattr(settings, "ADMIN_WRITE_ENABLED", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin write controls are disabled in this environment",
        )


def _effective_environment() -> str:
    return str(getattr(settings, "ENVIRONMENT", "development") or "development").strip().lower()


def _normalize_run_id(raw_value: str | None, mode: str) -> str:
    clean = str(raw_value or "").strip()
    if clean:
        return clean
    return f"{mode}-{now_utc().strftime('%Y%m%dT%H%M%SZ')}"


def _run_seed_reset() -> dict[str, Any]:
    if _effective_environment() == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="World reset is blocked in production",
        )

    backend_root = Path(__file__).resolve().parents[2]
    command = [sys.executable, "scripts/seed_agents.py", "--reset"]
    try:
        completed = subprocess.run(
            command,
            cwd=str(backend_root),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Reset script timed out") from exc

    if completed.returncode != 0:
        stderr_tail = "\n".join((completed.stderr or "").strip().splitlines()[-6:])
        stdout_tail = "\n".join((completed.stdout or "").strip().splitlines()[-6:])
        detail_parts = [part for part in [stderr_tail, stdout_tail] if part]
        detail = "Reset/reseed failed"
        if detail_parts:
            detail = f"{detail}: {' | '.join(detail_parts)}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    stdout_lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    return {
        "ok": True,
        "command": " ".join(command),
        "output_tail": stdout_lines[-8:],
    }


@router.get("/status")
def admin_status(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    effective = runtime_config_service.get_effective(db)
    budget = usage_budget.get_snapshot()
    return {
        "environment": getattr(settings, "ENVIRONMENT", "development"),
        "admin_write_enabled": bool(getattr(settings, "ADMIN_WRITE_ENABLED", False)),
        "server_time_utc": now_utc().isoformat(),
        "viewer_ops": {
            "run_mode": effective.get("SIMULATION_RUN_MODE"),
            "run_id": str(effective.get("SIMULATION_RUN_ID") or "").strip(),
            "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
            "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
            "force_cheapest_route": bool(effective.get("FORCE_CHEAPEST_ROUTE", False)),
        },
        "llm_budget": {
            "day_key": budget.day_key.isoformat(),
            "calls_total": int(budget.calls_total),
            "calls_openrouter_free": int(budget.calls_openrouter_free),
            "calls_groq": int(budget.calls_groq),
            "estimated_cost_usd": float(budget.estimated_cost_usd),
            "soft_cap_usd": float(effective.get("LLM_DAILY_BUDGET_USD_SOFT", 0.0) or 0.0),
            "hard_cap_usd": float(effective.get("LLM_DAILY_BUDGET_USD_HARD", 0.0) or 0.0),
        },
        "actor": {
            "id": actor.actor_id,
            "ip": actor.client_ip,
        },
    }


@router.get("/config")
def get_admin_config(
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    return runtime_config_service.get_config_payload(db)


@router.patch("/config")
def patch_admin_config(
    request: ConfigPatchRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    try:
        result = runtime_config_service.update_settings(
            db,
            updates=request.updates,
            changed_by=actor.actor_id,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


@router.get("/audit")
def get_admin_audit(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    items = runtime_config_service.list_audit_entries(db, limit=limit, offset=offset)
    return {
        "count": len(items),
        "limit": int(limit),
        "offset": int(offset),
        "items": items,
    }


@router.post("/control/pause")
def pause_simulation(
    request: ControlRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    runtime_config_service.update_settings(
        db,
        updates={"SIMULATION_PAUSED": True},
        changed_by=actor.actor_id,
        reason=request.reason or "pause",
    )
    return {"ok": True, "simulation_paused": True}


@router.post("/control/resume")
def resume_simulation(
    request: ControlRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    runtime_config_service.update_settings(
        db,
        updates={"SIMULATION_PAUSED": False},
        changed_by=actor.actor_id,
        reason=request.reason or "resume",
    )
    return {"ok": True, "simulation_paused": False}


@router.post("/control/degrade")
def enable_degraded_routing(
    request: ControlRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    runtime_config_service.update_settings(
        db,
        updates={"FORCE_CHEAPEST_ROUTE": True},
        changed_by=actor.actor_id,
        reason=request.reason or "degrade",
    )
    return {"ok": True, "force_cheapest_route": True}


@router.post("/control/degrade/clear")
def disable_degraded_routing(
    request: ControlRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    runtime_config_service.update_settings(
        db,
        updates={"FORCE_CHEAPEST_ROUTE": False},
        changed_by=actor.actor_id,
        reason=request.reason or "degrade_clear",
    )
    return {"ok": True, "force_cheapest_route": False}


@router.post("/control/run-mode")
def set_run_mode(
    request: ModeChangeRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()
    runtime_config_service.update_settings(
        db,
        updates={"SIMULATION_RUN_MODE": request.mode},
        changed_by=actor.actor_id,
        reason=request.reason or "run_mode_change",
    )
    return {"ok": True, "run_mode": request.mode}


@router.post("/control/run/start")
def start_simulation_run(
    request: RunStartRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()

    mode = str(request.mode or "").strip()
    run_id = _normalize_run_id(request.run_id, mode)

    if request.reset_world and mode != "test":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reset_world is only supported for test runs",
        )

    # Pause before any destructive maintenance.
    runtime_config_service.update_settings(
        db,
        updates={"SIMULATION_PAUSED": True},
        changed_by=actor.actor_id,
        reason=request.reason or f"run_start_{mode}_pre_pause",
    )

    reset_result = None
    if request.reset_world:
        reset_result = _run_seed_reset()

    runtime_config_service.update_settings(
        db,
        updates={
            "SIMULATION_RUN_MODE": mode,
            "SIMULATION_RUN_ID": run_id,
            "SIMULATION_ACTIVE": True,
            "SIMULATION_PAUSED": False,
        },
        changed_by=actor.actor_id,
        reason=request.reason or f"run_start_{mode}",
    )

    return {
        "ok": True,
        "mode": mode,
        "run_id": run_id,
        "simulation_active": True,
        "simulation_paused": False,
        "reset_world": bool(request.reset_world),
        "reset_result": reset_result,
    }


@router.post("/control/run/stop")
def stop_simulation_run(
    request: RunStopRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()

    updates: dict[str, Any] = {"SIMULATION_PAUSED": True}
    if request.clear_run_id:
        updates["SIMULATION_RUN_ID"] = ""

    result = runtime_config_service.update_settings(
        db,
        updates=updates,
        changed_by=actor.actor_id,
        reason=request.reason or "run_stop",
    )
    effective = result.get("effective") or {}
    return {
        "ok": True,
        "simulation_paused": bool(effective.get("SIMULATION_PAUSED", True)),
        "run_id": str(effective.get("SIMULATION_RUN_ID") or "").strip(),
    }


@router.post("/control/run/reset-dev")
def reset_dev_world(
    request: ControlRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_admin_auth),
):
    _assert_writes_enabled()

    runtime_config_service.update_settings(
        db,
        updates={"SIMULATION_PAUSED": True},
        changed_by=actor.actor_id,
        reason=request.reason or "dev_world_reset_pre_pause",
    )
    reset_result = _run_seed_reset()
    return {"ok": True, "simulation_paused": True, "reset_result": reset_result}


@router.get("/run/metrics")
def get_run_metrics(
    run_id: str | None = Query(default=None, max_length=64),
    hours_fallback: int = Query(default=24, ge=1, le=24 * 14),
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    effective = runtime_config_service.get_effective(db)
    resolved_run_id = str(run_id or effective.get("SIMULATION_RUN_ID") or "").strip()

    if not resolved_run_id:
        return {
            "run_id": "",
            "run_mode": str(effective.get("SIMULATION_RUN_MODE") or "test"),
            "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
            "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
            "run_started_at": None,
            "llm": {
                "calls": 0,
                "success_calls": 0,
                "fallback_calls": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
            "activity": {
                "checkpoint_actions": 0,
                "deterministic_actions": 0,
                "proposal_actions": 0,
                "vote_actions": 0,
                "forum_actions": 0,
                "forum_messages": 0,
            },
            "governance": {
                "proposals_created": 0,
                "active_proposals": 0,
                "votes_cast": 0,
            },
        }

    run_started_at = None
    if resolved_run_id:
        json_run_id = json.dumps(resolved_run_id)
        run_started_at = (
            db.query(AdminConfigChange)
            .filter(
                AdminConfigChange.key == "SIMULATION_RUN_ID",
                cast(AdminConfigChange.new_value, String) == json_run_id,
            )
            .order_by(AdminConfigChange.created_at.desc(), AdminConfigChange.id.desc())
            .first()
        )

    fallback_start = now_utc() - timedelta(hours=int(hours_fallback))
    since_ts = (run_started_at.created_at if run_started_at and run_started_at.created_at else fallback_start)

    llm_totals = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS fallback_calls,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE (:run_id = '' OR run_id = :run_id)
              AND created_at >= :since_ts
            """
        ),
        {"run_id": resolved_run_id, "since_ts": since_ts},
    ).first()

    runtime_actions = db.execute(
        text(
            """
            SELECT
              COALESCE(SUM(CASE WHEN (event_metadata -> 'runtime' ->> 'mode') = 'checkpoint' THEN 1 ELSE 0 END), 0) AS checkpoint_actions,
              COALESCE(SUM(CASE WHEN (event_metadata -> 'runtime' ->> 'mode') = 'deterministic_fallback' THEN 1 ELSE 0 END), 0) AS deterministic_actions,
              COALESCE(SUM(CASE WHEN event_type = 'create_proposal' THEN 1 ELSE 0 END), 0) AS proposal_actions,
              COALESCE(SUM(CASE WHEN event_type = 'vote' THEN 1 ELSE 0 END), 0) AS vote_actions,
              COALESCE(SUM(CASE WHEN event_type IN ('forum_post', 'forum_reply') THEN 1 ELSE 0 END), 0) AS forum_actions
            FROM events
            WHERE created_at >= :since_ts
            """
        ),
        {"since_ts": since_ts},
    ).first()

    governance = db.execute(
        text(
            """
            SELECT
              COALESCE(SUM(CASE WHEN created_at >= :since_ts THEN 1 ELSE 0 END), 0) AS proposals_created,
              COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) AS active_proposals
            FROM proposals
            """
        ),
        {"since_ts": since_ts},
    ).first()

    votes_cast = db.execute(
        text(
            """
            SELECT COUNT(*) AS votes_cast
            FROM votes
            WHERE created_at >= :since_ts
            """
        ),
        {"since_ts": since_ts},
    ).scalar() or 0

    forum_messages = db.execute(
        text(
            """
            SELECT COUNT(*) AS forum_messages
            FROM messages
            WHERE created_at >= :since_ts
              AND message_type IN ('forum_post', 'forum_reply')
            """
        ),
        {"since_ts": since_ts},
    ).scalar() or 0

    return {
        "run_id": resolved_run_id,
        "run_mode": str(effective.get("SIMULATION_RUN_MODE") or "test"),
        "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
        "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
        "run_started_at": since_ts.isoformat() if since_ts else None,
        "llm": {
            "calls": int((llm_totals.calls if llm_totals else 0) or 0),
            "success_calls": int((llm_totals.success_calls if llm_totals else 0) or 0),
            "fallback_calls": int((llm_totals.fallback_calls if llm_totals else 0) or 0),
            "total_tokens": int((llm_totals.total_tokens if llm_totals else 0) or 0),
            "estimated_cost_usd": float((llm_totals.estimated_cost_usd if llm_totals else 0.0) or 0.0),
        },
        "activity": {
            "checkpoint_actions": int((runtime_actions.checkpoint_actions if runtime_actions else 0) or 0),
            "deterministic_actions": int((runtime_actions.deterministic_actions if runtime_actions else 0) or 0),
            "proposal_actions": int((runtime_actions.proposal_actions if runtime_actions else 0) or 0),
            "vote_actions": int((runtime_actions.vote_actions if runtime_actions else 0) or 0),
            "forum_actions": int((runtime_actions.forum_actions if runtime_actions else 0) or 0),
            "forum_messages": int(forum_messages or 0),
        },
        "governance": {
            "proposals_created": int((governance.proposals_created if governance else 0) or 0),
            "active_proposals": int((governance.active_proposals if governance else 0) or 0),
            "votes_cast": int(votes_cast or 0),
        },
    }


@router.get("/kpi/rollups")
def get_kpi_rollups(
    days: int = Query(default=14, ge=1, le=90),
    refresh: bool = Query(default=True),
    db: Session = Depends(get_db),
    _actor: AdminActor = Depends(require_admin_auth),
):
    resolved_days = max(1, min(90, int(days or getattr(settings, "KPI_ROLLUP_LOOKBACK_DAYS_DEFAULT", 14))))
    try:
        payload = get_recent_rollups(db, days=resolved_days, refresh=bool(refresh))
    except Exception as e:
        message = str(e).lower()
        if "kpi_daily_rollups" in message and "does not exist" in message:
            return {
                "days": resolved_days,
                "generated_at": now_utc().isoformat(),
                "summary": {"latest_day_key": None, "latest": None, "seven_day_avg": {}},
                "items": [],
            }
        raise

    return {
        "days": resolved_days,
        "generated_at": now_utc().isoformat(),
        "summary": payload.get("summary") or {},
        "items": payload.get("items") or [],
    }
