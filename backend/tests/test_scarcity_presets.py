from app.services.scarcity_presets import get_scarcity_preset, list_scarcity_presets


def test_internal_scarcity_tight_preset_matches_tuning_plan():
    preset = get_scarcity_preset("internal_scarcity_tight_v1")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
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
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 30.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 800.0, "energy": 200.0, "materials": 500.0}


def test_internal_scarcity_tight_v3_preset_broadens_food_pressure():
    preset = get_scarcity_preset("internal_scarcity_tight_v3")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
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
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.2
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.5
    assert preset.agent_resource_targets == {"food": 18.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 350.0, "energy": 200.0, "materials": 500.0}


def test_internal_scarcity_tight_v5_preset_is_a_real_step_change():
    preset = get_scarcity_preset("internal_scarcity_tight_v5")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 1.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 0.8
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 12.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 150.0, "energy": 200.0, "materials": 500.0}


def test_internal_scarcity_tight_v6_preset_tightens_food_without_changing_death_semantics():
    preset = get_scarcity_preset("internal_scarcity_tight_v6")

    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 5.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 1.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 1.0
    assert preset.runtime_overrides["SURVIVAL_DEATH_THRESHOLD"] == 5
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 0.6
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.5
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 10.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 100.0, "energy": 200.0, "materials": 500.0}


def test_internal_canary_b_legibility_preset_relaxes_food_side_for_observation_window():
    preset = get_scarcity_preset("internal_canary_b_legibility_v1")

    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
    assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 4.0
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 1.0
    assert preset.runtime_overrides["SURVIVAL_DEATH_THRESHOLD"] == 5
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.0
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.5
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 16.0, "energy": 18.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 250.0, "energy": 200.0, "materials": 500.0}


def test_internal_canary_c_survival_window_preset_adds_active_headroom_without_restoring_reserve_support():
    preset = get_scarcity_preset("internal_canary_c_survival_window_v1")

    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
    assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is False
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.4
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.75
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 22.0, "energy": 24.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 450.0, "energy": 300.0, "materials": 500.0}


def test_standard_reset_preset_restores_named_baseline():
    preset = get_scarcity_preset("standard_reset_v2")

    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides.get("SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED", True) is True
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.agent_resource_targets["food"] == 50.0
    assert preset.common_pool_targets["energy"] == 1000.0


def test_all_internal_tuning_presets_use_shorter_proposal_timing():
    for preset in list_scarcity_presets():
        if not preset.name.startswith("internal_"):
            continue
        assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
        assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60


def test_list_scarcity_presets_is_sorted_and_complete():
    names = [preset.name for preset in list_scarcity_presets()]

    assert names == [
        "internal_canary_b_legibility_v1",
        "internal_canary_c_survival_window_v1",
        "internal_scarcity_tight_v1",
        "internal_scarcity_tight_v2",
        "internal_scarcity_tight_v3",
        "internal_scarcity_tight_v4",
        "internal_scarcity_tight_v5",
        "internal_scarcity_tight_v6",
        "standard_reset_v2",
    ]
