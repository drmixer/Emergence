"""Helpers for deriving simulation time from persisted activity."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import ensure_utc
from app.models.models import Event


def get_simulation_anchor(db: Session):
    """Return the earliest non-summary event timestamp, or earliest event as fallback."""
    first_core_event = (
        db.query(Event)
        .filter(Event.event_type != "daily_summary")
        .order_by(Event.created_at.asc(), Event.id.asc())
        .first()
    )
    if first_core_event and first_core_event.created_at:
        return ensure_utc(first_core_event.created_at)

    first_any_event = db.query(Event).order_by(Event.created_at.asc(), Event.id.asc()).first()
    if first_any_event and first_any_event.created_at:
        return ensure_utc(first_any_event.created_at)
    return None


def get_latest_simulation_activity_at(db: Session):
    """Return the latest non-summary event timestamp, or latest event as fallback."""
    latest_core_event = (
        db.query(Event)
        .filter(Event.event_type != "daily_summary")
        .order_by(Event.created_at.desc(), Event.id.desc())
        .first()
    )
    if latest_core_event and latest_core_event.created_at:
        return ensure_utc(latest_core_event.created_at)

    latest_any_event = db.query(Event).order_by(Event.created_at.desc(), Event.id.desc()).first()
    if latest_any_event and latest_any_event.created_at:
        return ensure_utc(latest_any_event.created_at)
    return None


def get_simulation_day_delta() -> timedelta:
    """Return the configured simulation day duration."""
    day_length_minutes = max(1, int(getattr(settings, "DAY_LENGTH_MINUTES", 60) or 60))
    return timedelta(minutes=day_length_minutes)


def get_simulation_day_number(db: Session) -> int:
    """
    Derive the current simulation day from the latest persisted activity.

    This intentionally freezes when the run is paused or stopped instead of
    drifting forward with wall-clock time.
    """
    anchor = get_simulation_anchor(db)
    if anchor is None:
        return 0

    latest_at = get_latest_simulation_activity_at(db) or anchor
    if latest_at <= anchor:
        return 1

    elapsed = latest_at - anchor
    return int(elapsed // get_simulation_day_delta()) + 1


def get_completed_simulation_day_count(db: Session) -> int:
    """Return the number of fully completed simulation days based on persisted activity."""
    anchor = get_simulation_anchor(db)
    if anchor is None:
        return 0

    latest_at = get_latest_simulation_activity_at(db)
    if latest_at is None or latest_at <= anchor:
        return 0

    return int((latest_at - anchor) // get_simulation_day_delta())


def get_simulation_elapsed(db: Session) -> timedelta:
    """Return elapsed simulated wall time between first and latest activity."""
    anchor = get_simulation_anchor(db)
    latest_at = get_latest_simulation_activity_at(db)
    if anchor is None or latest_at is None or latest_at <= anchor:
        return timedelta(0)
    return latest_at - anchor
