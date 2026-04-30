#!/usr/bin/env python3
"""Summarize one canonical agent slot across recent runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a canonical agent slot across recent runs.")
    parser.add_argument("--agent-number", type=int, default=6, help="Canonical Agent #NN to inspect.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum recent run ids to include.")
    args = parser.parse_args()

    agent_number = int(args.agent_number)
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                WITH target_agent AS (
                  SELECT id, agent_number, display_name, model_type, tier, personality_type, status,
                         starvation_cycles, died_at, death_cause
                  FROM agents
                  WHERE agent_number = :agent_number
                ),
                recent_runs AS (
                  SELECT run_id, started_at, ended_at, condition_name, run_class
                  FROM simulation_runs
                  ORDER BY started_at DESC
                  LIMIT :limit
                )
                SELECT
                  r.run_id,
                  r.started_at,
                  r.ended_at,
                  r.condition_name,
                  r.run_class,
                  a.display_name,
                  a.model_type,
                  a.tier,
                  a.personality_type,
                  COUNT(e.id) AS events,
                  COALESCE(SUM(CASE WHEN e.event_type = 'work' THEN 1 ELSE 0 END), 0) AS work_actions,
                  COALESCE(SUM(CASE WHEN e.event_type = 'request_aid' THEN 1 ELSE 0 END), 0) AS aid_requests,
                  COALESCE(SUM(CASE WHEN e.event_type = 'trade' THEN 1 ELSE 0 END), 0) AS trades,
                  COALESCE(SUM(CASE WHEN e.event_type = 'became_dormant' THEN 1 ELSE 0 END), 0) AS dormancy_events,
                  COALESCE(SUM(CASE WHEN e.event_type = 'starvation_warning' THEN 1 ELSE 0 END), 0) AS starvation_warnings,
                  COALESCE(SUM(CASE WHEN e.event_type = 'agent_died' THEN 1 ELSE 0 END), 0) AS deaths,
                  MIN(CASE WHEN e.event_type = 'became_dormant' THEN e.created_at ELSE NULL END) AS first_dormant_at,
                  MIN(CASE WHEN e.event_type = 'agent_died' THEN e.created_at ELSE NULL END) AS died_at
                FROM recent_runs r
                CROSS JOIN target_agent a
                LEFT JOIN events e
                  ON e.agent_id = a.id
                 AND e.created_at >= r.started_at
                 AND (r.ended_at IS NULL OR e.created_at <= r.ended_at)
                 AND (
                   (e.event_metadata -> 'runtime' ->> 'run_id') = r.run_id
                   OR e.event_metadata IS NULL
                 )
                GROUP BY r.run_id, r.started_at, r.ended_at, r.condition_name, r.run_class,
                         a.display_name, a.model_type, a.tier, a.personality_type
                ORDER BY r.started_at DESC
                """
            ),
            {"agent_number": agent_number, "limit": max(1, int(args.limit))},
        ).fetchall()
        payload = {
            "agent_number": agent_number,
            "singleton_warning": (
                "If this slot is the only live-roster member of its model, interpret recurring deaths "
                "as a singleton model/slot hypothesis, not a model conclusion."
            ),
            "runs": [
                {
                    "run_id": str(row.run_id),
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "ended_at": row.ended_at.isoformat() if row.ended_at else None,
                    "condition_name": row.condition_name,
                    "run_class": row.run_class,
                    "display_name": row.display_name,
                    "model_type": row.model_type,
                    "tier": int(row.tier or 0),
                    "personality_type": row.personality_type,
                    "events": int(row.events or 0),
                    "work_actions": int(row.work_actions or 0),
                    "aid_requests": int(row.aid_requests or 0),
                    "trades": int(row.trades or 0),
                    "dormancy_events": int(row.dormancy_events or 0),
                    "starvation_warnings": int(row.starvation_warnings or 0),
                    "deaths": int(row.deaths or 0),
                    "first_dormant_at": row.first_dormant_at.isoformat() if row.first_dormant_at else None,
                    "died_at": row.died_at.isoformat() if row.died_at else None,
                }
                for row in rows
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
