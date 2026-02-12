"""Season transfer helpers for snapshot export and next-season seeding."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import now_utc
from app.models.models import (
    Agent,
    AgentInventory,
    AgentLineage,
    AgentMemory,
    Law,
    Proposal,
    SeasonSnapshot,
    SimulationRun,
    Vote,
)
from app.services.agent_identity import immutable_alias_for_agent_number

SURVIVOR_SNAPSHOT_TYPE_V1 = "survivors_v1"
TRANSFER_POLICY_VERSION_V1 = "season_transfer_policy_v1"
DEFAULT_TARGET_AGENT_COUNT = 50

_INVENTORY_BASELINE = {
    "food": Decimal(str(settings.STARTING_FOOD)),
    "energy": Decimal(str(settings.STARTING_ENERGY)),
    "materials": Decimal(str(settings.STARTING_MATERIALS)),
}


def _as_int_list(values: Iterable[Any]) -> list[int]:
    numbers: list[int] = []
    for value in values:
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed >= 1:
            numbers.append(parsed)
    return numbers


def _serialize_survivor_snapshot_payload(
    db: Session,
    *,
    run_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    survivors = (
        db.query(Agent)
        .filter(Agent.status == "active")
        .order_by(Agent.agent_number.asc(), Agent.id.asc())
        .all()
    )
    if not survivors:
        return {
            "version": SURVIVOR_SNAPSHOT_TYPE_V1,
            "run_id": run_id,
            "generated_at": generated_at.isoformat(),
            "survivor_count": 0,
            "survivors": [],
        }

    survivor_ids = [int(agent.id) for agent in survivors]
    inventory_rows = (
        db.query(AgentInventory)
        .filter(AgentInventory.agent_id.in_(survivor_ids))
        .all()
    )
    memory_rows = (
        db.query(AgentMemory)
        .filter(AgentMemory.agent_id.in_(survivor_ids))
        .all()
    )

    inventory_by_agent: dict[int, dict[str, float]] = {}
    for row in inventory_rows:
        agent_inventory = inventory_by_agent.setdefault(int(row.agent_id), {})
        agent_inventory[str(row.resource_type)] = float(row.quantity or 0)

    memory_by_agent: dict[int, AgentMemory] = {int(row.agent_id): row for row in memory_rows}

    survivor_payloads: list[dict[str, Any]] = []
    for agent in survivors:
        memory = memory_by_agent.get(int(agent.id))
        survivor_payloads.append(
            {
                "agent_number": int(agent.agent_number),
                "display_name": str(agent.display_name or "").strip() or None,
                "model_type": str(agent.model_type),
                "tier": int(agent.tier),
                "personality_type": str(agent.personality_type),
                "status": str(agent.status),
                "inventory": inventory_by_agent.get(int(agent.id), {}),
                "memory_summary": (
                    str(memory.summary_text or "").strip() if memory is not None else ""
                ),
            }
        )

    return {
        "version": SURVIVOR_SNAPSHOT_TYPE_V1,
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "survivor_count": len(survivor_payloads),
        "survivors": survivor_payloads,
    }


def export_season_snapshot(
    db: Session,
    *,
    run_id: str,
    snapshot_type: str = SURVIVOR_SNAPSHOT_TYPE_V1,
    dry_run: bool = False,
) -> dict[str, Any]:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        raise ValueError("run_id is required")
    clean_snapshot_type = str(snapshot_type or "").strip() or SURVIVOR_SNAPSHOT_TYPE_V1

    source_run = (
        db.query(SimulationRun)
        .filter(SimulationRun.run_id == clean_run_id)
        .first()
    )
    if source_run is None:
        raise ValueError("run_id must reference an existing simulation run")

    generated_at = now_utc()
    payload = _serialize_survivor_snapshot_payload(
        db,
        run_id=clean_run_id,
        generated_at=generated_at,
    )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "run_id": clean_run_id,
            "snapshot_type": clean_snapshot_type,
            "payload": payload,
            "snapshot_id": None,
        }

    row = SeasonSnapshot(
        run_id=clean_run_id,
        snapshot_type=clean_snapshot_type,
        payload_json=payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "dry_run": False,
        "run_id": clean_run_id,
        "snapshot_type": clean_snapshot_type,
        "payload": payload,
        "snapshot_id": int(row.id),
    }


def _resolve_survivor_agent_numbers(
    db: Session,
    *,
    parent_run_id: str,
    snapshot_type: str,
) -> tuple[list[int], str]:
    latest_snapshot = (
        db.query(SeasonSnapshot)
        .filter(
            SeasonSnapshot.run_id == parent_run_id,
            SeasonSnapshot.snapshot_type == snapshot_type,
        )
        .order_by(SeasonSnapshot.created_at.desc(), SeasonSnapshot.id.desc())
        .first()
    )

    if latest_snapshot is not None and isinstance(latest_snapshot.payload_json, dict):
        raw_survivors = latest_snapshot.payload_json.get("survivors") or []
        if isinstance(raw_survivors, list):
            parsed = _as_int_list(
                [
                    item.get("agent_number")
                    for item in raw_survivors
                    if isinstance(item, dict)
                ]
            )
            deduped_sorted = sorted(set(parsed))
            if deduped_sorted:
                return deduped_sorted, "season_snapshot"
            # An explicit empty list is still a valid snapshot source.
            if raw_survivors == []:
                return [], "season_snapshot"

    live_survivors = (
        db.query(Agent.agent_number)
        .filter(Agent.status == "active")
        .order_by(Agent.agent_number.asc())
        .all()
    )
    return sorted({int(row.agent_number) for row in live_survivors}), "live_status"


def _normalize_agent_inventory(db: Session, *, agent_id: int) -> None:
    existing = {
        str(row.resource_type): row
        for row in db.query(AgentInventory).filter(AgentInventory.agent_id == int(agent_id)).all()
    }
    for resource_type, amount in _INVENTORY_BASELINE.items():
        row = existing.get(resource_type)
        if row is None:
            db.add(
                AgentInventory(
                    agent_id=int(agent_id),
                    resource_type=resource_type,
                    quantity=amount,
                )
            )
        else:
            row.quantity = amount
            db.add(row)


def seed_next_season(
    db: Session,
    *,
    season_id: str,
    parent_run_id: str,
    transfer_policy_version: str,
    carry_passed_laws: bool = False,
    dry_run: bool = True,
    confirm: bool = False,
    target_agent_count: int = DEFAULT_TARGET_AGENT_COUNT,
    snapshot_type: str = SURVIVOR_SNAPSHOT_TYPE_V1,
) -> dict[str, Any]:
    clean_season_id = str(season_id or "").strip()
    clean_parent_run_id = str(parent_run_id or "").strip()
    clean_policy_version = str(transfer_policy_version or "").strip()
    clean_snapshot_type = str(snapshot_type or "").strip() or SURVIVOR_SNAPSHOT_TYPE_V1
    desired_count = int(target_agent_count or 0)

    if not clean_season_id:
        raise ValueError("season_id is required")
    if not clean_parent_run_id:
        raise ValueError("parent_run_id is required")
    if not clean_policy_version:
        raise ValueError("transfer_policy_version is required")
    if desired_count <= 0:
        raise ValueError("target_agent_count must be positive")

    source_run = (
        db.query(SimulationRun)
        .filter(SimulationRun.run_id == clean_parent_run_id)
        .first()
    )
    if source_run is None:
        raise ValueError("parent_run_id must reference an existing simulation run")

    survivor_numbers, survivor_source = _resolve_survivor_agent_numbers(
        db,
        parent_run_id=clean_parent_run_id,
        snapshot_type=clean_snapshot_type,
    )

    agent_numbers = _as_int_list(
        [row.agent_number for row in db.query(Agent.agent_number).all()]
    )
    available_numbers = sorted(set(agent_numbers))
    if len(available_numbers) < desired_count:
        raise ValueError(
            f"not enough agents in database for target count: have={len(available_numbers)} target={desired_count}"
        )

    carryover_set = sorted(set(survivor_numbers))
    if len(carryover_set) > desired_count:
        raise ValueError(
            f"survivor_count exceeds target_agent_count: survivors={len(carryover_set)} target={desired_count}"
        )

    fresh_needed = desired_count - len(carryover_set)
    fresh_candidates = [n for n in available_numbers if n not in set(carryover_set)]
    if len(fresh_candidates) < fresh_needed:
        raise ValueError(
            f"not enough fresh candidates: required={fresh_needed} available={len(fresh_candidates)}"
        )

    fresh_numbers = fresh_candidates[:fresh_needed]

    lineage_rows: list[dict[str, Any]] = []
    for child_agent_number in carryover_set:
        lineage_rows.append(
            {
                "season_id": clean_season_id,
                "parent_agent_number": int(child_agent_number),
                "child_agent_number": int(child_agent_number),
                "origin": "carryover",
            }
        )
    for child_agent_number in fresh_numbers:
        lineage_rows.append(
            {
                "season_id": clean_season_id,
                "parent_agent_number": None,
                "child_agent_number": int(child_agent_number),
                "origin": "fresh",
            }
        )
    lineage_rows = sorted(
        lineage_rows,
        key=lambda item: int(item.get("child_agent_number") or 0),
    )

    result = {
        "ok": True,
        "dry_run": bool(dry_run),
        "season_id": clean_season_id,
        "parent_run_id": clean_parent_run_id,
        "transfer_policy_version": clean_policy_version,
        "policy_expected_version": TRANSFER_POLICY_VERSION_V1,
        "transfer_policy_matches_default": (clean_policy_version == TRANSFER_POLICY_VERSION_V1),
        "snapshot_source": survivor_source,
        "snapshot_type": clean_snapshot_type,
        "target_agent_count": desired_count,
        "carryover_agent_count": len(carryover_set),
        "fresh_agent_count": len(fresh_numbers),
        "carryover_agent_numbers": carryover_set,
        "fresh_agent_numbers": fresh_numbers,
        "carry_passed_laws": bool(carry_passed_laws),
        "lineage_rows": lineage_rows,
    }

    if dry_run:
        return result

    if not confirm:
        raise ValueError("Refusing destructive seed operation without --confirm")

    now = now_utc()
    carryover_numbers = set(carryover_set)
    fresh_numbers_set = set(fresh_numbers)
    target_numbers = carryover_numbers | fresh_numbers_set

    votes_cleared = db.query(Vote).delete(synchronize_session=False)
    active_proposals = (
        db.query(Proposal)
        .filter(Proposal.status == "active")
        .all()
    )
    for row in active_proposals:
        row.status = "expired"
        row.resolved_at = now
        db.add(row)

    laws_deactivated = 0
    if not carry_passed_laws:
        active_laws = db.query(Law).filter(Law.active.is_(True)).all()
        for row in active_laws:
            row.active = False
            if row.repealed_at is None:
                row.repealed_at = now
            db.add(row)
        laws_deactivated = len(active_laws)

    memory_rows = db.query(AgentMemory).all()
    memory_by_agent_id: dict[int, AgentMemory] = {int(row.agent_id): row for row in memory_rows}

    agents = db.query(Agent).all()
    for agent in agents:
        agent_number = int(agent.agent_number)
        if agent_number not in target_numbers:
            continue

        agent.status = "active"
        agent.starvation_cycles = 0
        agent.died_at = None
        agent.death_cause = None
        agent.sanctioned_until = None
        agent.exiled = False
        agent.current_intent = {}
        agent.intent_expires_at = None
        agent.last_checkpoint_at = None
        agent.next_checkpoint_at = None
        agent.last_active_at = now

        agent.display_name = immutable_alias_for_agent_number(agent_number)

        if agent_number in fresh_numbers_set:
            memory = memory_by_agent_id.get(int(agent.id))
            if memory is None:
                memory = AgentMemory(
                    agent_id=int(agent.id),
                    summary_text="",
                    last_checkpoint_number=0,
                    last_updated_at=now,
                )
            else:
                memory.summary_text = ""
                memory.last_checkpoint_number = 0
                memory.last_updated_at = now
            db.add(memory)
        else:
            memory = memory_by_agent_id.get(int(agent.id))
            if memory is None:
                db.add(
                    AgentMemory(
                        agent_id=int(agent.id),
                        summary_text="",
                        last_checkpoint_number=0,
                        last_updated_at=now,
                    )
                )

        _normalize_agent_inventory(db, agent_id=int(agent.id))
        db.add(agent)

    lineage_deleted = (
        db.query(AgentLineage)
        .filter(AgentLineage.season_id == clean_season_id)
        .delete(synchronize_session=False)
    )
    for payload in lineage_rows:
        db.add(
            AgentLineage(
                season_id=clean_season_id,
                parent_agent_number=payload.get("parent_agent_number"),
                child_agent_number=int(payload.get("child_agent_number") or 0),
                origin=str(payload.get("origin") or "fresh"),
            )
        )

    db.commit()

    result.update(
        {
            "dry_run": False,
            "votes_cleared": int(votes_cleared or 0),
            "active_proposals_expired": len(active_proposals),
            "laws_deactivated": int(laws_deactivated),
            "lineage_rows_replaced": int(lineage_deleted or 0),
        }
    )
    return result
