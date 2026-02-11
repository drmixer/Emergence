#!/usr/bin/env python3
"""Seed next season from survivors with deterministic dry-run planning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.season_transfer import (
    DEFAULT_TARGET_AGENT_COUNT,
    SURVIVOR_SNAPSHOT_TYPE_V1,
    TRANSFER_POLICY_VERSION_V1,
    seed_next_season,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed next season from parent run survivors using transfer policy.",
    )
    parser.add_argument("--season-id", required=True, help="Destination season identifier.")
    parser.add_argument("--parent-run-id", required=True, help="Source run_id for survivor transfer.")
    parser.add_argument(
        "--transfer-policy-version",
        required=True,
        help=f"Transfer policy version, expected default: {TRANSFER_POLICY_VERSION_V1}",
    )
    parser.add_argument(
        "--target-agent-count",
        type=int,
        default=DEFAULT_TARGET_AGENT_COUNT,
        help=f"Target active agent count after seeding (default: {DEFAULT_TARGET_AGENT_COUNT}).",
    )
    parser.add_argument(
        "--snapshot-type",
        default=SURVIVOR_SNAPSHOT_TYPE_V1,
        help=f"Snapshot type to read for survivors (default: {SURVIVOR_SNAPSHOT_TYPE_V1}).",
    )
    parser.add_argument(
        "--carry-passed-laws",
        action="store_true",
        help="Keep existing active laws for next season.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print deterministic plan without modifying DB.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for destructive (non-dry-run) execution.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = seed_next_season(
            db,
            season_id=str(args.season_id),
            parent_run_id=str(args.parent_run_id),
            transfer_policy_version=str(args.transfer_policy_version),
            carry_passed_laws=bool(args.carry_passed_laws),
            dry_run=bool(args.dry_run),
            confirm=bool(args.confirm),
            target_agent_count=int(args.target_agent_count),
            snapshot_type=str(args.snapshot_type),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
