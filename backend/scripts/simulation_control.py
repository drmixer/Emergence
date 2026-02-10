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
from app.services.runtime_config import runtime_config_service


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
            },
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start/stop/status control for simulation runtime config.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Resume simulation processing.")
    start.add_argument("--run-mode", choices=("test", "real"), default=None)
    start.add_argument("--run-id", default=None)

    sub.add_parser("stop", help="Pause simulation processing.")
    sub.add_parser("status", help="Show effective simulation runtime state.")

    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(_status_payload(), indent=2))
        return

    if args.command == "stop":
        result = _update_runtime(
            {"SIMULATION_ACTIVE": False, "SIMULATION_PAUSED": True},
            "Operator stop via simulation_control.py",
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

        result = _update_runtime(
            updates,
            "Operator start via simulation_control.py",
        )
        print(json.dumps(result, indent=2))
        print(json.dumps(_status_payload(), indent=2))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
