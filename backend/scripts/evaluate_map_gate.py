#!/usr/bin/env python3
"""
Evaluate the Phase 1 map feature gate using measurable retention proxies.

The gate is intentionally conservative: the map should only ship once viewer
engagement/retention signals are strong enough to justify extra complexity.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import now_utc


@dataclass
class GateThresholds:
    min_distinct_bettors_7d: int
    min_total_bets_7d: int
    min_active_users_7d: int
    min_d7_retention: float
    min_d7_cohort_size: int


def _collect_metrics(now_ts) -> dict[str, Any]:
    since_7 = now_ts - timedelta(days=7)
    since_14 = now_ts - timedelta(days=14)

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT
                    COALESCE(COUNT(*) FILTER (WHERE created_at >= :since_7), 0) AS total_bets_7d,
                    COALESCE(COUNT(*) FILTER (WHERE created_at >= :since_14), 0) AS total_bets_14d,
                    COALESCE(COUNT(DISTINCT CASE WHEN created_at >= :since_7 THEN user_id END), 0) AS distinct_bettors_7d,
                    COALESCE(COUNT(DISTINCT CASE WHEN created_at >= :since_14 THEN user_id END), 0) AS distinct_bettors_14d
                FROM prediction_bets
                """
            ),
            {"since_7": since_7, "since_14": since_14},
        ).first()

        active_users = db.execute(
            text(
                """
                SELECT
                    COALESCE(COUNT(*) FILTER (WHERE last_active_at >= :since_7), 0) AS active_users_7d,
                    COALESCE(COUNT(*) FILTER (WHERE last_active_at >= :since_14), 0) AS active_users_14d
                FROM user_points
                """
            ),
            {"since_7": since_7, "since_14": since_14},
        ).first()

        retention = db.execute(
            text(
                """
                WITH cohort AS (
                    SELECT DISTINCT user_id
                    FROM prediction_bets
                    WHERE created_at >= :since_14
                      AND created_at < :since_7
                ),
                returning_users AS (
                    SELECT DISTINCT b.user_id
                    FROM prediction_bets b
                    JOIN cohort c ON c.user_id = b.user_id
                    WHERE b.created_at >= :since_7
                )
                SELECT
                    COALESCE((SELECT COUNT(*) FROM cohort), 0) AS cohort_size,
                    COALESCE((SELECT COUNT(*) FROM returning_users), 0) AS returning_size
                """
            ),
            {"since_7": since_7, "since_14": since_14},
        ).first()

        return {
            "window_start_7d_utc": since_7.isoformat(),
            "window_start_14d_utc": since_14.isoformat(),
            "total_bets_7d": int((row.total_bets_7d if row else 0) or 0),
            "total_bets_14d": int((row.total_bets_14d if row else 0) or 0),
            "distinct_bettors_7d": int((row.distinct_bettors_7d if row else 0) or 0),
            "distinct_bettors_14d": int((row.distinct_bettors_14d if row else 0) or 0),
            "active_users_7d": int((active_users.active_users_7d if active_users else 0) or 0),
            "active_users_14d": int((active_users.active_users_14d if active_users else 0) or 0),
            "d7_cohort_size": int((retention.cohort_size if retention else 0) or 0),
            "d7_returning_users": int((retention.returning_size if retention else 0) or 0),
        }
    finally:
        db.close()


def _evaluate(metrics: dict[str, Any], thresholds: GateThresholds) -> dict[str, Any]:
    d7_cohort = int(metrics["d7_cohort_size"])
    d7_returning = int(metrics["d7_returning_users"])
    d7_retention = (d7_returning / d7_cohort) if d7_cohort > 0 else None

    checks = [
        {
            "key": "distinct_bettors_7d",
            "current": int(metrics["distinct_bettors_7d"]),
            "threshold": thresholds.min_distinct_bettors_7d,
            "met": int(metrics["distinct_bettors_7d"]) >= thresholds.min_distinct_bettors_7d,
        },
        {
            "key": "total_bets_7d",
            "current": int(metrics["total_bets_7d"]),
            "threshold": thresholds.min_total_bets_7d,
            "met": int(metrics["total_bets_7d"]) >= thresholds.min_total_bets_7d,
        },
        {
            "key": "active_users_7d",
            "current": int(metrics["active_users_7d"]),
            "threshold": thresholds.min_active_users_7d,
            "met": int(metrics["active_users_7d"]) >= thresholds.min_active_users_7d,
        },
        {
            "key": "d7_cohort_size",
            "current": d7_cohort,
            "threshold": thresholds.min_d7_cohort_size,
            "met": d7_cohort >= thresholds.min_d7_cohort_size,
        },
        {
            "key": "d7_retention",
            "current": d7_retention,
            "threshold": thresholds.min_d7_retention,
            "met": bool(d7_retention is not None and d7_retention >= thresholds.min_d7_retention),
        },
    ]

    all_met = all(bool(check["met"]) for check in checks)
    if all_met:
        decision = "go"
        reason = "all_gate_checks_met"
    elif d7_cohort < thresholds.min_d7_cohort_size:
        decision = "no-go"
        reason = "insufficient_retention_sample"
    else:
        decision = "no-go"
        reason = "retention_or_engagement_below_threshold"

    return {
        "phase1_map_decision": decision,
        "reason": reason,
        "phase1_map_enabled": bool(decision == "go"),
        "d7_retention": d7_retention,
        "checks": checks,
        "trigger_conditions_to_flip_to_go": [
            f"distinct_bettors_7d >= {thresholds.min_distinct_bettors_7d}",
            f"total_bets_7d >= {thresholds.min_total_bets_7d}",
            f"active_users_7d >= {thresholds.min_active_users_7d}",
            f"d7_cohort_size >= {thresholds.min_d7_cohort_size}",
            f"d7_retention >= {thresholds.min_d7_retention:.2f}",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate whether the map feature should advance to Phase 1."
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="",
        help="Output directory (default: <repo>/output/launch_readiness)",
    )
    parser.add_argument("--min-distinct-bettors-7d", type=int, default=10)
    parser.add_argument("--min-total-bets-7d", type=int, default=30)
    parser.add_argument("--min-active-users-7d", type=int, default=10)
    parser.add_argument("--min-d7-retention", type=float, default=0.20)
    parser.add_argument("--min-d7-cohort-size", type=int, default=10)
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    outdir = (
        Path(args.outdir).expanduser().resolve()
        if args.outdir
        else (repo_root / "output" / "launch_readiness")
    )
    outdir.mkdir(parents=True, exist_ok=True)

    thresholds = GateThresholds(
        min_distinct_bettors_7d=max(1, int(args.min_distinct_bettors_7d)),
        min_total_bets_7d=max(1, int(args.min_total_bets_7d)),
        min_active_users_7d=max(1, int(args.min_active_users_7d)),
        min_d7_retention=max(0.0, min(1.0, float(args.min_d7_retention))),
        min_d7_cohort_size=max(1, int(args.min_d7_cohort_size)),
    )

    generated_at = now_utc()
    metrics = _collect_metrics(generated_at)
    decision = _evaluate(metrics, thresholds=thresholds)

    report = {
        "generated_at_utc": generated_at.isoformat(),
        "thresholds": {
            "min_distinct_bettors_7d": thresholds.min_distinct_bettors_7d,
            "min_total_bets_7d": thresholds.min_total_bets_7d,
            "min_active_users_7d": thresholds.min_active_users_7d,
            "min_d7_retention": thresholds.min_d7_retention,
            "min_d7_cohort_size": thresholds.min_d7_cohort_size,
        },
        "metrics": metrics,
        "decision": decision,
    }

    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    out_path = outdir / f"map_gate_{stamp}.json"
    latest_path = outdir / "map_gate_latest.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "generated_at_utc": report["generated_at_utc"],
                "decision": report["decision"]["phase1_map_decision"],
                "reason": report["decision"]["reason"],
                "artifact": str(out_path),
                "latest": str(latest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
