from app.services.scarcity_presets import get_scarcity_preset, list_scarcity_presets


def test_internal_scarcity_tight_preset_matches_tuning_plan():
    preset = get_scarcity_preset("internal_scarcity_tight_v1")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.agent_resource_targets == {"food": 35.0, "energy": 30.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 1000.0, "energy": 500.0, "materials": 500.0}


def test_internal_scarcity_tight_v2_preset_matches_energy_first_plan():
    preset = get_scarcity_preset("internal_scarcity_tight_v2")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 1.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 30.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 800.0, "energy": 200.0, "materials": 500.0}


def test_internal_scarcity_tight_v3_preset_broadens_food_pressure():
    preset = get_scarcity_preset("internal_scarcity_tight_v3")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.6
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.5
    assert preset.agent_resource_targets == {"food": 24.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 550.0, "energy": 200.0, "materials": 500.0}


def test_internal_scarcity_tight_v4_preset_shifts_to_mixed_scarcity():
    preset = get_scarcity_preset("internal_scarcity_tight_v4")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.2
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.5
    assert preset.agent_resource_targets == {"food": 18.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 350.0, "energy": 200.0, "materials": 500.0}


def test_standard_reset_preset_restores_named_baseline():
    preset = get_scarcity_preset("standard_reset_v2")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.agent_resource_targets["food"] == 50.0
    assert preset.common_pool_targets["energy"] == 1000.0


def test_list_scarcity_presets_is_sorted_and_complete():
    names = [preset.name for preset in list_scarcity_presets()]

    assert names == [
        "internal_scarcity_tight_v1",
        "internal_scarcity_tight_v2",
        "internal_scarcity_tight_v3",
        "internal_scarcity_tight_v4",
        "standard_reset_v2",
    ]
