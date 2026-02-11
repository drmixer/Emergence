#!/usr/bin/env python3
"""Export season survivor snapshot payload for a completed run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.season_transfer import (
    SURVIVOR_SNAPSHOT_TYPE_V1,
    export_season_snapshot,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export survivors/state snapshot for a run and persist in season_snapshots.",
    )
    parser.add_argument("--run-id", required=True, help="Source run_id to snapshot.")
    parser.add_argument(
        "--snapshot-type",
        default=SURVIVOR_SNAPSHOT_TYPE_V1,
        help=f"Snapshot type label (default: {SURVIVOR_SNAPSHOT_TYPE_V1}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview payload without persisting to DB.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = export_season_snapshot(
            db,
            run_id=str(args.run_id),
            snapshot_type=str(args.snapshot_type),
            dry_run=bool(args.dry_run),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
