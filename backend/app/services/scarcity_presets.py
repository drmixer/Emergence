"""Named scarcity presets for internal tuning and repeatable canaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScarcityPreset:
    name: str
    description: str
    runtime_overrides: dict[str, Any]
    agent_resource_targets: dict[str, float]
    common_pool_targets: dict[str, float]
    recommended_run_class: str = "standard_72h"


SCARCITY_PRESETS: dict[str, ScarcityPreset] = {
    "standard_reset_v2": ScarcityPreset(
        name="standard_reset_v2",
        description=(
            "Restore the standard world baseline while keeping dormant auto-revival disabled "
            "so reserve aid does not erase dormancy consequences."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 2.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 2.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.25,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.25,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": True,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
        },
        agent_resource_targets={
            "food": 50.0,
            "energy": 50.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 2000.0,
            "energy": 1000.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v1": ScarcityPreset(
        name="internal_scarcity_tight_v1",
        description=(
            "Tighter internal scarcity canary with higher upkeep, lower starting stocks, and "
            "no automatic reserve revival."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.5,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
        },
        agent_resource_targets={
            "food": 35.0,
            "energy": 30.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 1000.0,
            "energy": 500.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v2": ScarcityPreset(
        name="internal_scarcity_tight_v2",
        description=(
            "Sharper energy-first tuning canary with steeper active upkeep, weaker dormant "
            "energy buffering, lower starting inventories, and no automatic reserve revival."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 30.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 800.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v3": ScarcityPreset(
        name="internal_scarcity_tight_v3",
        description=(
            "Broader multi-resource tuning canary that preserves the energy-consequence gains from "
            "v2 while tightening food availability and keeping reserve auto-support disabled."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.6,
            "WORK_YIELD_GENERATE_BASE": 1.5,
            "WORK_YIELD_GATHER_BASE": 0.5,
        },
        agent_resource_targets={
            "food": 24.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 550.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v4": ScarcityPreset(
        name="internal_scarcity_tight_v4",
        description=(
            "Mixed-scarcity tuning canary that keeps the restored dormancy consequences from patch1 "
            "while making food meaningfully tighter instead of relying on an energy-only bottleneck."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.2,
            "WORK_YIELD_GENERATE_BASE": 1.5,
            "WORK_YIELD_GATHER_BASE": 0.5,
        },
        agent_resource_targets={
            "food": 18.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 350.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v5": ScarcityPreset(
        name="internal_scarcity_tight_v5",
        description=(
            "Aggressive mixed-scarcity tuning canary that suppresses exogenous relief, sharply "
            "cuts food throughput, and lowers both agent and common-pool food buffers."
        ),
        runtime_overrides={
            "SURVIVAL_ACTIVE_FOOD_COST": 4.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.75,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 0.8,
            "WORK_YIELD_GENERATE_BASE": 1.5,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 12.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 150.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
    "internal_scarcity_tight_v6": ScarcityPreset(
        name="internal_scarcity_tight_v6",
        description=(
            "Food-first follow-up canary that keeps the corrected dormancy semantics from v5 "
            "while tightening food upkeep and farm throughput further without changing death semantics."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            "SURVIVAL_ACTIVE_FOOD_COST": 5.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 1.0,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 0.6,
            "WORK_YIELD_GENERATE_BASE": 1.5,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 10.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 100.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
    "internal_canary_b_legibility_v1": ScarcityPreset(
        name="internal_canary_b_legibility_v1",
        description=(
            "Canary B preset for the legibility diagnosis. Keeps the Canary A baseline intact "
            "except for a modest food-side relaxation intended to preserve an interpretable "
            "population through the first 4 hours."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            "SURVIVAL_ACTIVE_FOOD_COST": 4.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 4.0,
            "SURVIVAL_DORMANT_FOOD_COST": 0.75,
            "SURVIVAL_DORMANT_ENERGY_COST": 1.0,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.0,
            "WORK_YIELD_GENERATE_BASE": 1.5,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 16.0,
            "energy": 18.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 250.0,
            "energy": 200.0,
            "materials": 500.0,
        },
    ),
}


def get_scarcity_preset(name: str) -> ScarcityPreset:
    key = str(name or "").strip()
    try:
        return SCARCITY_PRESETS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(SCARCITY_PRESETS))
        raise KeyError(f"Unknown scarcity preset `{key}`. Choices: {choices}") from exc


def list_scarcity_presets() -> list[ScarcityPreset]:
    return [SCARCITY_PRESETS[key] for key in sorted(SCARCITY_PRESETS)]
