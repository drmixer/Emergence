#!/usr/bin/env python3
"""Analyze one canonical agent slot across recent runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.agent_identity import immutable_alias_for_agent_number


def _row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row._mapping)


def _fetch_one(db, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    return _row_dict(db.execute(text(sql), params).first())


def _fetch_all(db, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [_row_dict(row) for row in db.execute(text(sql), params).fetchall()]


def _agent_row(db, agent_number: int) -> dict[str, Any]:
    return _fetch_one(
        db,
        """
        SELECT id, agent_number, display_name, model_type, tier, personality_type, status,
               starvation_cycles, died_at, death_cause
        FROM agents
        WHERE agent_number = :agent_number
        """,
        {"agent_number": agent_number},
    )


def _inventory(db, agent_id: int) -> dict[str, float]:
    rows = _fetch_all(
        db,
        """
        SELECT resource_type, quantity
        FROM agent_inventory
        WHERE agent_id = :agent_id
        ORDER BY resource_type ASC
        """,
        {"agent_id": agent_id},
    )
    return {str(row["resource_type"]): float(row["quantity"] or 0) for row in rows}


def _recent_runs(db, limit: int) -> list[dict[str, Any]]:
    return _fetch_all(
        db,
        """
        SELECT run_id, condition_name, run_class, started_at, ended_at, end_reason
        FROM simulation_runs
        WHERE started_at IS NOT NULL
        ORDER BY started_at DESC, id DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


def _run_agent_summary(db, *, run_id: str, agent_id: int) -> dict[str, Any]:
    return _fetch_one(
        db,
        """
        SELECT
          COUNT(*) AS event_count,
          COALESCE(SUM(CASE WHEN event_type = 'work' THEN 1 ELSE 0 END), 0) AS work_events,
          COALESCE(SUM(CASE WHEN event_type = 'request_aid' THEN 1 ELSE 0 END), 0) AS aid_requests,
          COALESCE(SUM(CASE WHEN event_type = 'refuse_aid' THEN 1 ELSE 0 END), 0) AS aid_refusals,
          COALESCE(SUM(CASE WHEN event_type = 'trade' THEN 1 ELSE 0 END), 0) AS trades,
          COALESCE(SUM(CASE WHEN event_type IN ('forum_post', 'forum_reply', 'direct_message') THEN 1 ELSE 0 END), 0) AS messages,
          MIN(CASE WHEN event_type = 'became_dormant' THEN created_at END) AS first_dormant_at,
          MIN(CASE WHEN event_type = 'agent_died' THEN created_at END) AS died_at,
          MIN(CASE WHEN event_type = 'starvation_warning' THEN created_at END) AS first_starvation_warning_at
        FROM events
        WHERE agent_id = :agent_id
          AND (event_metadata -> 'runtime' ->> 'run_id') = :run_id
        """,
        {"run_id": run_id, "agent_id": agent_id},
    )


def _run_llm_summary(db, *, run_id: str, agent_id: int) -> dict[str, Any]:
    return _fetch_one(
        db,
        """
        SELECT
          COUNT(*) AS calls,
          COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS successes,
          COALESCE(SUM(CASE WHEN NOT success THEN 1 ELSE 0 END), 0) AS failures,
          COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS provider_model_fallbacks,
          COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
          MIN(created_at) AS first_call_at,
          MAX(created_at) AS last_call_at
        FROM llm_usage
        WHERE run_id = :run_id
          AND agent_id = :agent_id
        """,
        {"run_id": run_id, "agent_id": agent_id},
    )


def _peer_comparison(db, *, run_id: str, model_type: str, agent_number: int) -> dict[str, Any]:
    return {
        "same_model_agents": _fetch_all(
            db,
            """
            SELECT a.agent_number, a.display_name, a.status, COUNT(lu.id) AS llm_calls
            FROM agents a
            LEFT JOIN llm_usage lu ON lu.agent_id = a.id AND lu.run_id = :run_id
            WHERE a.model_type = :model_type
            GROUP BY a.id, a.agent_number, a.display_name, a.status
            ORDER BY a.agent_number ASC
            """,
            {"run_id": run_id, "model_type": model_type},
        ),
        "neighbor_agents": _fetch_all(
            db,
            """
            SELECT a.agent_number, a.display_name, a.model_type, a.status, COUNT(lu.id) AS llm_calls
            FROM agents a
            LEFT JOIN llm_usage lu ON lu.agent_id = a.id AND lu.run_id = :run_id
            WHERE a.agent_number >= :prev_number
              AND a.agent_number <= :next_number
            GROUP BY a.id, a.agent_number, a.display_name, a.model_type, a.status
            ORDER BY a.agent_number ASC
            """,
            {
                "prev_number": max(1, agent_number - 1),
                "agent_number": agent_number,
                "next_number": agent_number + 1,
                "run_id": run_id,
            },
        ),
    }


def build_report(agent_number: int, limit_runs: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        agent = _agent_row(db, agent_number)
        if not agent:
            raise SystemExit(f"Agent #{agent_number} not found")
        agent_id = int(agent["id"])
        model_type = str(agent["model_type"] or "")
        runs = []
        for run in _recent_runs(db, limit_runs):
            run_id = str(run["run_id"])
            runs.append(
                {
                    **run,
                    "agent_events": _run_agent_summary(db, run_id=run_id, agent_id=agent_id),
                    "agent_llm": _run_llm_summary(db, run_id=run_id, agent_id=agent_id),
                    "peer_comparison": _peer_comparison(
                        db,
                        run_id=run_id,
                        model_type=model_type,
                        agent_number=agent_number,
                    ),
                }
            )
        return {
            "agent": {
                **agent,
                "alias": immutable_alias_for_agent_number(agent_number),
                "current_inventory": _inventory(db, agent_id),
            },
            "singleton_model_hypothesis": {
                "model_type": model_type,
                "same_model_current_count": len(
                    _fetch_all(db, "SELECT id FROM agents WHERE model_type = :model_type", {"model_type": model_type})
                ),
                "interpretation": "Singleton model/slot evidence is a hypothesis input, not a conclusion.",
            },
            "runs": runs,
        }
    finally:
        db.close()


def _markdown(report: dict[str, Any]) -> str:
    agent = report["agent"]
    rows = [
        f"# Agent Slot Analysis: {agent.get('alias')} (Agent #{agent.get('agent_number')})",
        "",
        f"- Current model: `{agent.get('model_type')}`",
        f"- Current status: `{agent.get('status')}`",
        f"- Current inventory: {agent.get('current_inventory')}",
        f"- Same-model current count: {report['singleton_model_hypothesis']['same_model_current_count']}",
        "- Interpretation: singleton model/slot evidence is a hypothesis input, not a conclusion.",
        "",
        "## Recent Runs",
    ]
    for run in report["runs"]:
        events = run.get("agent_events") or {}
        llm = run.get("agent_llm") or {}
        rows.extend(
            [
                "",
                f"### {run.get('run_id')}",
                f"- Condition: {run.get('condition_name') or 'n/a'}",
                f"- Window: {run.get('started_at')} -> {run.get('ended_at')}",
                f"- Agent events: {int(events.get('event_count') or 0)}; work={int(events.get('work_events') or 0)}, messages={int(events.get('messages') or 0)}, aid_requests={int(events.get('aid_requests') or 0)}",
                f"- Dormant at: {events.get('first_dormant_at') or 'n/a'}; died at: {events.get('died_at') or 'n/a'}",
                f"- LLM calls: {int(llm.get('calls') or 0)}; successes={int(llm.get('successes') or 0)}, failures={int(llm.get('failures') or 0)}, provider/model fallbacks={int(llm.get('provider_model_fallbacks') or 0)}",
            ]
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one canonical agent slot across recent runs.")
    parser.add_argument("--agent-number", type=int, default=6)
    parser.add_argument("--limit-runs", type=int, default=8)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    report = build_report(agent_number=args.agent_number, limit_runs=args.limit_runs)
    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
