"""Viewer/report labels for reserve policy intent versus runtime mechanics."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Law
from app.services.law_effects import active_survival_reserve_laws, is_survival_reserve_law
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    reserve_active_aid_min_pool_remaining,
    reserve_active_aid_target_energy,
    reserve_active_aid_target_food,
    reserve_active_aid_enabled,
    reserve_active_aid_trigger_energy,
    reserve_active_aid_trigger_food,
    reserve_auto_contribution_enabled,
    reserve_auto_revive_enabled,
    reserve_dormant_maintenance_enabled,
)


RESERVE_GATE_LABELS = {
    "auto_contribution": "Auto contribution",
    "active_aid": "Active-agent aid",
    "dormant_maintenance": "Dormant maintenance",
    "auto_revive": "Auto revive",
}


def reserve_mechanical_access_payload() -> dict[str, Any]:
    """Return current runtime gates without implying any law is active."""
    gates = {
        "auto_contribution": bool(reserve_auto_contribution_enabled()),
        "active_aid": bool(reserve_active_aid_enabled()),
        "dormant_maintenance": bool(reserve_dormant_maintenance_enabled()),
        "auto_revive": bool(reserve_auto_revive_enabled()),
    }
    enabled_modes = [key for key, enabled in gates.items() if enabled]
    disabled_modes = [key for key, enabled in gates.items() if not enabled]
    if enabled_modes:
        label = "Some automatic reserve mechanics are enabled by runtime gates."
    else:
        label = "Automatic reserve mechanics are disabled by runtime gates."
    return {
        **{f"{key}_enabled": enabled for key, enabled in gates.items()},
        "enabled_modes": enabled_modes,
        "disabled_modes": disabled_modes,
        "mode_labels": RESERVE_GATE_LABELS,
        "active_aid_thresholds": {
            "food_trigger_below": float(reserve_active_aid_trigger_food()),
            "energy_trigger_below": float(reserve_active_aid_trigger_energy()),
            "food_target": float(max(reserve_active_aid_target_food(), active_food_cost())),
            "energy_target": float(max(reserve_active_aid_target_energy(), active_energy_cost())),
            "min_pool_remaining": float(reserve_active_aid_min_pool_remaining()),
        },
        "label": label,
        "description": (
            "Runtime gates determine whether reserve law text can trigger automatic contributions, "
            "active-agent aid, dormant maintenance, or auto-revival."
        ),
    }


def reserve_policy_access_payload(db: Session) -> dict[str, Any]:
    """Return active reserve policy state alongside separate mechanical access gates."""
    active_laws = active_survival_reserve_laws(db)
    mechanics = reserve_mechanical_access_payload()
    policy_active = bool(active_laws)
    any_gate_enabled = bool(mechanics.get("enabled_modes"))
    automatic_mechanics_available = policy_active and any_gate_enabled
    automatic_support_available = policy_active and any(
        bool(mechanics.get(f"{mode}_enabled"))
        for mode in ("active_aid", "dormant_maintenance", "auto_revive")
    )
    if automatic_mechanics_available:
        status = "policy_and_mechanical_access"
        access_label = "Reserve policy has at least one automatic runtime path."
    elif policy_active:
        status = "policy_only"
        access_label = "Reserve policy is active, but automatic runtime paths are gated off."
    elif any_gate_enabled:
        status = "mechanical_gates_without_policy"
        access_label = "Reserve gates exist, but no active reserve policy is currently in force."
    else:
        status = "no_policy_or_mechanical_access"
        access_label = "No active reserve policy and no automatic reserve runtime path."

    return {
        "status": status,
        "policy_intent": {
            "reserve_law_active": policy_active,
            "reserve_law_count": len(active_laws),
            "active_law_ids": [int(law.id) for law in active_laws],
            "label": "Active reserve policy intent" if policy_active else "No active reserve policy intent",
            "description": (
                "Reserve laws express agent-approved policy intent; they do not by themselves prove "
                "automatic reserve access is mechanically available."
            ),
        },
        "mechanical_access": {
            **mechanics,
            "automatic_mechanics_available": automatic_mechanics_available,
            "automatic_support_available": automatic_support_available,
            "label": access_label,
        },
    }


def reserve_law_semantics_payload(law: Law) -> dict[str, Any] | None:
    """Return per-law reserve labels for viewer surfaces."""
    if not is_survival_reserve_law(law):
        return None
    mechanics = reserve_mechanical_access_payload()
    active = bool(law.active)
    any_gate_enabled = bool(mechanics.get("enabled_modes"))
    automatic_mechanics_available = active and any_gate_enabled
    automatic_support_available = active and any(
        bool(mechanics.get(f"{mode}_enabled"))
        for mode in ("active_aid", "dormant_maintenance", "auto_revive")
    )
    return {
        "kind": "survival_reserve",
        "policy_intent_label": (
            "Active reserve policy intent" if active else "Historical reserve policy intent"
        ),
        "mechanical_access_label": (
            "Automatic reserve runtime path exists"
            if automatic_mechanics_available
            else "Automatic reserve runtime path is not currently reachable from this law alone"
        ),
        "mechanical_access": mechanics,
        "automatic_mechanics_available": automatic_mechanics_available,
        "automatic_support_available": automatic_support_available,
        "description": (
            "This label separates the law's policy intent from runtime gates for automatic reserve "
            "contribution, active aid, dormant maintenance, and auto-revival."
        ),
    }
