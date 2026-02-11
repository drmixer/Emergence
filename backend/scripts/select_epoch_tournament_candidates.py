#!/usr/bin/env python3
"""Score and select epoch tournament champions with deterministic tie-breakers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.epoch_tournament import (
    DEFAULT_CHAMPIONS_PER_SEASON,
    DEFAULT_TARGET_CHAMPIONS,
    SCORING_POLICY_VERSION_V1,
    select_epoch_tournament_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select epoch tournament candidates and champions.")
    parser.add_argument("--epoch-id", required=True, help="Epoch identifier to score.")
    parser.add_argument(
        "--season-id",
        action="append",
        default=[],
        help="Optional season_id filter. Repeat for multiple seasons.",
    )
    parser.add_argument(
        "--champions-per-season",
        type=int,
        default=DEFAULT_CHAMPIONS_PER_SEASON,
        help=f"Champions selected per season (default: {DEFAULT_CHAMPIONS_PER_SEASON}).",
    )
    parser.add_argument(
        "--target-total-champions",
        type=int,
        default=DEFAULT_TARGET_CHAMPIONS,
        help=(
            "Optional cap on total selected champions. "
            f"Use 0 to disable cap (default: {DEFAULT_TARGET_CHAMPIONS})."
        ),
    )
    parser.add_argument(
        "--scoring-policy-version",
        default=SCORING_POLICY_VERSION_V1,
        help=f"Scoring policy version label (default: {SCORING_POLICY_VERSION_V1}).",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write JSON/markdown artifacts under output/reports/epochs.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = select_epoch_tournament_candidates(
            db,
            epoch_id=str(args.epoch_id or "").strip(),
            season_ids=[str(value or "").strip() for value in args.season_id or []],
            champions_per_season=max(1, int(args.champions_per_season or 1)),
            target_total_champions=(
                int(args.target_total_champions)
                if int(args.target_total_champions or 0) > 0
                else None
            ),
            scoring_policy_version=str(args.scoring_policy_version or "").strip() or SCORING_POLICY_VERSION_V1,
            write_artifacts=not bool(args.no_write),
        )
        payload = result.get("payload") or {}
        print(
            json.dumps(
                {
                    "status": result.get("status"),
                    "epoch_id": payload.get("epoch_id"),
                    "season_ids": payload.get("season_ids"),
                    "candidate_count": payload.get("candidate_count"),
                    "eligible_count": payload.get("eligible_count"),
                    "selected_count": payload.get("selected_count"),
                    "selected": [
                        {
                            "season_id": item.get("season_id"),
                            "agent_number": item.get("agent_number"),
                            "champion_score": item.get("champion_score"),
                            "selection_status": item.get("selection_status"),
                        }
                        for item in (payload.get("selected") or [])
                    ],
                    "artifacts": result.get("artifacts") or {},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
