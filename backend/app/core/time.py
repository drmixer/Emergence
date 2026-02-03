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

