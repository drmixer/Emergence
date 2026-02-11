#!/usr/bin/env python3
"""Aggregate replicate summaries for a condition and export comparison artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.condition_reports import (
    generate_and_record_condition_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare run replicates for one condition.")
    parser.add_argument("--condition", required=True, help="Condition name to aggregate.")
    parser.add_argument("--season-number", type=int, default=0, help="Optional season number filter.")
    parser.add_argument(
        "--min-replicates",
        type=int,
        default=3,
        help="Minimum required replicates for claim threshold.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = generate_and_record_condition_comparison(
            db,
            condition_name=str(args.condition or "").strip(),
            min_replicates=max(1, int(args.min_replicates or 1)),
            season_number=(int(args.season_number) if int(args.season_number or 0) > 0 else None),
        )
        db.commit()
        payload = result.get("payload") or {}
        artifacts = result.get("artifacts") or {}
        print(
            json.dumps(
                {
                    "status": "generated",
                    "condition_name": payload.get("condition_name"),
                    "replicate_count": payload.get("replicate_count"),
                    "meets_replicate_threshold": payload.get("meets_replicate_threshold"),
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
