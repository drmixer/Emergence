#!/usr/bin/env python3
"""Generate deterministic next-run planner artifacts for a run_id."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.run_reports import generate_next_run_plan_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate run planner report (JSON + markdown artifacts).")
    parser.add_argument("--run-id", required=True, help="Run ID to synthesize.")
    parser.add_argument("--condition", default="", help="Optional condition label for recommendation context.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        payload = generate_next_run_plan_artifact(
            db,
            run_id=str(args.run_id or "").strip(),
            condition_name=str(args.condition or "").strip() or None,
        )
        db.commit()
        run_dir = Path(__file__).resolve().parents[2] / "output" / "reports" / "runs"
        print(
            json.dumps(
                {
                    "run_id": payload.get("run_id"),
                    "condition_name": payload.get("condition_name"),
                    "recommended_next_condition": payload.get("recommended_next_condition"),
                    "outdir": str(run_dir / str(payload.get("run_id") or "")),
                }
            )
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
