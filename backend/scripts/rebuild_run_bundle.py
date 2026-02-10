#!/usr/bin/env python3
"""Rebuild full run report bundle (technical + story + planner + article upserts)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.run_reports import generate_run_bundle_for_run_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild full report bundle for a run id.")
    parser.add_argument("--run-id", required=True, help="Run ID to synthesize.")
    parser.add_argument("--condition", default="", help="Optional condition label for tags/replicate gating.")
    parser.add_argument("--season-number", type=int, default=0, help="Optional season number tag.")
    parser.add_argument("--actor-id", default="run-bundle-cli", help="Audit actor id for upserted content.")
    args = parser.parse_args()

    payload = generate_run_bundle_for_run_id(
        run_id=str(args.run_id or "").strip(),
        actor_id=str(args.actor_id or "").strip() or "run-bundle-cli",
        condition_name=str(args.condition or "").strip() or None,
        season_number=(int(args.season_number) if int(args.season_number or 0) > 0 else None),
    )
    payload["status"] = "generated"
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
