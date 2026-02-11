#!/usr/bin/env python3
"""Export a deterministic run summary report (JSON + markdown)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.condition_reports import (
    generate_and_record_run_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export run summary report artifact.")
    parser.add_argument("--run-id", required=True, help="Run ID to summarize.")
    parser.add_argument("--condition", default="", help="Optional condition label override.")
    parser.add_argument("--season-number", type=int, default=0, help="Optional season number override.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = generate_and_record_run_summary(
            db,
            run_id=str(args.run_id or "").strip(),
            condition_name=(str(args.condition or "").strip() or None),
            season_number=(int(args.season_number) if int(args.season_number or 0) > 0 else None),
        )
        db.commit()
        payload = result.get("payload") or {}
        artifacts = result.get("artifacts") or {}
        print(
            json.dumps(
                {
                    "status": "generated",
                    "run_id": payload.get("run_id"),
                    "condition_name": payload.get("condition_name"),
                    "replicate_index": payload.get("replicate_index"),
                    "replicate_count": payload.get("replicate_count"),
                    "artifacts": artifacts,
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
