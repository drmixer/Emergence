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
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
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
            "SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED": False,
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
