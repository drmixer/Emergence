from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.models import Agent, AgentLineage, SimulationRun


VALID_LINEAGE_ORIGINS = {"carryover", "fresh"}


def resolve_active_or_latest_season_id(db: Session) -> str | None:
    active_row = (
        db.query(SimulationRun.season_id)
        .filter(
            SimulationRun.season_id.isnot(None),
            SimulationRun.season_id != "",
            SimulationRun.ended_at.is_(None),
        )
        .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
        .first()
    )
    if active_row and str(active_row.season_id or "").strip():
        return str(active_row.season_id).strip()

    latest_row = (
        db.query(SimulationRun.season_id)
        .filter(
            SimulationRun.season_id.isnot(None),
            SimulationRun.season_id != "",
        )
        .order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc())
        .first()
    )
    if latest_row and str(latest_row.season_id or "").strip():
        return str(latest_row.season_id).strip()
    return None


def lineage_map_for_season(db: Session, *, season_id: str | None) -> dict[int, dict[str, Any]]:
    rows: list[AgentLineage] = []
    clean_season_id = str(season_id or "").strip()
    if clean_season_id:
        rows = (
            db.query(AgentLineage)
            .filter(AgentLineage.season_id == clean_season_id)
            .all()
        )
    if not rows:
        rows = (
            db.query(AgentLineage)
            .order_by(AgentLineage.created_at.desc(), AgentLineage.id.desc())
            .all()
        )

    by_child: dict[int, dict[str, Any]] = {}
    for row in rows:
        child_number = int(row.child_agent_number or 0)
        if child_number <= 0 or child_number in by_child:
            continue
        origin = str(row.origin or "").strip()
        by_child[child_number] = {
            "lineage_origin": (origin if origin in VALID_LINEAGE_ORIGINS else None),
            "lineage_season_id": str(row.season_id or "").strip() or None,
            "lineage_parent_agent_number": (
                int(row.parent_agent_number) if row.parent_agent_number is not None else None
            ),
        }
    return by_child


def lineage_payload_for_agent_number(
    agent_number: int | None,
    lineage_by_agent_number: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    safe_agent_number = int(agent_number or 0)
    lineage = lineage_by_agent_number.get(safe_agent_number, {}) if safe_agent_number > 0 else {}
    origin = lineage.get("lineage_origin")
    return {
        "lineage_origin": origin,
        "lineage_is_carryover": bool(origin == "carryover"),
        "lineage_is_fresh": bool(origin == "fresh"),
        "lineage_parent_agent_number": lineage.get("lineage_parent_agent_number"),
        "lineage_season_id": lineage.get("lineage_season_id"),
    }


def agent_number_map(db: Session, *, agent_ids: Iterable[int]) -> dict[int, int]:
    clean_ids = sorted({int(agent_id) for agent_id in agent_ids if int(agent_id) > 0})
    if not clean_ids:
        return {}
    rows = (
        db.query(Agent.id, Agent.agent_number)
        .filter(Agent.id.in_(clean_ids))
        .all()
    )
    return {
        int(agent_id): int(agent_number)
        for agent_id, agent_number in rows
        if agent_id is not None and agent_number is not None
    }
