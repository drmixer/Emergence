from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc
from app.models.models import KpiEvent

ALLOWED_KPI_EVENT_NAMES = {
    "landing_view",
    "landing_run_click",
    "run_detail_view",
    "replay_start",
    "replay_complete",
    "share_clicked",
    "share_copied",
    "share_native_success",
    "shared_link_open",
    "onboarding_shown",
    "onboarding_completed",
    "onboarding_skipped",
    "onboarding_glossary_opened",
}
SHARE_EVENT_NAMES = {"share_clicked", "share_copied", "share_native_success"}
RETENTION_EVENT_NAMES = {"run_detail_view", "replay_start"}


def _clean_text(value: Any, *, max_len: int) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    return text_value[:max_len]


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    den = float(denominator or 0)
    if den <= 0:
        return 0.0
    return float(numerator or 0) / den


def _clean_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, raw in value.items():
        key_text = _clean_text(key, max_len=80)
        if not key_text:
            continue
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            cleaned[key_text] = raw
        elif isinstance(raw, (list, dict)):
            cleaned[key_text] = raw
        else:
            cleaned[key_text] = str(raw)
        if len(cleaned) >= 20:
            break
    return cleaned


def normalize_kpi_event(payload: dict[str, Any]) -> dict[str, Any]:
    event_name = _clean_text(payload.get("event_name"), max_len=64).lower()
    if event_name not in ALLOWED_KPI_EVENT_NAMES:
        raise ValueError("unsupported event_name")

    visitor_id = _clean_text(payload.get("visitor_id"), max_len=128)
    if not visitor_id:
        raise ValueError("visitor_id is required")

    session_id = _clean_text(payload.get("session_id"), max_len=128) or None
    run_id = _clean_text(payload.get("run_id"), max_len=64) or None
    surface = _clean_text(payload.get("surface"), max_len=64) or None
    target = _clean_text(payload.get("target"), max_len=64) or None
    path = _clean_text(payload.get("path"), max_len=255) or None
    referrer = _clean_text(payload.get("referrer"), max_len=255) or None

    event_id = payload.get("event_id")
    if event_id is not None:
        try:
            event_id = int(event_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("event_id must be an integer") from exc
        if event_id <= 0:
            raise ValueError("event_id must be > 0")

    return {
        "event_name": event_name,
        "visitor_id": visitor_id,
        "session_id": session_id,
        "run_id": run_id,
        "event_id": event_id,
        "surface": surface,
        "target": target,
        "path": path,
        "referrer": referrer,
        "event_metadata": _clean_metadata(payload.get("metadata")),
    }


def _compute_retention_for_day(db: Session, *, cohort_day: date, followup_days: int) -> dict[str, Any]:
    cohort_size = int(
        db.execute(
            text(
                """
                SELECT COUNT(DISTINCT visitor_id)
                FROM kpi_events
                WHERE day_key = :day_key
                  AND event_name IN ('run_detail_view', 'replay_start')
                """
            ),
            {"day_key": cohort_day},
        ).scalar()
        or 0
    )

    followup_day = cohort_day + timedelta(days=followup_days)
    today = now_utc().date()
    if followup_day > today:
        return {
            "cohort_size": cohort_size,
            "returning_users": 0,
            "retention_rate": None,
        }

    returning_users = int(
        db.execute(
            text(
                """
                SELECT COUNT(DISTINCT k2.visitor_id)
                FROM kpi_events k2
                WHERE k2.day_key = :followup_day
                  AND k2.event_name IN ('run_detail_view', 'replay_start')
                  AND k2.visitor_id IN (
                    SELECT DISTINCT k1.visitor_id
                    FROM kpi_events k1
                    WHERE k1.day_key = :cohort_day
                      AND k1.event_name IN ('run_detail_view', 'replay_start')
                  )
                """
            ),
            {"cohort_day": cohort_day, "followup_day": followup_day},
        ).scalar()
        or 0
    )

    return {
        "cohort_size": cohort_size,
        "returning_users": returning_users,
        "retention_rate": _safe_ratio(returning_users, cohort_size),
    }


def compute_daily_rollup(db: Session, *, day_key: date) -> dict[str, Any]:
    totals = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE event_name = 'landing_view') AS landing_views,
              COUNT(DISTINCT CASE WHEN event_name = 'landing_view' THEN visitor_id END) AS landing_view_visitors,
              COUNT(*) FILTER (WHERE event_name = 'landing_run_click') AS landing_run_clicks,
              COUNT(DISTINCT CASE WHEN event_name = 'landing_run_click' THEN visitor_id END) AS landing_run_click_visitors,
              COUNT(*) FILTER (WHERE event_name = 'run_detail_view') AS run_detail_views,
              COUNT(DISTINCT CASE WHEN event_name = 'run_detail_view' THEN visitor_id END) AS run_detail_visitors,
              COUNT(*) FILTER (WHERE event_name = 'replay_start') AS replay_starts,
              COUNT(DISTINCT CASE WHEN event_name = 'replay_start' THEN visitor_id END) AS replay_start_visitors,
              COUNT(*) FILTER (WHERE event_name = 'replay_complete') AS replay_completions,
              COUNT(DISTINCT CASE WHEN event_name = 'replay_complete' THEN visitor_id END) AS replay_completion_visitors,
              COUNT(*) FILTER (WHERE event_name IN ('share_clicked', 'share_copied', 'share_native_success')) AS share_actions,
              COUNT(DISTINCT CASE WHEN event_name IN ('share_clicked', 'share_copied', 'share_native_success') THEN visitor_id END) AS share_action_visitors,
              COUNT(*) FILTER (WHERE event_name = 'share_clicked') AS share_clicks,
              COUNT(DISTINCT CASE WHEN event_name = 'share_clicked' THEN visitor_id END) AS share_click_visitors,
              COUNT(*) FILTER (WHERE event_name = 'shared_link_open') AS shared_link_opens,
              COUNT(DISTINCT CASE WHEN event_name = 'shared_link_open' THEN visitor_id END) AS shared_link_open_visitors,
              COUNT(DISTINCT CASE WHEN event_name IN ('run_detail_view', 'replay_start') THEN visitor_id END) AS viewer_visitors
            FROM kpi_events
            WHERE day_key = :day_key
            """
        ),
        {"day_key": day_key},
    ).first()

    landing_view_visitors = int((totals.landing_view_visitors if totals else 0) or 0)
    landing_run_click_visitors = int((totals.landing_run_click_visitors if totals else 0) or 0)
    run_detail_visitors = int((totals.run_detail_visitors if totals else 0) or 0)
    replay_start_visitors = int((totals.replay_start_visitors if totals else 0) or 0)
    replay_completion_visitors = int((totals.replay_completion_visitors if totals else 0) or 0)
    share_action_visitors = int((totals.share_action_visitors if totals else 0) or 0)
    share_click_visitors = int((totals.share_click_visitors if totals else 0) or 0)
    shared_link_open_visitors = int((totals.shared_link_open_visitors if totals else 0) or 0)
    viewer_visitors = int((totals.viewer_visitors if totals else 0) or 0)

    d1 = _compute_retention_for_day(db, cohort_day=day_key, followup_days=1)
    d7 = _compute_retention_for_day(db, cohort_day=day_key, followup_days=7)

    return {
        "day_key": day_key,
        "landing_views": int((totals.landing_views if totals else 0) or 0),
        "landing_view_visitors": landing_view_visitors,
        "landing_run_clicks": int((totals.landing_run_clicks if totals else 0) or 0),
        "landing_run_click_visitors": landing_run_click_visitors,
        "run_detail_views": int((totals.run_detail_views if totals else 0) or 0),
        "run_detail_visitors": run_detail_visitors,
        "replay_starts": int((totals.replay_starts if totals else 0) or 0),
        "replay_start_visitors": replay_start_visitors,
        "replay_completions": int((totals.replay_completions if totals else 0) or 0),
        "replay_completion_visitors": replay_completion_visitors,
        "share_actions": int((totals.share_actions if totals else 0) or 0),
        "share_action_visitors": share_action_visitors,
        "share_clicks": int((totals.share_clicks if totals else 0) or 0),
        "share_click_visitors": share_click_visitors,
        "shared_link_opens": int((totals.shared_link_opens if totals else 0) or 0),
        "shared_link_open_visitors": shared_link_open_visitors,
        "landing_to_run_ctr": _safe_ratio(landing_run_click_visitors, landing_view_visitors),
        "run_to_replay_start_rate": _safe_ratio(replay_start_visitors, run_detail_visitors),
        "replay_completion_rate": _safe_ratio(replay_completion_visitors, replay_start_visitors),
        "share_action_rate": _safe_ratio(share_action_visitors, viewer_visitors),
        "shared_link_ctr": _safe_ratio(shared_link_open_visitors, share_click_visitors),
        "d1_cohort_size": int(d1["cohort_size"] or 0),
        "d1_returning_users": int(d1["returning_users"] or 0),
        "d1_retention_rate": d1["retention_rate"],
        "d7_cohort_size": int(d7["cohort_size"] or 0),
        "d7_returning_users": int(d7["returning_users"] or 0),
        "d7_retention_rate": d7["retention_rate"],
    }


def upsert_daily_rollup(db: Session, *, day_key: date) -> dict[str, Any]:
    rollup = compute_daily_rollup(db, day_key=day_key)
    db.execute(
        text(
            """
            INSERT INTO kpi_daily_rollups (
              day_key,
              landing_views,
              landing_view_visitors,
              landing_run_clicks,
              landing_run_click_visitors,
              run_detail_views,
              run_detail_visitors,
              replay_starts,
              replay_start_visitors,
              replay_completions,
              replay_completion_visitors,
              share_actions,
              share_action_visitors,
              share_clicks,
              share_click_visitors,
              shared_link_opens,
              shared_link_open_visitors,
              landing_to_run_ctr,
              run_to_replay_start_rate,
              replay_completion_rate,
              share_action_rate,
              shared_link_ctr,
              d1_cohort_size,
              d1_returning_users,
              d1_retention_rate,
              d7_cohort_size,
              d7_returning_users,
              d7_retention_rate,
              created_at,
              updated_at
            ) VALUES (
              :day_key,
              :landing_views,
              :landing_view_visitors,
              :landing_run_clicks,
              :landing_run_click_visitors,
              :run_detail_views,
              :run_detail_visitors,
              :replay_starts,
              :replay_start_visitors,
              :replay_completions,
              :replay_completion_visitors,
              :share_actions,
              :share_action_visitors,
              :share_clicks,
              :share_click_visitors,
              :shared_link_opens,
              :shared_link_open_visitors,
              :landing_to_run_ctr,
              :run_to_replay_start_rate,
              :replay_completion_rate,
              :share_action_rate,
              :shared_link_ctr,
              :d1_cohort_size,
              :d1_returning_users,
              :d1_retention_rate,
              :d7_cohort_size,
              :d7_returning_users,
              :d7_retention_rate,
              NOW(),
              NOW()
            )
            ON CONFLICT (day_key) DO UPDATE SET
              landing_views = EXCLUDED.landing_views,
              landing_view_visitors = EXCLUDED.landing_view_visitors,
              landing_run_clicks = EXCLUDED.landing_run_clicks,
              landing_run_click_visitors = EXCLUDED.landing_run_click_visitors,
              run_detail_views = EXCLUDED.run_detail_views,
              run_detail_visitors = EXCLUDED.run_detail_visitors,
              replay_starts = EXCLUDED.replay_starts,
              replay_start_visitors = EXCLUDED.replay_start_visitors,
              replay_completions = EXCLUDED.replay_completions,
              replay_completion_visitors = EXCLUDED.replay_completion_visitors,
              share_actions = EXCLUDED.share_actions,
              share_action_visitors = EXCLUDED.share_action_visitors,
              share_clicks = EXCLUDED.share_clicks,
              share_click_visitors = EXCLUDED.share_click_visitors,
              shared_link_opens = EXCLUDED.shared_link_opens,
              shared_link_open_visitors = EXCLUDED.shared_link_open_visitors,
              landing_to_run_ctr = EXCLUDED.landing_to_run_ctr,
              run_to_replay_start_rate = EXCLUDED.run_to_replay_start_rate,
              replay_completion_rate = EXCLUDED.replay_completion_rate,
              share_action_rate = EXCLUDED.share_action_rate,
              shared_link_ctr = EXCLUDED.shared_link_ctr,
              d1_cohort_size = EXCLUDED.d1_cohort_size,
              d1_returning_users = EXCLUDED.d1_returning_users,
              d1_retention_rate = EXCLUDED.d1_retention_rate,
              d7_cohort_size = EXCLUDED.d7_cohort_size,
              d7_returning_users = EXCLUDED.d7_returning_users,
              d7_retention_rate = EXCLUDED.d7_retention_rate,
              updated_at = NOW()
            """
        ),
        rollup,
    )
    return rollup


def refresh_recent_rollups(db: Session, *, days: int) -> None:
    resolved_days = max(1, min(90, int(days)))
    today = now_utc().date()
    for offset in range(resolved_days):
        day_key = today - timedelta(days=offset)
        upsert_daily_rollup(db, day_key=day_key)


def record_kpi_event(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(getattr(settings, "KPI_EVENT_INGEST_ENABLED", True)):
        raise ValueError("kpi event ingest is disabled")

    clean = normalize_kpi_event(payload)
    occurred_at = now_utc()
    day_key = occurred_at.date()
    event = KpiEvent(
        day_key=day_key,
        occurred_at=occurred_at,
        event_name=str(clean["event_name"]),
        visitor_id=str(clean["visitor_id"]),
        session_id=clean["session_id"],
        run_id=clean["run_id"],
        event_id=clean["event_id"],
        surface=clean["surface"],
        target=clean["target"],
        path=clean["path"],
        referrer=clean["referrer"],
        event_metadata=clean["event_metadata"],
    )
    db.add(event)
    db.flush()

    # Update the current day plus retention-dependent cohorts.
    refresh_days = {
        day_key,
        day_key - timedelta(days=1),
        day_key - timedelta(days=7),
    }
    for refresh_day in refresh_days:
        upsert_daily_rollup(db, day_key=refresh_day)

    db.commit()
    return {
        "id": int(event.id or 0),
        "event_name": event.event_name,
        "day_key": day_key.isoformat(),
    }


def _serialize_rollup_row(row: Any) -> dict[str, Any]:
    return {
        "day_key": row.day_key.isoformat(),
        "landing_views": int(row.landing_views or 0),
        "landing_view_visitors": int(row.landing_view_visitors or 0),
        "landing_run_clicks": int(row.landing_run_clicks or 0),
        "landing_run_click_visitors": int(row.landing_run_click_visitors or 0),
        "run_detail_views": int(row.run_detail_views or 0),
        "run_detail_visitors": int(row.run_detail_visitors or 0),
        "replay_starts": int(row.replay_starts or 0),
        "replay_start_visitors": int(row.replay_start_visitors or 0),
        "replay_completions": int(row.replay_completions or 0),
        "replay_completion_visitors": int(row.replay_completion_visitors or 0),
        "share_actions": int(row.share_actions or 0),
        "share_action_visitors": int(row.share_action_visitors or 0),
        "share_clicks": int(row.share_clicks or 0),
        "share_click_visitors": int(row.share_click_visitors or 0),
        "shared_link_opens": int(row.shared_link_opens or 0),
        "shared_link_open_visitors": int(row.shared_link_open_visitors or 0),
        "landing_to_run_ctr": float(row.landing_to_run_ctr or 0.0),
        "run_to_replay_start_rate": float(row.run_to_replay_start_rate or 0.0),
        "replay_completion_rate": float(row.replay_completion_rate or 0.0),
        "share_action_rate": float(row.share_action_rate or 0.0),
        "shared_link_ctr": float(row.shared_link_ctr or 0.0),
        "d1_cohort_size": int(row.d1_cohort_size or 0),
        "d1_returning_users": int(row.d1_returning_users or 0),
        "d1_retention_rate": (None if row.d1_retention_rate is None else float(row.d1_retention_rate)),
        "d7_cohort_size": int(row.d7_cohort_size or 0),
        "d7_returning_users": int(row.d7_returning_users or 0),
        "d7_retention_rate": (None if row.d7_retention_rate is None else float(row.d7_retention_rate)),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_recent_rollups(db: Session, *, days: int, refresh: bool = True) -> dict[str, Any]:
    resolved_days = max(1, min(90, int(days)))
    if refresh:
        refresh_recent_rollups(db, days=resolved_days)
        db.commit()

    rows = db.execute(
        text(
            """
            SELECT *
            FROM kpi_daily_rollups
            ORDER BY day_key DESC
            LIMIT :limit
            """
        ),
        {"limit": resolved_days},
    ).fetchall()
    items = [_serialize_rollup_row(row) for row in rows]
    latest = items[0] if items else None

    window = items[:7]
    def _avg_rate(field: str) -> float | None:
        values = [float(item[field]) for item in window if item.get(field) is not None]
        if not values:
            return None
        return sum(values) / len(values)

    summary = {
        "latest_day_key": latest.get("day_key") if latest else None,
        "latest": latest,
        "seven_day_avg": {
            "landing_to_run_ctr": _avg_rate("landing_to_run_ctr"),
            "run_to_replay_start_rate": _avg_rate("run_to_replay_start_rate"),
            "replay_completion_rate": _avg_rate("replay_completion_rate"),
            "share_action_rate": _avg_rate("share_action_rate"),
            "shared_link_ctr": _avg_rate("shared_link_ctr"),
            "d1_retention_rate": _avg_rate("d1_retention_rate"),
            "d7_retention_rate": _avg_rate("d7_retention_rate"),
        },
    }

    return {"items": items, "summary": summary}
