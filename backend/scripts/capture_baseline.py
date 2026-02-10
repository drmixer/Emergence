#!/usr/bin/env python3
"""
Capture a baseline snapshot for runtime guardrails.

This script writes a single JSON artifact under output/baseline containing:
- current budget counters
- active stop-condition thresholds
- trailing provider failure stats
- fresh rolling metrics export (via scripts/eval_metrics.py)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget


def _runtime_thresholds() -> dict[str, Any]:
    keys = [
        "OPENROUTER_RPM_LIMIT",
        "LLM_DAILY_BUDGET_USD_SOFT",
        "LLM_DAILY_BUDGET_USD_HARD",
        "LLM_MAX_CALLS_PER_DAY_TOTAL",
        "LLM_MAX_CALLS_PER_DAY_OPENROUTER_FREE",
        "LLM_MAX_CALLS_PER_DAY_GROQ",
        "LLM_MAX_CALLS_PER_DAY_GEMINI",
        "STOP_CONDITION_ENFORCEMENT_ENABLED",
        "STOP_PROVIDER_FAILURE_WINDOW_MINUTES",
        "STOP_PROVIDER_FAILURE_THRESHOLD",
        "STOP_DB_POOL_UTILIZATION_THRESHOLD",
        "STOP_DB_POOL_CONSECUTIVE_CHECKS",
    ]
    return {key: runtime_config_service.get_effective_value_cached(key) for key in keys}


def _provider_failure_stats(window_minutes: int) -> dict[str, Any]:
    since_ts = now_utc() - timedelta(minutes=max(1, int(window_minutes or 1)))
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_count,
                    COALESCE(SUM(CASE WHEN success THEN 0 ELSE 1 END), 0) AS failure_count
                FROM llm_usage
                WHERE created_at >= :since_ts
                """
            ),
            {"since_ts": since_ts},
        ).first()
        successes = int((row.success_count if row else 0) or 0)
        failures = int((row.failure_count if row else 0) or 0)
        total = successes + failures
        return {
            "window_minutes": int(window_minutes),
            "successes": successes,
            "failures": failures,
            "total": total,
            "failure_rate": (failures / total) if total > 0 else 0.0,
        }
    except Exception as exc:
        return {
            "window_minutes": int(window_minutes),
            "error": str(exc),
        }
    finally:
        db.close()


def _run_eval_metrics(
    backend_root: Path, outdir: Path, windows: int, window_minutes: int
) -> dict[str, Any]:
    metrics_outdir = outdir / "metrics"
    metrics_outdir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(backend_root / "scripts" / "eval_metrics.py"),
        "--windows",
        str(int(windows)),
        "--window-minutes",
        str(int(window_minutes)),
        "--outdir",
        str(metrics_outdir),
    ]
    completed = subprocess.run(
        cmd,
        cwd=str(backend_root),
        capture_output=True,
        text=True,
        check=False,
    )

    payload: dict[str, Any] = {
        "command": cmd,
        "returncode": int(completed.returncode),
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }
    if completed.returncode == 0:
        try:
            payload["result"] = json.loads((completed.stdout or "").strip())
        except Exception:
            payload["result"] = None
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture baseline run metrics + stop-condition guardrails."
    )
    parser.add_argument(
        "--windows", type=int, default=12, help="eval_metrics windows (default: 12)"
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=5,
        help="eval_metrics window minutes (default: 5)",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="",
        help="Output directory (default: <repo>/output/baseline)",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    outdir = (
        Path(args.outdir).expanduser().resolve()
        if args.outdir
        else (repo_root / "output" / "baseline")
    )
    outdir.mkdir(parents=True, exist_ok=True)

    generated_at = now_utc()
    thresholds = _runtime_thresholds()
    budget = usage_budget.get_snapshot()
    window_minutes = int(
        thresholds.get("STOP_PROVIDER_FAILURE_WINDOW_MINUTES")
        or args.window_minutes
        or 5
    )

    report = {
        "generated_at_utc": generated_at.isoformat(),
        "thresholds": thresholds,
        "budget_snapshot": {
            "day_key": budget.day_key.isoformat(),
            "calls_total": int(budget.calls_total),
            "calls_openrouter_free": int(budget.calls_openrouter_free),
            "calls_groq": int(budget.calls_groq),
            "calls_gemini": int(budget.calls_gemini),
            "estimated_cost_usd": float(budget.estimated_cost_usd),
        },
        "provider_failure_window": _provider_failure_stats(
            window_minutes=window_minutes
        ),
        "eval_metrics": _run_eval_metrics(
            backend_root=backend_root,
            outdir=outdir,
            windows=int(args.windows),
            window_minutes=int(args.window_minutes),
        ),
    }

    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    baseline_path = outdir / f"baseline_{stamp}.json"
    latest_path = outdir / "baseline_latest.json"
    baseline_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "generated_at_utc": report["generated_at_utc"],
                "baseline_json": str(baseline_path),
                "baseline_latest_json": str(latest_path),
                "eval_metrics_returncode": report["eval_metrics"]["returncode"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
