#!/usr/bin/env python3
"""Generate the weekly State of Emergence digest draft and markdown artifact."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.services.archive_drafts import generate_weekly_draft


def _parse_anchor_date(raw_value: str | None) -> date | None:
    clean = str(raw_value or "").strip()
    if not clean:
        return None
    try:
        return date.fromisoformat(clean)
    except ValueError as exc:
        raise SystemExit(f"Invalid --anchor-date '{clean}'. Expected YYYY-MM-DD.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a weekly digest draft with locked template and evidence links."
    )
    parser.add_argument("--lookback-days", type=int, default=7, help="Lookback window in days (1-30)")
    parser.add_argument("--anchor-date", type=str, default="", help="Digest anchor date in YYYY-MM-DD (UTC)")
    parser.add_argument("--actor-id", type=str, default="weekly-digest-cli", help="Actor id for created_by/updated_by")
    parser.add_argument(
        "--allow-duplicate-anchor",
        action="store_true",
        help="Allow creating another draft for the same anchor date instead of reusing existing draft",
    )
    parser.add_argument(
        "--print-markdown",
        action="store_true",
        help="Print generated markdown after JSON metadata",
    )
    args = parser.parse_args()

    now_value = now_utc()
    anchor_date = _parse_anchor_date(args.anchor_date) or now_value.date()
    skip_if_exists = not bool(args.allow_duplicate_anchor)

    db = SessionLocal()
    try:
        result = generate_weekly_draft(
            db,
            actor_id=str(args.actor_id or "weekly-digest-cli").strip() or "weekly-digest-cli",
            lookback_days=int(args.lookback_days),
            anchor_date=anchor_date,
            now_ts=now_value,
            skip_if_exists_for_anchor=skip_if_exists,
        )
        if result.created and result.article is not None:
            db.commit()
            db.refresh(result.article)
        else:
            db.rollback()

        payload = {
            "slug": (str(result.article.slug) if result.article is not None else None),
            "created": bool(result.created),
            "status": str(result.status or "ok"),
            "message": result.message,
            "evidence_gate": result.evidence_gate,
            "title": (str(result.article.title) if result.article is not None else None),
            "evidence_run_id": (
                str(result.article.evidence_run_id or "").strip() or None
                if result.article is not None
                else None
            ),
            "digest_markdown_path": result.digest_markdown_path,
            "digest_template_version": result.digest_template_version,
        }
        print(json.dumps(payload))

        if args.print_markdown and result.digest_markdown:
            print("\n" + result.digest_markdown)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
