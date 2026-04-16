#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.guarded_stop_scheduler import (
    build_launch_agent_spec,
    default_railway_path,
    default_label,
    default_plist_path,
    execute_guarded_stop,
    install_launch_agent,
    parse_stop_at,
    repo_root_from_script,
    uninstall_launch_agent,
)


def _project_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return repo_root_from_script(Path(__file__))


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule or execute a guarded simulation stop.")
    sub = parser.add_subparsers(dest="command", required=True)

    schedule = sub.add_parser("schedule", help="Install a local launchd job that stops a run at or after a target time.")
    schedule.add_argument("--run-id", required=True)
    schedule.add_argument("--stop-at", required=True, help="ISO-8601 timestamp with timezone, for example 2026-04-15T10:00:00-07:00")
    schedule.add_argument("--project-root", default=None)
    schedule.add_argument("--label", default=None)
    schedule.add_argument("--plist-path", default=None)
    schedule.add_argument("--log-path", default=None)
    schedule.add_argument("--railway-path", default=None)
    schedule.add_argument("--dry-run", action="store_true")

    execute = sub.add_parser("execute", help="Guarded stop entrypoint invoked by launchd.")
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--stop-at", required=True)
    execute.add_argument("--project-root", default=None)
    execute.add_argument("--label", required=True)
    execute.add_argument("--plist-path", required=True)
    execute.add_argument("--log-path", default=None)
    execute.add_argument("--railway-path", default=None)
    execute.add_argument("--dry-run", action="store_true")

    unschedule = sub.add_parser("unschedule", help="Remove a previously scheduled local guarded stop.")
    unschedule.add_argument("--run-id", required=True)
    unschedule.add_argument("--label", default=None)
    unschedule.add_argument("--plist-path", default=None)
    unschedule.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    project_root = _project_root(getattr(args, "project_root", None))

    if args.command == "schedule":
        stop_at = parse_stop_at(args.stop_at)
        label = str(args.label or "").strip() or default_label(args.run_id)
        plist_path = Path(args.plist_path).expanduser().resolve() if args.plist_path else default_plist_path(label)
        log_path = Path(args.log_path).expanduser().resolve() if args.log_path else None
        railway_path = Path(args.railway_path).expanduser().resolve() if args.railway_path else default_railway_path()
        spec = build_launch_agent_spec(
            run_id=args.run_id,
            stop_at=stop_at,
            project_root=project_root,
            script_path=Path(__file__),
            label=label,
            plist_path=plist_path,
            log_path=log_path,
            railway_path=railway_path,
        )
        payload = {
            "command": "schedule",
            "run_id": args.run_id,
            "stop_at": stop_at.isoformat(),
            "label": spec.label,
            "plist_path": str(spec.plist_path),
            "log_path": str(spec.log_path),
            "railway_path": str(railway_path),
            "program_arguments": spec.program_arguments,
        }
        if args.dry_run:
            payload["dry_run"] = True
        else:
            payload["install_result"] = install_launch_agent(spec)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "execute":
        result = execute_guarded_stop(
            run_id=args.run_id,
            stop_at=parse_stop_at(args.stop_at),
            project_root=project_root,
            label=str(args.label).strip(),
            plist_path=Path(args.plist_path).expanduser().resolve(),
            railway_path=Path(args.railway_path).expanduser().resolve() if args.railway_path else default_railway_path(),
            dry_run=bool(args.dry_run),
        )
        if args.log_path:
            result["log_path"] = str(Path(args.log_path).expanduser().resolve())
        print(json.dumps(result, indent=2))
        return

    if args.command == "unschedule":
        label = str(args.label or "").strip() or default_label(args.run_id)
        plist_path = Path(args.plist_path).expanduser().resolve() if args.plist_path else default_plist_path(label)
        payload = {
            "command": "unschedule",
            "run_id": args.run_id,
            "label": label,
            "plist_path": str(plist_path),
        }
        if args.dry_run:
            payload["dry_run"] = True
        else:
            payload["unschedule_result"] = uninstall_launch_agent(label=label, plist_path=plist_path, remove_file=True)
        print(json.dumps(payload, indent=2))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
