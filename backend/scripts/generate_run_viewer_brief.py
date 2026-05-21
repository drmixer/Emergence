#!/usr/bin/env python3
"""Generate Gemini-written viewer brief artifacts for a run_id."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.run_reports import generate_run_viewer_brief_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate run viewer brief (JSON + markdown artifacts).")
    parser.add_argument("--run-id", required=True, help="Run ID to synthesize.")
    parser.add_argument("--condition", default="", help="Optional condition label for tagging/replicate gating.")
    parser.add_argument("--season-number", type=int, default=0, help="Optional season number tag.")
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Write the constrained template brief without Gemini. Default uses Gemini and fails validation on mismatched output.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        payload = generate_run_viewer_brief_artifact(
            db,
            run_id=str(args.run_id or "").strip(),
            condition_name=str(args.condition or "").strip() or None,
            season_number=(int(args.season_number) if int(args.season_number or 0) > 0 else None),
            generate_with_gemini=not bool(args.no_gemini),
        )
        db.commit()
        run_dir = Path(__file__).resolve().parents[2] / "output" / "reports" / "runs"
        print(
            json.dumps(
                {
                    "run_id": payload.get("run_id"),
                    "status_label": payload.get("status_label"),
                    "evidence_completeness": payload.get("evidence_completeness"),
                    "condition_name": payload.get("condition_name"),
                    "viewer_brief_generation_status": (payload.get("gemini_viewer_brief_generation") or {}).get("status"),
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
