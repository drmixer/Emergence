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
import json
import sys
from typing import Any
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import SimulationRun
from app.services.runtime_config import runtime_config_service

_DEFAULT_PROTOCOL_VERSION = "protocol_v1"
_DEFAULT_RUN_CLASS = "standard_72h"


def _status_payload() -> dict[str, Any]:
    db = SessionLocal()
    try:
        effective = runtime_config_service.get_effective(db)
        counts_row = db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM agent_actions) AS action_count,
                  (SELECT COUNT(*) FROM llm_usage) AS llm_usage_count,
                  (SELECT MAX(created_at) FROM agent_actions) AS last_action_at,
                  (SELECT MAX(created_at) FROM llm_usage) AS last_llm_call_at
                """
            )
        ).first()
        return {
            "simulation_active": bool(effective.get("SIMULATION_ACTIVE", True)),
            "simulation_paused": bool(effective.get("SIMULATION_PAUSED", False)),
            "simulation_run_mode": str(effective.get("SIMULATION_RUN_MODE") or ""),
            "simulation_run_id": str(effective.get("SIMULATION_RUN_ID") or ""),
            "simulation_condition_name": str(effective.get("SIMULATION_CONDITION_NAME") or ""),
            "simulation_season_number": int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
            "action_count": int((counts_row.action_count if counts_row else 0) or 0),
            "llm_usage_count": int((counts_row.llm_usage_count if counts_row else 0) or 0),
            "last_action_at": counts_row.last_action_at.isoformat() if counts_row and counts_row.last_action_at else None,
            "last_llm_call_at": counts_row.last_llm_call_at.isoformat() if counts_row and counts_row.last_llm_call_at else None,
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
                "SIMULATION_CONDITION_NAME": str(effective.get("SIMULATION_CONDITION_NAME") or ""),
                "SIMULATION_SEASON_NUMBER": int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
            },
        }
    finally:
        db.close()


def _clean_optional_text(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _upsert_run_registry_start(
    *,
    run_id: str,
    run_mode: str | None,
    condition_name: str | None,
    season_number: int | None,
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
        clean_condition = _clean_optional_text(condition_name)
        clean_season_number = int(season_number or 0)
        season_value = clean_season_number if clean_season_number > 0 else None
        created = row is None

        if row is None:
            row = SimulationRun(
                run_id=clean_run_id,
                run_mode=clean_mode,
                protocol_version=_DEFAULT_PROTOCOL_VERSION,
                condition_name=clean_condition,
                season_number=season_value,
                run_class=_DEFAULT_RUN_CLASS,
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
            row.run_class = str(row.run_class or _DEFAULT_RUN_CLASS)
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
    start.add_argument("--condition", default=None)
    start.add_argument("--season-number", type=int, default=None)

    sub.add_parser("stop", help="Pause simulation processing.")
    sub.add_parser("status", help="Show effective simulation runtime state.")

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "stop":
        status_before = _status_payload()
        run_id_before = str(status_before.get("simulation_run_id") or "").strip()
        result = _update_runtime(
            {"SIMULATION_ACTIVE": False, "SIMULATION_PAUSED": True},
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
        updates: dict[str, Any] = {
            "SIMULATION_ACTIVE": True,
            "SIMULATION_PAUSED": False,
        }
        if args.run_mode:
            updates["SIMULATION_RUN_MODE"] = args.run_mode
        if args.run_id is not None:
            updates["SIMULATION_RUN_ID"] = str(args.run_id)
        if args.condition is not None:
            updates["SIMULATION_CONDITION_NAME"] = str(args.condition or "").strip()
        if args.season_number is not None:
            updates["SIMULATION_SEASON_NUMBER"] = int(args.season_number or 0)

        result = _update_runtime(
            updates,
            "Operator start via simulation_control.py",
        )
        effective = result.get("effective", {})
        result["run_registry"] = _upsert_run_registry_start(
            run_id=str(effective.get("SIMULATION_RUN_ID") or "").strip(),
            run_mode=str(effective.get("SIMULATION_RUN_MODE") or "").strip() or None,
            condition_name=(
                str(effective.get("SIMULATION_CONDITION_NAME") or "").strip() or None
            ),
            season_number=int(effective.get("SIMULATION_SEASON_NUMBER") or 0),
            reason="Operator start via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
