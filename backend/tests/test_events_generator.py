from app.services import events_generator


def test_world_event_generation_enabled_defaults_true(monkeypatch):
    monkeypatch.setattr(
        events_generator.runtime_config_service,
        "get_effective_value_cached",
        lambda key: None,
    )

    assert events_generator.world_event_generation_enabled() is True


def test_world_event_generation_enabled_parses_false(monkeypatch):
    monkeypatch.setattr(
        events_generator.runtime_config_service,
        "get_effective_value_cached",
        lambda key: "false" if key == "WORLD_EVENT_GENERATION_ENABLED" else None,
    )

    assert events_generator.world_event_generation_enabled() is False
