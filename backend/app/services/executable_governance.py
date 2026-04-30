"""Bounded executable governance templates.

This module intentionally executes only structured runtime effects. Natural
language legal text remains evidence of agent intent, not executable code.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import ensure_utc
from app.models.models import Agent, AgentInventory, Event, GlobalResources, Law, Proposal, Transaction
from app.services.live_run_scope import get_live_run_window
from app.services.runtime_config import runtime_config_service


GOVERNANCE_CLASSES = {
    "resolution",
    "standing_law",
    "allocation",
    "amendment",
    "emergency_action",
    "advisory_law",
}
LAW_CLASSES = {"standing_law", "advisory_law", "amendment", "emergency_action"}

EFFECT_COMMON_POOL_ALLOCATION = "common_pool_allocation"
EFFECT_ACTIVE_RESERVE_AID = "active_reserve_aid"
SUPPORTED_RUNTIME_EFFECTS = {EFFECT_COMMON_POOL_ALLOCATION, EFFECT_ACTIVE_RESERVE_AID}

RESOURCE_TYPES = {"food", "energy", "materials"}


def normalize_governance_class(proposal_type: str | None, governance_class: str | None, runtime_effect: Any = None) -> str:
    supplied = str(governance_class or "").strip().lower()
    if supplied in GOVERNANCE_CLASSES:
        return supplied

    effect_type = _effect_type(runtime_effect)
    ptype = str(proposal_type or "").strip().lower()
    if ptype == "standing_law":
        return "standing_law"
    if ptype == "allocation":
        return "allocation"
    if ptype == "rule" or ptype == "resolution":
        return "resolution"
    if ptype == "constitutional" or ptype == "amendment":
        return "amendment"
    if ptype == "emergency_action":
        return "emergency_action"
    if ptype == "law" and effect_type == EFFECT_ACTIVE_RESERVE_AID:
        return "standing_law"
    if ptype == "law":
        return "advisory_law"
    return "resolution"


def law_class_for_proposal(proposal: Proposal) -> str:
    governance_class = normalize_governance_class(
        proposal.proposal_type,
        proposal.governance_class,
        proposal.runtime_effect,
    )
    if governance_class in {"standing_law", "amendment", "emergency_action"}:
        return governance_class
    return "advisory_law"


def normalize_runtime_effect(raw_effect: Any, *, governance_class: str, db: Session | None = None) -> tuple[dict[str, Any], list[str]]:
    """Return a sanitized effect and validation errors."""
    if raw_effect in (None, "", {}):
        return {}, []
    if not isinstance(raw_effect, dict):
        return {}, ["runtime_effect must be an object"]

    effect_type = _effect_type(raw_effect)
    if effect_type not in SUPPORTED_RUNTIME_EFFECTS:
        return {}, ["runtime_effect.type must be common_pool_allocation or active_reserve_aid"]

    if effect_type == EFFECT_COMMON_POOL_ALLOCATION:
        return _normalize_common_pool_allocation(raw_effect, governance_class=governance_class, db=db)
    if effect_type == EFFECT_ACTIVE_RESERVE_AID:
        return _normalize_active_reserve_aid(raw_effect, governance_class=governance_class)
    return {}, ["unsupported runtime_effect.type"]


def governance_payload_for_proposal(proposal: Proposal) -> dict[str, Any]:
    governance_class = normalize_governance_class(
        proposal.proposal_type,
        proposal.governance_class,
        proposal.runtime_effect,
    )
    effect = proposal.runtime_effect if isinstance(proposal.runtime_effect, dict) else {}
    return _governance_payload(governance_class=governance_class, runtime_effect=effect)


def governance_payload_for_law(law: Law) -> dict[str, Any]:
    law_class = str(law.law_class or "").strip().lower() or "advisory_law"
    effect = law.runtime_effect if isinstance(law.runtime_effect, dict) else {}
    return _governance_payload(governance_class=law_class, runtime_effect=effect)


def active_executable_active_aid_laws(db: Session) -> list[Law]:
    run_window = get_live_run_window(db)
    if run_window.run_id is None:
        return []

    query = db.query(Law).filter(Law.active.is_(True), Law.runtime_effect.isnot(None))
    if run_window.started_at is not None:
        query = query.filter(Law.passed_at >= run_window.started_at)
    if run_window.ended_at is not None:
        query = query.filter(Law.passed_at <= run_window.ended_at)

    laws: list[Law] = []
    for law in query.order_by(Law.passed_at.asc(), Law.id.asc()).all():
        if _effect_type(law.runtime_effect) != EFFECT_ACTIVE_RESERVE_AID:
            continue
        if str(law.law_class or "").strip().lower() not in {"standing_law", "emergency_action"}:
            continue
        laws.append(law)
    return laws


def execute_allocation_effect_for_passed_proposal(db: Session, proposal: Proposal) -> dict[str, Any] | None:
    effect = proposal.runtime_effect if isinstance(proposal.runtime_effect, dict) else {}
    if _effect_type(effect) != EFFECT_COMMON_POOL_ALLOCATION:
        return None

    governance_class = normalize_governance_class(
        proposal.proposal_type,
        proposal.governance_class,
        effect,
    )
    if governance_class not in {"allocation", "emergency_action"}:
        return _log_governance_execution(
            db,
            agent_id=proposal.author_agent_id,
            proposal=proposal,
            law=None,
            effect=effect,
            status="skipped",
            block_reason="common_pool_allocation requires allocation or emergency_action governance_class",
            transfers=[],
        )

    transfers = list(effect.get("transfers") or [])
    min_pool_remaining = Decimal(str(effect.get("min_pool_remaining") or "0"))
    executed: list[dict[str, Any]] = []
    block_reasons: list[str] = []

    pools = {
        str(row.resource_type): row
        for row in db.query(GlobalResources).filter(GlobalResources.resource_type.in_(RESOURCE_TYPES)).all()
    }

    for transfer in transfers:
        recipient_number = int(transfer.get("recipient_agent_id") or 0)
        resource_type = str(transfer.get("resource_type") or "").strip().lower()
        amount = Decimal(str(transfer.get("amount") or "0")).quantize(Decimal("0.01"))
        recipient = db.query(Agent).filter(Agent.agent_number == recipient_number).first()
        pool = pools.get(resource_type)
        if recipient is None:
            block_reasons.append(f"recipient Agent #{recipient_number} not found")
            continue
        if recipient.status == "dead":
            block_reasons.append(f"recipient Agent #{recipient_number} is dead")
            continue
        if pool is None:
            block_reasons.append(f"common pool has no {resource_type} row")
            continue
        available = Decimal(str(pool.in_common_pool or 0))
        if available - amount < min_pool_remaining:
            block_reasons.append(
                f"{resource_type} pool floor would be violated for Agent #{recipient_number}"
            )
            continue

        inventory = (
            db.query(AgentInventory)
            .filter(
                AgentInventory.agent_id == recipient.id,
                AgentInventory.resource_type == resource_type,
            )
            .first()
        )
        if inventory is None:
            inventory = AgentInventory(agent_id=recipient.id, resource_type=resource_type, quantity=Decimal("0"))
            db.add(inventory)
        before = Decimal(str(inventory.quantity or 0))
        pool_before = Decimal(str(pool.in_common_pool or 0))
        inventory.quantity += amount
        pool.in_common_pool -= amount
        db.add(
            Transaction(
                to_agent_id=recipient.id,
                resource_type=resource_type,
                amount=amount,
                transaction_type="allocation",
            )
        )
        executed.append(
            {
                "recipient_agent_id": int(recipient.id),
                "recipient_agent_number": int(recipient.agent_number),
                "resource_type": resource_type,
                "amount": float(amount),
                "recipient_quantity_before": float(before),
                "recipient_quantity_after": float(inventory.quantity or 0),
                "pool_before": float(pool_before),
                "pool_after": float(pool.in_common_pool or 0),
            }
        )

    status = "executed" if executed and not block_reasons else "partial" if executed else "skipped"
    return _log_governance_execution(
        db,
        agent_id=proposal.author_agent_id,
        proposal=proposal,
        law=None,
        effect=effect,
        status=status,
        block_reason="; ".join(block_reasons),
        transfers=executed,
    )


def runtime_effect_label(runtime_effect: Any) -> str:
    effect_type = _effect_type(runtime_effect)
    if effect_type == EFFECT_COMMON_POOL_ALLOCATION:
        return "Allocation: one-time transfer"
    if effect_type == EFFECT_ACTIVE_RESERVE_AID:
        return "Standing Law: executable"
    return "Advisory only: unsupported effect"


def _effect_type(raw_effect: Any) -> str:
    if not isinstance(raw_effect, dict):
        return ""
    return str(raw_effect.get("type") or raw_effect.get("effect_type") or "").strip().lower()


def _normalize_common_pool_allocation(
    raw_effect: dict[str, Any],
    *,
    governance_class: str,
    db: Session | None,
) -> tuple[dict[str, Any], list[str]]:
    if governance_class not in {"allocation", "emergency_action"}:
        return {}, ["common_pool_allocation requires governance_class allocation or emergency_action"]

    raw_transfers = raw_effect.get("transfers")
    if not isinstance(raw_transfers, list) or not raw_transfers:
        return {}, ["common_pool_allocation requires a non-empty transfers list"]
    if len(raw_transfers) > 10:
        return {}, ["common_pool_allocation supports at most 10 transfers"]

    errors: list[str] = []
    transfers: list[dict[str, Any]] = []
    for index, raw_transfer in enumerate(raw_transfers, start=1):
        if not isinstance(raw_transfer, dict):
            errors.append(f"transfer {index} must be an object")
            continue
        try:
            recipient_number = int(raw_transfer.get("recipient_agent_id") or 0)
        except (TypeError, ValueError):
            recipient_number = 0
        resource_type = str(raw_transfer.get("resource_type") or "").strip().lower()
        try:
            amount = Decimal(str(raw_transfer.get("amount") or "0")).quantize(Decimal("0.01"))
        except Exception:
            amount = Decimal("0")
        if recipient_number <= 0:
            errors.append(f"transfer {index} requires recipient_agent_id")
        elif db is not None:
            recipient = db.query(Agent).filter(Agent.agent_number == recipient_number).first()
            if recipient is None:
                errors.append(f"transfer {index} recipient Agent #{recipient_number} not found")
            elif recipient.status == "dead":
                errors.append(f"transfer {index} recipient Agent #{recipient_number} is dead")
        if resource_type not in RESOURCE_TYPES:
            errors.append(f"transfer {index} resource_type must be food|energy|materials")
        if amount <= 0 or amount > Decimal("1000"):
            errors.append(f"transfer {index} amount must be > 0 and <= 1000")
        transfers.append(
            {
                "recipient_agent_id": recipient_number,
                "resource_type": resource_type,
                "amount": float(amount),
            }
        )

    try:
        min_pool_remaining = Decimal(str(raw_effect.get("min_pool_remaining") or "0")).quantize(Decimal("0.01"))
    except Exception:
        min_pool_remaining = Decimal("0")
    if min_pool_remaining < 0:
        errors.append("min_pool_remaining must be >= 0")
    if errors:
        return {}, errors
    return {
        "type": EFFECT_COMMON_POOL_ALLOCATION,
        "description": "One-time transfer from the common pool after passage if validation succeeds.",
        "transfers": transfers,
        "min_pool_remaining": float(min_pool_remaining),
        "reactivate_dormant": bool(raw_effect.get("reactivate_dormant", False)),
    }, []


def _normalize_active_reserve_aid(
    raw_effect: dict[str, Any],
    *,
    governance_class: str,
) -> tuple[dict[str, Any], list[str]]:
    if governance_class not in {"standing_law", "emergency_action"}:
        return {}, ["active_reserve_aid requires governance_class standing_law or emergency_action"]

    errors: list[str] = []

    def _positive_decimal(name: str, default: str) -> Decimal:
        try:
            value = Decimal(str(raw_effect.get(name, default))).quantize(Decimal("0.01"))
        except Exception:
            errors.append(f"{name} must be numeric")
            return Decimal(default)
        if value < 0:
            errors.append(f"{name} must be >= 0")
        if value > Decimal("1000"):
            errors.append(f"{name} must be <= 1000")
        return value

    trigger_food = _positive_decimal("trigger_food_below", "2.00")
    trigger_energy = _positive_decimal("trigger_energy_below", "2.00")
    target_food = _positive_decimal("target_food", "3.00")
    target_energy = _positive_decimal("target_energy", "3.00")
    min_pool_remaining = _positive_decimal("min_pool_remaining", "25.00")
    if errors:
        return {}, errors
    return {
        "type": EFFECT_ACTIVE_RESERVE_AID,
        "description": "Recurring active-agent common-pool aid when an active agent is below declared thresholds.",
        "trigger_food_below": float(trigger_food),
        "trigger_energy_below": float(trigger_energy),
        "target_food": float(target_food),
        "target_energy": float(target_energy),
        "min_pool_remaining": float(min_pool_remaining),
        "recipient_status": "active_only",
        "revival": "disabled",
    }, []


def _governance_payload(*, governance_class: str, runtime_effect: dict[str, Any]) -> dict[str, Any]:
    executable = _effect_type(runtime_effect) in SUPPORTED_RUNTIME_EFFECTS
    labels_by_class = {
        "resolution": "Resolution: non-binding",
        "standing_law": "Standing Law: executable" if executable else "Standing Law: no supported effect",
        "allocation": "Allocation: one-time transfer" if executable else "Allocation: unsupported effect",
        "amendment": "Amendment",
        "emergency_action": "Emergency Action",
        "advisory_law": "Advisory only: unsupported effect",
    }
    return {
        "governance_class": governance_class,
        "class_label": labels_by_class.get(governance_class, "Resolution: non-binding"),
        "executable": executable,
        "execution_label": "Executable: active" if executable else "Advisory only: unsupported effect",
        "runtime_effect": runtime_effect,
        "runtime_effect_label": runtime_effect_label(runtime_effect),
    }


def _log_governance_execution(
    db: Session,
    *,
    agent_id: int | None,
    proposal: Proposal | None,
    law: Law | None,
    effect: dict[str, Any],
    status: str,
    block_reason: str,
    transfers: list[dict[str, Any]],
) -> dict[str, Any]:
    target = proposal or law
    title = str(getattr(target, "title", "") or "Governance effect")
    metadata = _with_runtime_metadata({
        "proposal_id": int(proposal.id) if proposal and proposal.id is not None else None,
        "law_id": int(law.id) if law and law.id is not None else None,
        "runtime_effect": effect,
        "execution_status": status,
        "block_reason": block_reason or None,
        "transfers": transfers,
    })
    event = Event(
        agent_id=agent_id,
        event_type="governance_execution",
        description=f"Governance execution {status}: {title}",
        event_metadata=metadata,
    )
    db.add(event)
    db.flush()
    return {
        "event_id": int(event.id),
        "status": status,
        "block_reason": block_reason or None,
        "transfers": transfers,
    }


def _with_runtime_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    payload = dict(metadata or {})
    runtime = payload.get("runtime")
    runtime_payload = dict(runtime) if isinstance(runtime, dict) else {}
    run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip()
    run_mode = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_MODE") or "").strip()
    if run_id:
        runtime_payload["run_id"] = run_id[:64]
    if run_mode:
        runtime_payload["run_mode"] = run_mode
    if runtime_payload:
        payload["runtime"] = runtime_payload
    return payload
