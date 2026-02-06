#!/usr/bin/env python3
"""
Compute rolling simulation metrics and export trend reports (CSV + JSON).

Usage:
  cd backend
  ./venv/bin/python scripts/eval_metrics.py --windows 12 --window-minutes 5
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import ensure_utc, now_utc
from app.models.models import AgentInventory, Event
from app.services.emergence_metrics import compute_emergence_metrics


ACTION_TYPES = {
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "work",
    "trade",
    "set_name",
    "idle",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
    "vote_enforcement",
}

GOVERNANCE_TYPES = {
    "create_proposal",
    "vote",
    "law_passed",
}

ENFORCEMENT_TYPES = {
    "vote_enforcement",
    "enforcement_initiated",
    "agent_sanctioned",
    "resources_seized",
    "agent_exiled",
}


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _safe_entropy(counts: Iterable[int], total: int) -> float:
    if total <= 0:
        return 0.0
    entropy = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        entropy -= p * math.log2(p)
    return entropy


def _window_metrics(events: list[Event], window: Window) -> dict:
    action_events = [e for e in events if e.event_type in ACTION_TYPES]
    governance_count = sum(1 for e in events if e.event_type in GOVERNANCE_TYPES)
    enforcement_count = sum(1 for e in events if e.event_type in ENFORCEMENT_TYPES)
    invalid_count = sum(1 for e in events if e.event_type == "invalid_action")

    total_actions = len(action_events)
    by_type = Counter(e.event_type for e in action_events)
    by_agent = Counter(e.agent_id for e in action_events if e.agent_id is not None)

    top_action = None
    top_action_share = 0.0
    if by_type and total_actions > 0:
        top_action, top_action_count = by_type.most_common(1)[0]
        top_action_share = top_action_count / total_actions

    top_agent_share = 0.0
    hhi_agents = 0.0
    if by_agent and total_actions > 0:
        top_agent_share = by_agent.most_common(1)[0][1] / total_actions
        hhi_agents = sum((c / total_actions) ** 2 for c in by_agent.values())

    return {
        "window_start_utc": _iso(window.start),
        "window_end_utc": _iso(window.end),
        "total_events": len(events),
        "total_actions": total_actions,
        "unique_action_types": len(by_type),
        "action_entropy_bits": round(_safe_entropy(by_type.values(), total_actions), 4),
        "top_action": top_action or "",
        "top_action_share": round(top_action_share, 4),
        "top_agent_share": round(top_agent_share, 4),
        "agent_hhi": round(hhi_agents, 6),
        "governance_events": governance_count,
        "enforcement_events": enforcement_count,
        "invalid_actions": invalid_count,
    }


def _resource_concentration() -> dict:
    db = SessionLocal()
    try:
        inventories = db.query(AgentInventory).all()
        by_agent = Counter()
        totals = Counter()
        for inv in inventories:
            if inv.resource_type not in {"food", "energy", "materials"}:
                continue
            qty = float(inv.quantity)
            by_agent[inv.agent_id] += qty
            totals[inv.resource_type] += qty

        combined = sum(by_agent.values())
        ranked = [qty for _, qty in by_agent.most_common()]
        if combined <= 0 or not ranked:
            return {
                "resource_totals": dict(totals),
                "top1_share": 0.0,
                "top10_share": 0.0,
            }
        top1 = ranked[0] / combined
        top10 = sum(ranked[:10]) / combined
        return {
            "resource_totals": {k: round(v, 4) for k, v in totals.items()},
            "top1_share": round(top1, 4),
            "top10_share": round(top10, 4),
        }
    finally:
        db.close()


def _fetch_events(lookback_start: datetime, end: datetime) -> list[Event]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Event)
            .filter(Event.created_at >= lookback_start, Event.created_at <= end)
            .order_by(Event.created_at.asc())
            .all()
        )
        return rows
    finally:
        db.close()


def _build_windows(now: datetime, windows: int, window_minutes: int) -> list[Window]:
    result: list[Window] = []
    duration = timedelta(minutes=window_minutes)
    start = now - (duration * windows)
    for i in range(windows):
        w_start = start + (duration * i)
        w_end = w_start + duration
        result.append(Window(start=w_start, end=w_end))
    return result


def _events_for_window(events: list[Event], window: Window) -> list[Event]:
    window_events = []
    for e in events:
        created = ensure_utc(e.created_at)
        if created is None:
            continue
        if window.start < created <= window.end:
            window_events.append(e)
    return window_events


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "window_start_utc",
        "window_end_utc",
        "total_events",
        "total_actions",
        "unique_action_types",
        "action_entropy_bits",
        "top_action",
        "top_action_share",
        "top_agent_share",
        "agent_hhi",
        "governance_events",
        "enforcement_events",
        "invalid_actions",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export rolling emergence metrics.")
    parser.add_argument("--windows", type=int, default=12, help="Number of windows (default: 12)")
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=5,
        help="Minutes per window (default: 5)",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="",
        help="Output directory (default: <repo>/output/metrics)",
    )
    args = parser.parse_args()

    if args.windows < 1 or args.window_minutes < 1:
        raise SystemExit("--windows and --window-minutes must be >= 1")

    repo_root = Path(__file__).resolve().parents[2]
    default_outdir = repo_root / "output" / "metrics"
    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else default_outdir
    outdir.mkdir(parents=True, exist_ok=True)

    generated_at = now_utc()
    windows = _build_windows(generated_at, args.windows, args.window_minutes)
    lookback_start = windows[0].start

    events = _fetch_events(lookback_start=lookback_start, end=generated_at)
    window_rows = []
    for w in windows:
        row = _window_metrics(_events_for_window(events, w), w)
        window_rows.append(row)

    latest = window_rows[-1] if window_rows else {}
    emergence_metrics_latest_window: dict = {}
    if windows:
        current_window = windows[-1]
        previous_window = windows[-2] if len(windows) > 1 else None
        db = SessionLocal()
        try:
            emergence_metrics_latest_window = compute_emergence_metrics(
                db,
                window_start=current_window.start,
                window_end=current_window.end,
                previous_window_start=(previous_window.start if previous_window else None),
                previous_window_end=(previous_window.end if previous_window else None),
            )
            emergence_metrics_latest_window.pop("coalition_edge_keys", None)
        finally:
            db.close()

    report = {
        "generated_at_utc": _iso(generated_at),
        "windows": args.windows,
        "window_minutes": args.window_minutes,
        "latest_window": latest,
        "emergence_metrics_latest_window": emergence_metrics_latest_window,
        "resource_concentration_now": _resource_concentration(),
        "rows": window_rows,
    }

    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    csv_path = outdir / f"metrics_{stamp}.csv"
    json_path = outdir / f"metrics_{stamp}.json"
    latest_csv_path = outdir / "metrics_latest.csv"
    latest_json_path = outdir / "metrics_latest.json"

    _write_csv(window_rows, csv_path)
    _write_csv(window_rows, latest_csv_path)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "generated_at_utc": report["generated_at_utc"],
                "windows": args.windows,
                "window_minutes": args.window_minutes,
                "events_in_lookback": len(events),
                "latest_window": latest,
                "csv": str(csv_path),
                "json": str(json_path),
                "latest_csv": str(latest_csv_path),
                "latest_json": str(latest_json_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
