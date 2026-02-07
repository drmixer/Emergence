#!/usr/bin/env python3
"""
Review highlight-feed quality and write a report under output/launch_readiness.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.analytics import get_latest_summary, plot_turns, plot_turns_replay
from app.services.featured_events import get_dramatic_events, get_featured_events


def _coverage(items: list[dict], key: str) -> float:
    if not items:
        return 0.0
    present = sum(1 for item in items if str(item.get(key) or "").strip())
    return present / len(items)


def _avg_len(items: list[dict], key: str) -> float:
    lengths = [
        len(str(item.get(key) or "").strip())
        for item in items
        if str(item.get(key) or "").strip()
    ]
    if not lengths:
        return 0.0
    return sum(lengths) / len(lengths)


def main() -> int:
    now = datetime.now(timezone.utc)
    featured = get_featured_events(limit=20)
    dramatic = get_dramatic_events(hours=72, limit=20)
    plot = plot_turns(limit=16, hours=72, min_salience=55)
    replay = plot_turns_replay(hours=24, min_salience=55, bucket_minutes=30, limit=220)
    summary = get_latest_summary()

    feature_titles = [str(item.get("title") or "").strip() for item in featured]
    feature_count = len(feature_titles)
    unique_titles = len(set(feature_titles))

    plot_items = list(plot.get("items") or [])
    plot_salience = [int(item.get("salience") or 0) for item in plot_items]

    checks = {
        "featured_non_empty": feature_count > 0,
        "featured_title_coverage": _coverage(featured, "title") >= 0.95,
        "featured_description_coverage": _coverage(featured, "description") >= 0.95,
        "featured_unique_title_ratio": (
            (unique_titles / feature_count) if feature_count else 0.0
        )
        >= 0.7,
        "plot_turns_present": len(plot_items) > 0,
        "plot_salience_min_respected": (
            min(plot_salience) >= int(plot.get("min_salience") or 0)
            if plot_salience
            else False
        ),
        "daily_summary_available": bool((summary or {}).get("summary")),
    }

    report = {
        "generated_at_utc": now.isoformat(),
        "featured": {
            "count": feature_count,
            "title_coverage": round(_coverage(featured, "title"), 4),
            "description_coverage": round(_coverage(featured, "description"), 4),
            "avg_title_len": round(_avg_len(featured, "title"), 2),
            "avg_description_len": round(_avg_len(featured, "description"), 2),
            "unique_title_ratio": (
                round((unique_titles / feature_count), 4) if feature_count else 0.0
            ),
        },
        "dramatic": {
            "count": len(dramatic),
            "title_coverage": round(_coverage(dramatic, "title"), 4),
            "description_coverage": round(_coverage(dramatic, "description"), 4),
        },
        "plot_turns": {
            "count": len(plot_items),
            "min_salience_config": int(plot.get("min_salience") or 0),
            "min_salience_observed": min(plot_salience) if plot_salience else None,
            "max_salience_observed": max(plot_salience) if plot_salience else None,
        },
        "replay": {
            "count": int(replay.get("count") or 0),
            "bucket_count": int(replay.get("bucket_count") or 0),
        },
        "daily_summary": {
            "available": bool((summary or {}).get("summary")),
            "day_number": (summary or {}).get("day_number"),
        },
        "checks": checks,
        "overall_pass": all(checks.values()),
    }

    outdir = Path(__file__).resolve().parents[2] / "output" / "launch_readiness"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    report_path = outdir / f"highlight_quality_review_{stamp}.json"
    latest_path = outdir / "highlight_quality_review_latest.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "overall_pass": bool(report["overall_pass"]),
                "report": str(report_path),
                "latest": str(latest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
