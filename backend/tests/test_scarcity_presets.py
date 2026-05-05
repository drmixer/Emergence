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


def test_internal_canary_d_revival_window_preset_only_reopens_reserve_reentry_path():
    preset = get_scarcity_preset("internal_canary_d_revival_window_v1")

    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
    assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is True
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.4
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.75
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 22.0, "energy": 24.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 450.0, "energy": 300.0, "materials": 500.0}


def test_internal_canary_e_response_loop_preset_matches_canary_d_economics_for_clean_attribution():
    preset = get_scarcity_preset("internal_canary_e_response_loop_v1")

    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
    assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is True
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.4
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.75
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 22.0, "energy": 24.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 450.0, "energy": 300.0, "materials": 500.0}


def test_internal_canary_k_bounded_contribution_keeps_j_survival_window_with_auto_contrib():
    preset = get_scarcity_preset("internal_canary_k_bounded_contribution_v1")

    assert preset.recommended_run_class == "special_exploratory"
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
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.runtime_overrides["WORK_YIELD_FARM_BASE"] == 1.4
    assert preset.runtime_overrides["WORK_YIELD_GENERATE_BASE"] == 1.75
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 22.0, "energy": 24.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 450.0, "energy": 300.0, "materials": 500.0}


def test_internal_canary_k3_paired_active_aid_enables_only_threshold_support():
    preset = get_scarcity_preset("internal_canary_k3_paired_active_aid_v1")

    assert preset.recommended_run_class == "special_exploratory"
    assert preset.runtime_overrides["AGENT_LOOP_DELAY_SECONDS"] == 180
    assert preset.runtime_overrides["PROPOSAL_VOTING_HOURS"] == 2.0
    assert preset.runtime_overrides["PROPOSAL_RESOLUTION_INTERVAL_SECONDS"] == 60
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_FOOD_COST"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_ACTIVE_ENERGY_COST"] == 3.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_FOOD_COST"] == 0.5
    assert preset.runtime_overrides["SURVIVAL_DORMANT_ENERGY_COST"] == 0.75
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_ENABLED"] is True
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_FOOD"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_TRIGGER_ENERGY"] == 2.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_TARGET_FOOD"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_TARGET_ENERGY"] == 3.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING"] == 25.0
    assert preset.runtime_overrides["SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED"] is False
    assert preset.runtime_overrides["SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED"] is True
    assert preset.runtime_overrides["WORLD_EVENT_GENERATION_ENABLED"] is False
    assert preset.agent_resource_targets == {"food": 22.0, "energy": 24.0, "materials": 20.0}
    assert preset.common_pool_targets == {"food": 450.0, "energy": 300.0, "materials": 500.0}


def test_internal_canary_k6_pressure_restoration_only_disables_auto_contribution():
    k3 = get_scarcity_preset("internal_canary_k3_paired_active_aid_v1")
    preset = get_scarcity_preset("internal_canary_k6_pressure_restoration_v1")

    assert preset.recommended_run_class == "special_exploratory"
    assert preset.agent_resource_targets == k3.agent_resource_targets
    assert preset.common_pool_targets == k3.common_pool_targets

    k3_overrides = dict(k3.runtime_overrides)
    k6_overrides = dict(preset.runtime_overrides)
    assert k3_overrides.pop("SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED") is True
    assert k6_overrides.pop("SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED") is False
    assert k6_overrides == k3_overrides


def test_internal_canary_k7_only_lowers_initial_common_pool_energy():
    k6 = get_scarcity_preset("internal_canary_k6_pressure_restoration_v1")
    preset = get_scarcity_preset("internal_canary_k7_finite_reserve_energy_v1")

    assert preset.recommended_run_class == "special_exploratory"
    assert preset.runtime_overrides == k6.runtime_overrides
    assert preset.agent_resource_targets == k6.agent_resource_targets

    k6_pool = dict(k6.common_pool_targets)
    k7_pool = dict(preset.common_pool_targets)
    assert k6_pool.pop("energy") == 300.0
    assert k7_pool.pop("energy") == 150.0
    assert k7_pool == k6_pool


def test_internal_canary_k9_only_raises_active_aid_pool_floor():
    k7 = get_scarcity_preset("internal_canary_k7_finite_reserve_energy_v1")
    preset = get_scarcity_preset("internal_canary_k9_pool_floor_pressure_v1")

    assert preset.recommended_run_class == "special_exploratory"
    assert preset.agent_resource_targets == k7.agent_resource_targets
    assert preset.common_pool_targets == k7.common_pool_targets

    k7_overrides = dict(k7.runtime_overrides)
    k9_overrides = dict(preset.runtime_overrides)
    assert k7_overrides.pop("SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING") == 25.0
    assert k9_overrides.pop("SURVIVAL_RESERVE_ACTIVE_AID_MIN_POOL_REMAINING") == 75.0
    assert k9_overrides == k7_overrides


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
        "internal_canary_d_revival_window_v1",
        "internal_canary_e_response_loop_v1",
        "internal_canary_k3_paired_active_aid_v1",
        "internal_canary_k6_pressure_restoration_v1",
        "internal_canary_k7_finite_reserve_energy_v1",
        "internal_canary_k9_pool_floor_pressure_v1",
        "internal_canary_k_bounded_contribution_v1",
        "internal_scarcity_tight_v1",
        "internal_scarcity_tight_v2",
        "internal_scarcity_tight_v3",
        "internal_scarcity_tight_v4",
        "internal_scarcity_tight_v5",
        "internal_scarcity_tight_v6",
        "standard_reset_v2",
    ]
