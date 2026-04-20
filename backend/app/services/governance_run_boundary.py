"""Helpers for keeping proposals and laws isolated to a single run window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, now_utc
from app.models.models import Law, Proposal
from app.services.live_run_scope import LiveRunWindow, get_run_window


@dataclass(frozen=True)
class GovernanceBoundaryCleanupResult:
    proposals_expired: int = 0
    laws_deactivated: int = 0


def _windowed_query(query, column, *, started_at: datetime | None, ended_at: datetime | None):
    if started_at is not None:
        query = query.filter(column >= started_at)
    if ended_at is not None:
        query = query.filter(column <= ended_at)
    return query


def _expire_active_proposals(
    db: Session,
    *,
    started_at: datetime | None,
    ended_at: datetime | None,
    resolved_at: datetime,
) -> int:
    proposals = _windowed_query(
        db.query(Proposal).filter(Proposal.status == "active"),
        Proposal.created_at,
        started_at=started_at,
        ended_at=ended_at,
    ).all()
    for proposal in proposals:
        proposal.status = "expired"
        proposal.resolved_at = resolved_at
        db.add(proposal)
    return len(proposals)


def _deactivate_active_laws(
    db: Session,
    *,
    started_at: datetime | None,
    ended_at: datetime | None,
    repealed_at: datetime,
) -> int:
    laws = _windowed_query(
        db.query(Law).filter(Law.active.is_(True)),
        Law.passed_at,
        started_at=started_at,
        ended_at=ended_at,
    ).all()
    for law in laws:
        law.active = False
        if law.repealed_at is None:
            law.repealed_at = repealed_at
        db.add(law)
    return len(laws)


def close_run_governance_state(
    db: Session,
    *,
    run_id: str | None,
    cutoff_at: datetime | None = None,
) -> GovernanceBoundaryCleanupResult:
    """Archive active governance created inside a run so it cannot bleed forward."""
    run_window = get_run_window(db, run_id)
    if run_window.run_id is None:
        return GovernanceBoundaryCleanupResult()

    cutoff = ensure_utc(cutoff_at) or ensure_utc(run_window.ended_at) or now_utc()
    started_at = ensure_utc(run_window.started_at)
    ended_at = ensure_utc(run_window.ended_at) or cutoff

    return GovernanceBoundaryCleanupResult(
        proposals_expired=_expire_active_proposals(
            db,
            started_at=started_at,
            ended_at=ended_at,
            resolved_at=cutoff,
        ),
        laws_deactivated=_deactivate_active_laws(
            db,
            started_at=started_at,
            ended_at=ended_at,
            repealed_at=cutoff,
        ),
    )


def retire_inherited_governance_state(
    db: Session,
    *,
    run_id: str | None,
    cutoff_at: datetime | None = None,
) -> GovernanceBoundaryCleanupResult:
    """Deactivate older active governance before a new run begins."""
    run_window: LiveRunWindow = get_run_window(db, run_id)
    if run_window.run_id is None or run_window.started_at is None:
        return GovernanceBoundaryCleanupResult()

    cutoff = ensure_utc(cutoff_at) or ensure_utc(run_window.started_at) or now_utc()

    return GovernanceBoundaryCleanupResult(
        proposals_expired=_expire_active_proposals(
            db,
            started_at=None,
            ended_at=cutoff,
            resolved_at=cutoff,
        ),
        laws_deactivated=_deactivate_active_laws(
            db,
            started_at=None,
            ended_at=cutoff,
            repealed_at=cutoff,
        ),
    )
