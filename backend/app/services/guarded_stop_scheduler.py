from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
from typing import Any, Callable


DEFAULT_LABEL_PREFIX = "com.emergence.sim-stop"
DEFAULT_POLL_SECONDS = 60


@dataclass(frozen=True)
class LaunchAgentSpec:
    label: str
    plist_path: Path
    log_path: Path
    working_directory: Path
    program_arguments: list[str]
    start_interval: int = DEFAULT_POLL_SECONDS


def repo_root_from_script(script_path: Path) -> Path:
    return script_path.resolve().parents[2]


def parse_stop_at(raw_value: str) -> datetime:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        raise ValueError("stop_at is required")
    normalized = clean_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("stop_at must include an explicit timezone offset")
    return parsed.astimezone(timezone.utc)


def sanitize_run_id(run_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run_id or "").strip())
    clean = clean.strip(".-")
    return clean or "unknown-run"


def default_label(run_id: str) -> str:
    return f"{DEFAULT_LABEL_PREFIX}.{sanitize_run_id(run_id)}"


def default_plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def default_log_path(project_root: Path, run_id: str) -> Path:
    return project_root / "tmp" / f"auto-stop-{sanitize_run_id(run_id)}.log"


def default_python_path(project_root: Path) -> Path:
    candidate = project_root / "backend" / "venv" / "bin" / "python"
    if candidate.exists():
        return candidate
    return Path(sys.executable).resolve()


def default_railway_path() -> Path:
    env_path = str(os.environ.get("RAILWAY_BIN") or "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()

    resolved = shutil.which("railway")
    if resolved:
        return Path(resolved).resolve()

    common_candidates = [
        Path("/opt/homebrew/bin/railway"),
        Path("/usr/local/bin/railway"),
    ]
    for candidate in common_candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(
        "Unable to resolve railway binary. Set RAILWAY_BIN or install Railway CLI."
    )


def build_launch_agent_spec(
    *,
    run_id: str,
    stop_at: datetime,
    project_root: Path,
    script_path: Path,
    label: str | None = None,
    plist_path: Path | None = None,
    log_path: Path | None = None,
    python_path: Path | None = None,
    railway_path: Path | None = None,
) -> LaunchAgentSpec:
    resolved_label = str(label or "").strip() or default_label(run_id)
    resolved_plist = (plist_path or default_plist_path(resolved_label)).expanduser().resolve()
    resolved_log = (log_path or default_log_path(project_root, run_id)).expanduser().resolve()
    resolved_python = (python_path or default_python_path(project_root)).expanduser().resolve()
    resolved_railway = (railway_path or default_railway_path()).expanduser().resolve()
    resolved_script = script_path.expanduser().resolve()
    return LaunchAgentSpec(
        label=resolved_label,
        plist_path=resolved_plist,
        log_path=resolved_log,
        working_directory=project_root.resolve(),
        program_arguments=[
            str(resolved_python),
            str(resolved_script),
            "execute",
            "--run-id",
            str(run_id),
            "--stop-at",
            stop_at.isoformat(),
            "--project-root",
            str(project_root.resolve()),
            "--label",
            resolved_label,
            "--plist-path",
            str(resolved_plist),
            "--log-path",
            str(resolved_log),
            "--railway-path",
            str(resolved_railway),
        ],
    )


def launch_agent_plist_payload(spec: LaunchAgentSpec) -> dict[str, Any]:
    return {
        "Label": spec.label,
        "ProgramArguments": spec.program_arguments,
        "WorkingDirectory": str(spec.working_directory),
        "RunAtLoad": True,
        "StartInterval": int(spec.start_interval),
        "StandardOutPath": str(spec.log_path),
        "StandardErrorPath": str(spec.log_path),
    }


def write_launch_agent_plist(spec: LaunchAgentSpec) -> Path:
    spec.plist_path.parent.mkdir(parents=True, exist_ok=True)
    spec.log_path.parent.mkdir(parents=True, exist_ok=True)
    with spec.plist_path.open("wb") as handle:
        plistlib.dump(launch_agent_plist_payload(spec), handle, sort_keys=True)
    return spec.plist_path


def launchctl_domain() -> str:
    return f"gui/{os.getuid()}"


def _run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def install_launch_agent(spec: LaunchAgentSpec) -> dict[str, Any]:
    write_launch_agent_plist(spec)
    domain = launchctl_domain()
    bootout = _run_command(
        ["launchctl", "bootout", domain, str(spec.plist_path)],
        check=False,
    )
    bootstrap = _run_command(
        ["launchctl", "bootstrap", domain, str(spec.plist_path)],
    )
    return {
        "label": spec.label,
        "plist_path": str(spec.plist_path),
        "log_path": str(spec.log_path),
        "bootout_returncode": int(bootout.returncode),
        "bootstrap_stdout": bootstrap.stdout.strip(),
        "bootstrap_stderr": bootstrap.stderr.strip(),
    }


def uninstall_launch_agent(*, label: str, plist_path: Path, remove_file: bool = True) -> dict[str, Any]:
    domain = launchctl_domain()
    bootout = _run_command(
        ["launchctl", "bootout", domain, str(plist_path)],
        check=False,
    )
    removed = False
    if remove_file and plist_path.exists():
        plist_path.unlink()
        removed = True
    return {
        "label": label,
        "plist_path": str(plist_path),
        "bootout_returncode": int(bootout.returncode),
        "bootout_stdout": bootout.stdout.strip(),
        "bootout_stderr": bootout.stderr.strip(),
        "plist_removed": removed,
    }


def _railway_control_command(subcommand: str, railway_path: Path | None = None) -> list[str]:
    return [
        str((railway_path or default_railway_path()).expanduser().resolve()),
        "run",
        "-s",
        "backend",
        "--",
        "venv/bin/python",
        "scripts/simulation_control.py",
        subcommand,
    ]


def fetch_remote_status(project_root: Path, railway_path: Path | None = None) -> dict[str, Any]:
    result = _run_command(
        _railway_control_command("status", railway_path),
        cwd=project_root / "backend",
    )
    return json.loads(result.stdout)


def stop_remote_run(project_root: Path, railway_path: Path | None = None) -> dict[str, Any]:
    result = _run_command(
        _railway_control_command("stop", railway_path),
        cwd=project_root / "backend",
    )
    return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def execute_guarded_stop(
    *,
    run_id: str,
    stop_at: datetime,
    project_root: Path,
    label: str,
    plist_path: Path,
    railway_path: Path | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    status_fetcher: Callable[[Path, Path | None], dict[str, Any]] = fetch_remote_status,
    stop_runner: Callable[[Path, Path | None], dict[str, Any]] = stop_remote_run,
    unscheduler: Callable[..., dict[str, Any]] = uninstall_launch_agent,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    if current_time < stop_at:
        return {
            "result": "waiting",
            "run_id": run_id,
            "stop_at": stop_at.isoformat(),
            "checked_at": current_time.isoformat(),
        }

    try:
        status = status_fetcher(project_root, railway_path)
    except Exception as exc:
        return {
            "result": "retrying",
            "run_id": run_id,
            "stop_at": stop_at.isoformat(),
            "checked_at": current_time.isoformat(),
            "error": str(exc),
        }

    active_run_id = str(status.get("simulation_run_id") or "").strip()
    simulation_active = bool(status.get("simulation_active"))

    if simulation_active and active_run_id == str(run_id).strip():
        if dry_run:
            return {
                "result": "would_stop",
                "run_id": run_id,
                "checked_at": current_time.isoformat(),
                "status": status,
                "would_unschedule": True,
            }
        try:
            stop_result = stop_runner(project_root, railway_path)
        except Exception as exc:
            return {
                "result": "retrying",
                "run_id": run_id,
                "checked_at": current_time.isoformat(),
                "status": status,
                "error": str(exc),
            }
        unschedule_result = unscheduler(label=label, plist_path=plist_path, remove_file=True)
        return {
            "result": "stopped",
            "run_id": run_id,
            "checked_at": current_time.isoformat(),
            "status": status,
            "stop_result": stop_result,
            "unschedule_result": unschedule_result,
        }

    if dry_run:
        return {
            "result": "would_skip",
            "run_id": run_id,
            "checked_at": current_time.isoformat(),
            "status": status,
            "would_unschedule": True,
        }

    unschedule_result = unscheduler(label=label, plist_path=plist_path, remove_file=True)
    return {
        "result": "skipped",
        "run_id": run_id,
        "checked_at": current_time.isoformat(),
        "status": status,
        "unschedule_result": unschedule_result,
    }
