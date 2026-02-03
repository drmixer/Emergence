"""
Time helpers.

All database timestamps are timezone-aware (UTC). Use these helpers instead of
`datetime.utcnow()` to avoid mixing naive and aware datetimes.
"""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """
    Coerce a datetime to timezone-aware UTC.

    Some older rows may have been written with naive datetimes; treat those as UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
