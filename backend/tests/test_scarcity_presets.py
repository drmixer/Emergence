from app.services.scarcity_presets import get_scarcity_preset, list_scarcity_presets


def test_internal_scarcity_tight_preset_matches_tuning_plan():
    preset = get_scarcity_preset("internal_scarcity_tight_v1")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 35.0, "energy": 30.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 1000.0, "energy": 500.0, "materials": 500.0}


def test_standard_reset_preset_restores_named_baseline():
    preset = get_scarcity_preset("standard_reset_v2")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.agent_resource_targets["food"] == 50.0
    assert preset.common_pool_targets["energy"] == 1000.0


def test_list_scarcity_presets_is_sorted_and_complete():
    names = [preset.name for preset in list_scarcity_presets()]

    assert names == ["internal_scarcity_tight_v1", "standard_reset_v2"]
