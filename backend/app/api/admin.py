"""Internal admin/ops API (private, token-protected)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.admin_auth import AdminActor, require_admin_auth
from app.core.config import settings
from app.core.database import get_db
from app.core.time import now_utc
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


def _assert_writes_enabled() -> None:
    if not bool(getattr(settings, "ADMIN_WRITE_ENABLED", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin write controls are disabled in this environment",
        )


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
