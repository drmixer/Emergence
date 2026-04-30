#!/usr/bin/env python3
"""
Simple runtime control for simulation start/stop/status.

Usage examples:
  python scripts/simulation_control.py status
  python scripts/simulation_control.py start --run-mode real --run-id real-20260210T050104Z
  python scripts/simulation_control.py stop
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from typing import Any
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import SimulationRun
from app.services.governance_run_boundary import retire_inherited_governance_state
from app.services.run_policy import coerce_run_class, deterministic_failure_policy_for_run_class
from app.services.run_start_safety import RunStartSafetyError, assert_new_run_startable
from app.services.runtime_config import runtime_config_service

_DEFAULT_PROTOCOL_VERSION = "protocol_v1"
_DEFAULT_RUN_CLASS = "standard_72h"


def _status_payload() -> dict[str, Any]:
    db = SessionLocal()
    try:
        effective = runtime_config_service.get_effective(db)
        global_counts_row = db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM agent_actions) AS global_action_count,
                  (SELECT COUNT(*) FROM llm_usage) AS global_llm_usage_count,
                  (SELECT MAX(created_at) FROM agent_actions) AS global_last_action_at,
                  (SELECT MAX(created_at) FROM llm_usage) AS global_last_llm_call_at
                """
            )
        ).first()
        current_run_id = str(effective.get("SIMULATION_RUN_ID") or "").strip()
        run_row = None
        current_run_counts_row = None
        if current_run_id:
            run_row = (
                db.query(SimulationRun)
                .filter(SimulationRun.run_id == current_run_id)
                .first()
            )
            if run_row is not None and run_row.started_at is not None:
                current_run_counts_row = db.execute(
                    text(
                        """
                        SELECT
                          (
                            SELECT COUNT(*)
                            FROM agent_actions
                            WHERE created_at >= :started_at
                              AND (:ended_at IS NULL OR created_at <= :ended_at)
                          ) AS action_count,
                          (
                            SELECT COUNT(*)
                            FROM llm_usage
                            WHERE run_id = :run_id
                          ) AS llm_usage_count,
                          (
                            SELECT MAX(created_at)
                            FROM agent_actions
                            WHERE created_at >= :started_at
                              AND (:ended_at IS NULL OR created_at <= :ended_at)
                          ) AS last_action_at,
                          (
                            SELECT MAX(created_at)
                            FROM llm_usage
                            WHERE run_id = :run_id
                          ) AS last_llm_call_at
                        """
                    ),
                    {
                        "run_id": current_run_id,
                        "started_at": run_row.started_at,
                        "ended_at": run_row.ended_at,
                    },
                ).first()
        return {
            "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
            "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
            "simulation_run_mode": str(effective.get("SIMULATION_RUN_MODE") or ""),
            "simulation_run_id": current_run_id,
            "simulation_run_class": coerce_run_class(effective.get("SIMULATION_RUN_CLASS")),
            "deterministic_failure_policy": deterministic_failure_policy_for_run_class(
                effective.get("SIMULATION_RUN_CLASS")
            ),
            "simulation_condition_name": str(effective.get("SIMULATION_CONDITION_NAME") or ""),
            "simulation_season_number": int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
            "llm_daily_budget_usd_soft": float(effective.get("LLM_DAILY_BUDGET_USD_SOFT", 0.0) or 0.0),
            "llm_daily_budget_usd_hard": float(effective.get("LLM_DAILY_BUDGET_USD_HARD", 0.0) or 0.0),
            "simulation_auto_stop_at": str(effective.get("SIMULATION_AUTO_STOP_AT") or "").strip() or None,
            "simulation_auto_stop_run_id": str(effective.get("SIMULATION_AUTO_STOP_RUN_ID") or "").strip() or None,
            "run_started_at": run_row.started_at.isoformat() if run_row and run_row.started_at else None,
            "run_ended_at": run_row.ended_at.isoformat() if run_row and run_row.ended_at else None,
            "action_count": int((current_run_counts_row.action_count if current_run_counts_row else 0) or 0),
            "llm_usage_count": int((current_run_counts_row.llm_usage_count if current_run_counts_row else 0) or 0),
            "last_action_at": (
                current_run_counts_row.last_action_at.isoformat()
                if current_run_counts_row and current_run_counts_row.last_action_at
                else None
            ),
            "last_llm_call_at": (
                current_run_counts_row.last_llm_call_at.isoformat()
                if current_run_counts_row and current_run_counts_row.last_llm_call_at
                else None
            ),
            "global_action_count": int((global_counts_row.global_action_count if global_counts_row else 0) or 0),
            "global_llm_usage_count": int(
                (global_counts_row.global_llm_usage_count if global_counts_row else 0) or 0
            ),
            "global_last_action_at": (
                global_counts_row.global_last_action_at.isoformat()
                if global_counts_row and global_counts_row.global_last_action_at
                else None
            ),
            "global_last_llm_call_at": (
                global_counts_row.global_last_llm_call_at.isoformat()
                if global_counts_row and global_counts_row.global_last_llm_call_at
                else None
            ),
        }
    finally:
        db.close()


def _update_runtime(updates: dict[str, Any], reason: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        result = runtime_config_service.update_settings(
            db,
            updates=updates,
            changed_by="ops:simulation_control_script",
            reason=reason,
        )
        effective = result.get("effective", {})
        return {
            "applied": result.get("applied", {}),
            "effective": {
                "SIMULATION_ACTIVE": bool(effective.get("SIMULATION_ACTIVE", True)),
                "SIMULATION_PAUSED": bool(effective.get("SIMULATION_PAUSED", False)),
                "SIMULATION_RUN_MODE": str(effective.get("SIMULATION_RUN_MODE") or ""),
                "SIMULATION_RUN_ID": str(effective.get("SIMULATION_RUN_ID") or ""),
                "SIMULATION_RUN_CLASS": coerce_run_class(effective.get("SIMULATION_RUN_CLASS")),
                "SIMULATION_CONDITION_NAME": str(effective.get("SIMULATION_CONDITION_NAME") or ""),
                "SIMULATION_SEASON_NUMBER": int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
                "LLM_DAILY_BUDGET_USD_SOFT": float(effective.get("LLM_DAILY_BUDGET_USD_SOFT", 0.0) or 0.0),
                "LLM_DAILY_BUDGET_USD_HARD": float(effective.get("LLM_DAILY_BUDGET_USD_HARD", 0.0) or 0.0),
                "SIMULATION_AUTO_STOP_AT": str(effective.get("SIMULATION_AUTO_STOP_AT") or "").strip() or None,
                "SIMULATION_AUTO_STOP_RUN_ID": str(effective.get("SIMULATION_AUTO_STOP_RUN_ID") or "").strip() or None,
            },
        }
    finally:
        db.close()


def _parse_stop_at(raw_value: str) -> str:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        raise ValueError("stop_at is required")
    normalized = clean_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("stop_at must include an explicit timezone offset")
    return parsed.astimezone(timezone.utc).isoformat()


def _clean_optional_text(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _normalize_run_id(raw_value: str | None, mode: str) -> str:
    clean = str(raw_value or "").strip()
    if clean:
        return clean
    return f"{mode}-{now_utc().strftime('%Y%m%dT%H%M%SZ')}"


def _resolve_start_runtime_updates(
    *,
    requested_run_mode: str | None,
    requested_run_id: str | None,
    requested_run_class: str | None,
    requested_condition: str | None,
    requested_season_number: int | None,
    current_run_mode: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    resolved_run_mode = str(requested_run_mode or current_run_mode or "test").strip() or "test"
    resolved_run_id = _normalize_run_id(requested_run_id, resolved_run_mode)
    resolved_run_class = coerce_run_class(requested_run_class or _DEFAULT_RUN_CLASS)
    resolved_condition = str(requested_condition or "").strip()
    resolved_season_number = int(requested_season_number or 0)

    updates: dict[str, Any] = {
        "SIMULATION_ACTIVE": True,
        "SIMULATION_PAUSED": False,
        "SIMULATION_RUN_MODE": resolved_run_mode,
        "SIMULATION_RUN_ID": resolved_run_id,
        "SIMULATION_RUN_CLASS": resolved_run_class,
        "SIMULATION_CONDITION_NAME": resolved_condition,
        "SIMULATION_SEASON_NUMBER": resolved_season_number,
    }
    return updates, resolved_run_id, resolved_run_mode


def _upsert_run_registry_start(
    *,
    run_id: str,
    run_mode: str | None,
    run_class: str | None,
    condition_name: str | None,
    season_number: int | None,
    tuning_run: bool | None,
    reason: str,
) -> dict[str, Any]:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        return {"updated": False, "reason": "missing_run_id"}

    db = SessionLocal()
    try:
        row = (
            db.query(SimulationRun)
            .filter(SimulationRun.run_id == clean_run_id)
            .first()
        )
        started_at = now_utc()
        clean_mode = str(run_mode or "").strip() or "test"
        resolved_run_class = coerce_run_class(run_class)
        clean_condition = _clean_optional_text(condition_name)
        clean_season_number = int(season_number or 0)
        season_value = clean_season_number if clean_season_number > 0 else None
        resolved_tuning = bool(tuning_run)
        created = row is None

        if row is None:
            row = SimulationRun(
                run_id=clean_run_id,
                run_mode=clean_mode,
                protocol_version=_DEFAULT_PROTOCOL_VERSION,
                condition_name=clean_condition,
                season_number=season_value,
                run_class=resolved_run_class,
                protocol_deviation=resolved_tuning,
                deviation_reason=("tuning_run" if resolved_tuning else None),
                started_at=started_at,
                start_reason=reason,
                end_reason=None,
                ended_at=None,
            )
            db.add(row)
        else:
            row.run_mode = clean_mode
            row.protocol_version = str(
                row.protocol_version or _DEFAULT_PROTOCOL_VERSION
            )
            row.condition_name = clean_condition
            row.season_number = season_value
            row.run_class = resolved_run_class
            row.protocol_deviation = resolved_tuning
            row.deviation_reason = ("tuning_run" if resolved_tuning else None)
            row.started_at = started_at
            row.start_reason = reason
            row.end_reason = None
            row.ended_at = None
            db.add(row)

        db.commit()
        return {
            "updated": True,
            "created": created,
            "run_id": clean_run_id,
        }
    except Exception as exc:
        db.rollback()
        return {
            "updated": False,
            "run_id": clean_run_id,
            "error": str(exc),
        }
    finally:
        db.close()


def _retire_inherited_governance_state_for_start(run_id: str) -> dict[str, int]:
    db = SessionLocal()
    try:
        result = retire_inherited_governance_state(db, run_id=run_id)
        db.commit()
        return {
            "proposals_expired": int(result.proposals_expired),
            "laws_deactivated": int(result.laws_deactivated),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_run_registry_stop(*, run_id: str, reason: str) -> dict[str, Any]:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        return {"updated": False, "reason": "missing_run_id"}

    db = SessionLocal()
    try:
        row = (
            db.query(SimulationRun)
            .filter(SimulationRun.run_id == clean_run_id)
            .first()
        )
        if row is None:
            return {
                "updated": False,
                "run_id": clean_run_id,
                "reason": "not_found",
            }
        row.ended_at = now_utc()
        row.end_reason = reason
        db.add(row)
        db.commit()
        return {"updated": True, "run_id": clean_run_id}
    except Exception as exc:
        db.rollback()
        return {
            "updated": False,
            "run_id": clean_run_id,
            "error": str(exc),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start/stop/status control for simulation runtime config.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Resume simulation processing.")
    start.add_argument("--run-mode", choices=("test", "real"), default=None)
    start.add_argument("--run-id", default=None)
    start.add_argument("--run-class", choices=("standard_72h", "deep_96h", "special_exploratory"), default=None)
    start.add_argument("--condition", default=None)
    start.add_argument("--season-number", type=int, default=None)
    start.add_argument("--tuning-run", action="store_true")

    sub.add_parser("stop", help="Pause simulation processing.")
    sub.add_parser("status", help="Show effective simulation runtime state.")
    budget = sub.add_parser("budget", help="Set daily LLM budget caps. Use 0 to disable a cap.")
    budget.add_argument("--soft", type=float, required=True)
    budget.add_argument("--hard", type=float, required=True)
    schedule_stop = sub.add_parser("schedule-stop", help="Schedule a Railway-side guarded stop for a specific run.")
    schedule_stop.add_argument("--stop-at", required=True, help="ISO-8601 timestamp with timezone, e.g. 2026-04-16T14:20:00-07:00")
    schedule_stop.add_argument("--run-id", default=None, help="Run id to stop. Defaults to the currently active run id.")
    sub.add_parser("clear-stop-schedule", help="Clear the Railway-side guarded stop override.")

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "stop":
        status_before = _status_payload()
        run_id_before = str(status_before.get("simulation_run_id") or "").strip()
        result = _update_runtime(
            {
                "SIMULATION_ACTIVE": False,
                "SIMULATION_PAUSED": True,
                "SIMULATION_AUTO_STOP_AT": "",
                "SIMULATION_AUTO_STOP_RUN_ID": "",
            },
            "Operator stop via simulation_control.py",
        )
        result["run_registry"] = _mark_run_registry_stop(
            run_id=run_id_before,
            reason="Operator stop via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "start":
        status_before = _status_payload()
        updates, resolved_run_id, resolved_run_mode = _resolve_start_runtime_updates(
            requested_run_mode=args.run_mode,
            requested_run_id=args.run_id,
            requested_run_class=args.run_class,
            requested_condition=args.condition,
            requested_season_number=args.season_number,
            current_run_mode=str(status_before.get("simulation_run_mode") or "").strip() or None,
        )
        db = SessionLocal()
        try:
            assert_new_run_startable(db, run_id=resolved_run_id)
        except RunStartSafetyError as exc:
            raise SystemExit(str(exc)) from exc
        finally:
            db.close()

        resolved_tuning_run = bool(args.tuning_run)
        if not resolved_tuning_run:
            resolved_tuning_run = False

        result = _update_runtime(
            updates,
            "Operator start via simulation_control.py",
        )
        effective = result.get("effective", {})
        result["run_registry"] = _upsert_run_registry_start(
            run_id=resolved_run_id,
            run_mode=resolved_run_mode,
            run_class=coerce_run_class(effective.get("SIMULATION_RUN_CLASS")),
            condition_name=(
                str(effective.get("SIMULATION_CONDITION_NAME") or "").strip() or None
            ),
            season_number=int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
            tuning_run=resolved_tuning_run,
            reason="Operator start via simulation_control.py",
        )
        result["governance_boundary"] = _retire_inherited_governance_state_for_start(
            resolved_run_id
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "budget":
        result = _update_runtime(
            {
                "LLM_DAILY_BUDGET_USD_SOFT": args.soft,
                "LLM_DAILY_BUDGET_USD_HARD": args.hard,
            },
            "Operator budget-cap update via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "schedule-stop":
        status_before = _status_payload()
        target_run_id = str(args.run_id or status_before.get("simulation_run_id") or "").strip()
        if not target_run_id:
            raise SystemExit("schedule-stop requires --run-id or an active simulation_run_id")
        stop_at_utc = _parse_stop_at(args.stop_at)
        result = _update_runtime(
            {
                "SIMULATION_AUTO_STOP_AT": stop_at_utc,
                "SIMULATION_AUTO_STOP_RUN_ID": target_run_id,
            },
            "Operator schedule-stop via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "clear-stop-schedule":
        result = _update_runtime(
            {
                "SIMULATION_AUTO_STOP_AT": "",
                "SIMULATION_AUTO_STOP_RUN_ID": "",
            },
            "Operator cleared scheduled stop via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
