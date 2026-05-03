"""Named scarcity presets for internal tuning and repeatable canaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CANARY_TUNING_RUNTIME_OVERRIDES = {
    "PROPOSAL_VOTING_HOURS": 2.0,
    "PROPOSAL_RESOLUTION_INTERVAL_SECONDS": 60,
}


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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
            **CANARY_TUNING_RUNTIME_OVERRIDES,
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
    "internal_canary_c_survival_window_v1": ScarcityPreset(
        name="internal_canary_c_survival_window_v1",
        description=(
            "Survival-window calibration canary for hour-scale runs. Preserves the Canary B "
            "legibility surfaces and reserve semantics, but adds enough additional food/energy "
            "headroom to keep agents active long enough for social behavior to be observable."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
    ),
    "internal_canary_d_revival_window_v1": ScarcityPreset(
        name="internal_canary_d_revival_window_v1",
        description=(
            "Recovery-width canary layered on top of Canary C. Keeps the same survival-economics "
            "baseline, but re-enables reserve auto-contribution and reserve auto-revive so "
            "dormancy recovery is no longer trade-or-nothing."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": True,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
    ),
    "internal_canary_e_response_loop_v1": ScarcityPreset(
        name="internal_canary_e_response_loop_v1",
        description=(
            "Response-loop canary layered on top of Canary D. Keeps the same survival and recovery "
            "baseline, but is intended for checkpoint-timing and context-legibility changes that "
            "should increase bilateral responses without moving the economics."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": True,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
    ),
    "internal_canary_k_bounded_contribution_v1": ScarcityPreset(
        name="internal_canary_k_bounded_contribution_v1",
        description=(
            "Canary K preset for testing whether contribution laws with bounded mechanical teeth "
            "change the J failure mode. Keeps the Canary C/J survival window and disabled reserve "
            "aid/revival mechanics, but enables automatic reserve contribution once a survival "
            "reserve law is active."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": False,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
        recommended_run_class="special_exploratory",
    ),
    "internal_canary_k3_paired_active_aid_v1": ScarcityPreset(
        name="internal_canary_k3_paired_active_aid_v1",
        description=(
            "Canary K3 preset for the paired-mechanism follow-up to K2. Keeps contribution gated "
            "by current-run reserve laws, enables narrow active-agent reserve aid below explicit "
            "food/energy thresholds, and leaves dormant maintenance and auto-revival disabled."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 25.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": True,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
        recommended_run_class="special_exploratory",
    ),
    "internal_canary_k6_pressure_restoration_v1": ScarcityPreset(
        name="internal_canary_k6_pressure_restoration_v1",
        description=(
            "Canary K6 pressure-restoration diagnostic. Matches the K3/K5 active-aid survival "
            "window but disables automatic reserve contribution so active aid draws down the "
            "existing pool instead of being cushioned by automatic work diversion."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 25.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 300.0,
            "materials": 500.0,
        },
        recommended_run_class="special_exploratory",
    ),
    "internal_canary_k7_finite_reserve_energy_v1": ScarcityPreset(
        name="internal_canary_k7_finite_reserve_energy_v1",
        description=(
            "Canary K7 finite-reserve diagnostic. Matches K6 exactly except for a lower starting "
            "common-pool energy target, testing whether active aid plus a smaller finite energy "
            "reserve forces prioritization, bilateral aid, shortfalls, or dormancy."
        ),
        runtime_overrides={
            "AGENT_LOOP_DELAY_SECONDS": 180,
            **CANARY_TUNING_RUNTIME_OVERRIDES,
            "SURVIVAL_ACTIVE_FOOD_COST": 3.0,
            "SURVIVAL_ACTIVE_ENERGY_COST": 3.5,
            "SURVIVAL_DORMANT_FOOD_COST": 0.5,
            "SURVIVAL_DORMANT_ENERGY_COST": 0.75,
            "SURVIVAL_DEATH_THRESHOLD": 5,
            "SURVIVAL_RESERVE_ACTIVE_AID_ENABLED": True,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY": 2.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY": 3.0,
            "SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING": 25.0,
            "SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
            "SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED": False,
            "WORK_YIELD_FARM_BASE": 1.4,
            "WORK_YIELD_GENERATE_BASE": 1.75,
            "WORK_YIELD_GATHER_BASE": 0.5,
            "WORLD_EVENT_GENERATION_ENABLED": False,
        },
        agent_resource_targets={
            "food": 22.0,
            "energy": 24.0,
            "materials": 20.0,
        },
        common_pool_targets={
            "food": 450.0,
            "energy": 150.0,
            "materials": 500.0,
        },
        recommended_run_class="special_exploratory",
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
