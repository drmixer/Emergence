from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.services.guarded_stop_scheduler import (
    build_launch_agent_spec,
    execute_guarded_stop,
    parse_stop_at,
)


def test_build_launch_agent_spec_uses_backend_venv_and_repo_tmp(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "backend"
    python_path = backend_dir / "venv" / "bin" / "python"
    railway_path = tmp_path / "bin" / "railway"
    script_path = backend_dir / "scripts" / "schedule_guarded_stop.py"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    railway_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")
    railway_path.write_text("", encoding="utf-8")
    script_path.write_text("", encoding="utf-8")

    spec = build_launch_agent_spec(
        run_id="real-20260415T085921Z",
        stop_at=parse_stop_at("2026-04-16T10:00:00-07:00"),
        project_root=project_root,
        script_path=script_path,
        railway_path=railway_path,
    )

    assert spec.log_path == project_root / "tmp" / "auto-stop-real-20260415T085921Z.log"
    assert spec.program_arguments[0] == str(python_path.resolve())
    assert spec.program_arguments[1] == str(script_path.resolve())
    assert spec.program_arguments[2] == "execute"
    assert spec.program_arguments[-2] == "--railway-path"
    assert spec.program_arguments[-1] == str(railway_path.resolve())


def test_execute_guarded_stop_stops_matching_run_and_unschedules(tmp_path: Path):
    calls: list[str] = []

    def _status_fetcher(_project_root: Path, _railway_path: Path | None) -> dict[str, object]:
        calls.append("status")
        return {
            "simulation_active": True,
            "simulation_run_id": "real-20260415T085921Z",
        }

    def _stop_runner(_project_root: Path, _railway_path: Path | None) -> dict[str, object]:
        calls.append("stop")
        return {"stdout": "stopped"}

    def _unscheduler(**kwargs) -> dict[str, object]:
        calls.append("unschedule")
        return kwargs

    result = execute_guarded_stop(
        run_id="real-20260415T085921Z",
        stop_at=parse_stop_at("2026-04-16T10:00:00-07:00"),
        project_root=tmp_path,
        label="com.emergence.sim-stop.real-20260415T085921Z",
        plist_path=tmp_path / "guarded-stop.plist",
        now=datetime(2026, 4, 16, 17, 1, tzinfo=timezone.utc),
        status_fetcher=_status_fetcher,
        stop_runner=_stop_runner,
        unscheduler=_unscheduler,
    )

    assert result["result"] == "stopped"
    assert calls == ["status", "stop", "unschedule"]


def test_execute_guarded_stop_keeps_schedule_on_status_failure(tmp_path: Path):
    calls: list[str] = []

    def _status_fetcher(_project_root: Path, _railway_path: Path | None) -> dict[str, object]:
        calls.append("status")
        raise RuntimeError("railway unavailable")

    def _unscheduler(**kwargs) -> dict[str, object]:
        calls.append("unschedule")
        return kwargs

    result = execute_guarded_stop(
        run_id="real-20260415T085921Z",
        stop_at=parse_stop_at("2026-04-16T10:00:00-07:00"),
        project_root=tmp_path,
        label="com.emergence.sim-stop.real-20260415T085921Z",
        plist_path=tmp_path / "guarded-stop.plist",
        now=datetime(2026, 4, 16, 17, 1, tzinfo=timezone.utc),
        status_fetcher=_status_fetcher,
        unscheduler=_unscheduler,
    )

    assert result["result"] == "retrying"
    assert calls == ["status"]
