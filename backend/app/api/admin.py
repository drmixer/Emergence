"""Internal admin/ops API (private, token-protected)."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
import subprocess
import sys
from threading import Lock
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

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
from app.services.run_reports import maybe_generate_run_closeout_bundle
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget

router = APIRouter()
logger = logging.getLogger(__name__)

_KPI_ALERT_NOTIFY_LOCK = Lock()
_KPI_ALERT_NOTIFY_LAST_SENT_AT = None
_KPI_ALERT_NOTIFY_LAST_FINGERPRINT = ""

_KPI_ALERT_RULES = (
    {
        "metric": "landing_to_run_ctr",
        "label": "Landing -> Run CTR",
        "warning_floor": 0.12,
        "critical_floor": 0.08,
        "drop_warning_ratio": 0.20,
        "drop_critical_ratio": 0.35,
        "sample_field": "landing_view_visitors",
        "min_sample": 40,
    },
    {
        "metric": "replay_completion_rate",
        "label": "Replay Completion Rate",
        "warning_floor": 0.50,
        "critical_floor": 0.35,
        "drop_warning_ratio": 0.20,
        "drop_critical_ratio": 0.35,
        "sample_field": "replay_start_visitors",
        "min_sample": 25,
    },
    {
        "metric": "d1_retention_rate",
        "label": "D1 Retention",
        "warning_floor": 0.20,
        "critical_floor": 0.12,
        "drop_warning_ratio": 0.25,
        "drop_critical_ratio": 0.40,
        "sample_field": "d1_cohort_size",
        "min_sample": 25,
    },
    {
        "metric": "d7_retention_rate",
        "label": "D7 Retention",
        "warning_floor": 0.10,
        "critical_floor": 0.06,
        "drop_warning_ratio": 0.25,
        "drop_critical_ratio": 0.40,
        "sample_field": "d7_cohort_size",
        "min_sample": 25,
    },
)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _build_kpi_alerts(summary: dict[str, Any]) -> dict[str, Any]:
    latest = summary.get("latest") if isinstance(summary, dict) else None
    seven_day_avg = summary.get("seven_day_avg") if isinstance(summary, dict) else None
    latest = latest if isinstance(latest, dict) else {}
    seven_day_avg = seven_day_avg if isinstance(seven_day_avg, dict) else {}

    alerts: list[dict[str, Any]] = []
    for rule in _KPI_ALERT_RULES:
        metric = str(rule["metric"])
        label = str(rule["label"])
        latest_value = _safe_float(latest.get(metric))
        if latest_value is None:
            continue

        sample_field = str(rule["sample_field"])
        min_sample = int(rule["min_sample"])
        sample_size = _safe_int(latest.get(sample_field))
        if sample_size < min_sample:
            continue

        severity = ""
        reasons: list[str] = []
        if latest_value < float(rule["critical_floor"]):
            severity = "critical"
            reasons.append("below_critical_floor")
        elif latest_value < float(rule["warning_floor"]):
            severity = "warning"
            reasons.append("below_warning_floor")

        baseline_value = _safe_float(seven_day_avg.get(metric))
        drop_ratio = None
        if baseline_value is not None and baseline_value > 0 and latest_value < baseline_value:
            drop_ratio = (baseline_value - latest_value) / baseline_value
            if drop_ratio >= float(rule["drop_critical_ratio"]):
                severity = "critical"
                reasons.append("drop_vs_7d_critical")
            elif drop_ratio >= float(rule["drop_warning_ratio"]):
                if severity != "critical":
                    severity = "warning"
                reasons.append("drop_vs_7d_warning")

        if not severity:
            continue

        message = (
            f"{label} is {_format_rate(latest_value)} "
            f"(7d avg {_format_rate(baseline_value)}; sample={sample_size})."
        )
        alerts.append(
            {
                "metric": metric,
                "label": label,
                "severity": severity,
                "message": message,
                "day_key": latest.get("day_key"),
                "latest_value": latest_value,
                "seven_day_avg_value": baseline_value,
                "drop_ratio": drop_ratio,
                "sample_field": sample_field,
                "sample_size": sample_size,
                "minimum_sample_size": min_sample,
                "reasons": reasons,
            }
        )

    critical_count = sum(1 for item in alerts if item.get("severity") == "critical")
    warning_count = sum(1 for item in alerts if item.get("severity") == "warning")
    status = "critical" if critical_count > 0 else ("warning" if warning_count > 0 else "ok")

    return {
        "status": status,
        "counts": {
            "critical": critical_count,
            "warning": warning_count,
        },
        "items": alerts,
    }


def _kpi_alert_fingerprint(alerts_payload: dict[str, Any], *, latest_day_key: str | None) -> str:
    items = alerts_payload.get("items") if isinstance(alerts_payload, dict) else None
    normalized_items = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "metric": item.get("metric"),
                "severity": item.get("severity"),
                "day_key": item.get("day_key"),
                "latest_value": round(float(item.get("latest_value") or 0.0), 6),
                "seven_day_avg_value": (
                    None if item.get("seven_day_avg_value") is None else round(float(item.get("seven_day_avg_value") or 0.0), 6)
                ),
                "sample_size": int(item.get("sample_size") or 0),
                "reasons": sorted([str(reason) for reason in (item.get("reasons") or [])]),
            }
        )
    normalized_items.sort(key=lambda row: (str(row.get("severity")), str(row.get("metric"))))
    return json.dumps(
        {
            "latest_day_key": latest_day_key,
            "alerts": normalized_items,
        },
        sort_keys=True,
    )


def _maybe_notify_kpi_alerts(*, alerts_payload: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    webhook_url = str(getattr(settings, "KPI_ALERT_WEBHOOK_URL", "") or "").strip()
    notify_enabled = bool(getattr(settings, "KPI_ALERT_WEBHOOK_ENABLED", False))
    cooldown_minutes = max(1, int(getattr(settings, "KPI_ALERT_NOTIFY_COOLDOWN_MINUTES", 60) or 60))
    if not notify_enabled:
        return {"enabled": False, "attempted": False, "sent": False, "reason": "disabled"}
    if not webhook_url:
        return {"enabled": True, "attempted": False, "sent": False, "reason": "missing_webhook_url"}

    counts = alerts_payload.get("counts") if isinstance(alerts_payload, dict) else None
    critical_count = int((counts or {}).get("critical") or 0)
    if critical_count <= 0:
        return {"enabled": True, "attempted": False, "sent": False, "reason": "no_critical_alerts"}

    latest_day_key = (summary or {}).get("latest_day_key")
    fingerprint = _kpi_alert_fingerprint(alerts_payload, latest_day_key=latest_day_key)
    now_ts = now_utc()

    global _KPI_ALERT_NOTIFY_LAST_SENT_AT
    global _KPI_ALERT_NOTIFY_LAST_FINGERPRINT
    with _KPI_ALERT_NOTIFY_LOCK:
        if (
            _KPI_ALERT_NOTIFY_LAST_SENT_AT is not None
            and _KPI_ALERT_NOTIFY_LAST_FINGERPRINT == fingerprint
            and (now_ts - _KPI_ALERT_NOTIFY_LAST_SENT_AT) < timedelta(minutes=cooldown_minutes)
        ):
            return {
                "enabled": True,
                "attempted": False,
                "sent": False,
                "reason": "cooldown_active",
                "cooldown_minutes": cooldown_minutes,
                "last_sent_at": _KPI_ALERT_NOTIFY_LAST_SENT_AT.isoformat(),
            }

    warning_count = int((counts or {}).get("warning") or 0)
    text_summary = (
        f"[{str(getattr(settings, 'ENVIRONMENT', 'development') or 'development')}] "
        f"KPI critical alerts: {critical_count} critical, {warning_count} warning"
        f"{f' (day {latest_day_key})' if latest_day_key else ''}"
    )
    notification_payload = {
        "text": text_summary,
        "source": "emergence.ops.kpi",
        "environment": str(getattr(settings, "ENVIRONMENT", "development") or "development"),
        "generated_at": now_ts.isoformat(),
        "latest_day_key": latest_day_key,
        "status": alerts_payload.get("status"),
        "counts": alerts_payload.get("counts") or {},
        "alerts": alerts_payload.get("items") or [],
        "summary": {
            "latest": (summary or {}).get("latest"),
            "seven_day_avg": (summary or {}).get("seven_day_avg"),
        },
    }

    body = json.dumps(notification_payload).encode("utf-8")
    req = urlrequest.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            status_code = int(response.getcode() or 0)
    except urlerror.HTTPError as exc:
        logger.warning("KPI alert webhook HTTP error: status=%s body=%s", exc.code, exc.read().decode("utf-8", "ignore")[:250])
        return {
            "enabled": True,
            "attempted": True,
            "sent": False,
            "reason": "http_error",
            "status_code": int(exc.code),
        }
    except Exception as exc:
        logger.warning("KPI alert webhook failed: %s", exc)
        return {
            "enabled": True,
            "attempted": True,
            "sent": False,
            "reason": str(exc),
        }

    with _KPI_ALERT_NOTIFY_LOCK:
        _KPI_ALERT_NOTIFY_LAST_SENT_AT = now_ts
        _KPI_ALERT_NOTIFY_LAST_FINGERPRINT = fingerprint

    return {
        "enabled": True,
        "attempted": True,
        "sent": 200 <= status_code < 300,
        "status_code": status_code,
        "cooldown_minutes": cooldown_minutes,
        "last_sent_at": now_ts.isoformat(),
    }


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
    condition_name: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z0-9:_-]*$")
    season_number: int | None = Field(default=None, ge=0, le=9999)
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
            "condition_name": str(effective.get("SIMULATION_CONDITION_NAME") or "").strip() or None,
            "season_number": (
                int(effective.get("SIMULATION_SEASON_NUMBER") or 0)
                if int(effective.get("SIMULATION_SEASON_NUMBER") or 0) > 0
                else None
            ),
            "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
            "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
            "force_cheapest_route": bool(effective.get("FORCE_CHEAPEST_ROUTE", False)),
        },
        "llm_budget": {
            "day_key": budget.day_key.isoformat(),
            "calls_total": int(budget.calls_total),
            "calls_openrouter_free": int(budget.calls_openrouter_free),
            "calls_groq": int(budget.calls_groq),
            "calls_gemini": int(budget.calls_gemini),
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
            "SIMULATION_CONDITION_NAME": str(request.condition_name or "").strip(),
            "SIMULATION_SEASON_NUMBER": int(request.season_number or 0),
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
        "condition_name": str(request.condition_name or "").strip() or None,
        "season_number": int(request.season_number or 0) or None,
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
    effective_before = runtime_config_service.get_effective(db)
    run_id_before = str(effective_before.get("SIMULATION_RUN_ID") or "").strip()
    condition_name_before = str(effective_before.get("SIMULATION_CONDITION_NAME") or "").strip() or None
    season_number_before = (
        int(effective_before.get("SIMULATION_SEASON_NUMBER") or 0)
        if int(effective_before.get("SIMULATION_SEASON_NUMBER") or 0) > 0
        else None
    )

    updates: dict[str, Any] = {"SIMULATION_PAUSED": True}
    if request.clear_run_id:
        updates["SIMULATION_RUN_ID"] = ""
        updates["SIMULATION_CONDITION_NAME"] = ""
        updates["SIMULATION_SEASON_NUMBER"] = 0

    result = runtime_config_service.update_settings(
        db,
        updates=updates,
        changed_by=actor.actor_id,
        reason=request.reason or "run_stop",
    )
    effective = result.get("effective") or {}
    report_bundle = maybe_generate_run_closeout_bundle(
        run_id=run_id_before,
        actor_id=f"admin:{actor.actor_id}",
        condition_name=condition_name_before,
        season_number=season_number_before,
    )
    return {
        "ok": True,
        "simulation_paused": bool(effective.get("SIMULATION_PAUSED", True)),
        "run_id": str(effective.get("SIMULATION_RUN_ID") or "").strip(),
        "report_bundle": report_bundle,
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
            "condition_name": str(effective.get("SIMULATION_CONDITION_NAME") or "").strip() or None,
            "season_number": (
                int(effective.get("SIMULATION_SEASON_NUMBER") or 0)
                if int(effective.get("SIMULATION_SEASON_NUMBER") or 0) > 0
                else None
            ),
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
        "condition_name": str(effective.get("SIMULATION_CONDITION_NAME") or "").strip() or None,
        "season_number": (
            int(effective.get("SIMULATION_SEASON_NUMBER") or 0)
            if int(effective.get("SIMULATION_SEASON_NUMBER") or 0) > 0
            else None
        ),
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
            empty_alerts = {"status": "ok", "counts": {"critical": 0, "warning": 0}, "items": []}
            return {
                "days": resolved_days,
                "generated_at": now_utc().isoformat(),
                "summary": {"latest_day_key": None, "latest": None, "seven_day_avg": {}},
                "alerts": empty_alerts,
                "alert_notification": _maybe_notify_kpi_alerts(
                    alerts_payload=empty_alerts,
                    summary={"latest_day_key": None, "latest": None, "seven_day_avg": {}},
                ),
                "items": [],
            }
        raise

    summary = payload.get("summary") or {}
    alerts = _build_kpi_alerts(summary)
    return {
        "days": resolved_days,
        "generated_at": now_utc().isoformat(),
        "summary": summary,
        "alerts": alerts,
        "alert_notification": _maybe_notify_kpi_alerts(alerts_payload=alerts, summary=summary),
        "items": payload.get("items") or [],
    }
