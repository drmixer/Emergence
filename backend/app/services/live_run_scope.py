"""Helpers for scoping live viewer surfaces to the active run window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import ensure_utc
from app.models.models import SimulationRun
from app.services.runtime_config import runtime_config_service


@dataclass
class LiveRunWindow:
    run_id: str | None
    started_at: datetime | None
    ended_at: datetime | None


def get_live_run_window(db: Session) -> LiveRunWindow:
    """Return the runtime-selected run window for live viewer surfaces."""
    run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip() or None
    if not run_id:
        return LiveRunWindow(run_id=None, started_at=None, ended_at=None)

    row = db.query(SimulationRun).filter(SimulationRun.run_id == run_id).first()
    if row is None:
        return LiveRunWindow(run_id=run_id, started_at=None, ended_at=None)

    return LiveRunWindow(
        run_id=run_id,
        started_at=ensure_utc(row.started_at),
        ended_at=ensure_utc(row.ended_at),
    )


def apply_live_run_window(query: Any, column: Any, run_window: LiveRunWindow) -> Any:
    """Filter a SQLAlchemy query to the live run window when available."""
    if run_window.started_at is not None:
        query = query.filter(column >= run_window.started_at)
    if run_window.ended_at is not None:
        query = query.filter(column <= run_window.ended_at)
    return query
