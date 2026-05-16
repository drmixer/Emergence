import asyncio
from types import SimpleNamespace

from app.services import llm_client


def test_get_agent_action_preserves_zero_parse_retry_override(monkeypatch):
    overrides = {
        "LLM_ACTION_MAX_TOKENS": 220,
        "LLM_ACTION_PARSE_RETRY_ATTEMPTS": 0,
    }

    monkeypatch.setattr(
        llm_client.runtime_config_service,
        "get_effective_value_cached",
        lambda key: overrides.get(key),
    )

    calls = {"count": 0, "max_tokens": []}

    async def _fake_get_completion(**kwargs):
        calls["count"] += 1
        calls["max_tokens"].append(kwargs["max_tokens"])
        return '{"not_action":"missing"}'

    monkeypatch.setattr(llm_client.llm_client, "get_completion", _fake_get_completion)
    monkeypatch.setattr(
        llm_client,
        "parse_action_response_with_meta",
        lambda _response: (
            {"action": "idle"},
            {"ok": False, "parse_status": "missing_action", "error_type": "missing_action"},
        ),
    )

    action = asyncio.run(
        llm_client.get_agent_action(
            agent_id=7,
            model_type="gm_gemini_2_5_flash",
            system_prompt="system",
            context_prompt="context",
            checkpoint_number=1,
        )
    )

    assert calls["count"] == 1
    assert calls["max_tokens"] == [220]
    assert action["_llm_meta"]["parse"]["attempt"] == 1
    assert action["_llm_meta"]["parse"]["max_attempts"] == 1


def test_parse_action_response_rejects_truncated_json_like_payload():
    payload, meta = llm_client.parse_action_response_with_meta(
        '{"action":"forum_post","content":"Great to see the community rally'
    )

    assert payload["action"] == "idle"
    assert meta["ok"] is False
    assert meta["parse_status"] == "json_not_found_rejected"
    assert meta["error_type"] == "json_not_found"


def test_throttle_gemini_honors_runtime_rpm_limit(monkeypatch):
    client = llm_client.LLMClient()
    now = {"value": 100.0}
    client._gemini_window_s = 1.0
    client._gemini_calls.append(now["value"])
    sleeps: list[float] = []

    monkeypatch.setattr(llm_client.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(
        llm_client.runtime_config_service,
        "get_effective_value_cached",
        lambda key: 1 if key == "GEMINI_RPM_LIMIT" else None,
    )
    monkeypatch.setattr(llm_client.random, "random", lambda: 0.0)

    async def _fake_sleep(delay: float):
        sleeps.append(delay)
        now["value"] += delay + 0.001

    monkeypatch.setattr(llm_client.asyncio, "sleep", _fake_sleep)

    asyncio.run(client._throttle_gemini())

    assert len(sleeps) == 1
    assert 0.0 < sleeps[0] <= 1.0
    assert len(client._gemini_calls) == 1


def test_create_completion_with_budget_throttles_gemini(monkeypatch):
    client = llm_client.LLMClient()
    calls = {"gemini_throttle": 0, "openrouter_throttle": 0}
    create_kwargs: list[dict] = []

    async def _fake_gemini_throttle():
        calls["gemini_throttle"] += 1

    async def _fake_openrouter_throttle():
        calls["openrouter_throttle"] += 1

    async def _fake_create(**kwargs):
        create_kwargs.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"idle"}'))],
        )

    monkeypatch.setattr(client, "_throttle_gemini", _fake_gemini_throttle)
    monkeypatch.setattr(client, "_throttle_openrouter", _fake_openrouter_throttle)
    monkeypatch.setattr(
        client.gemini_client.chat.completions,
        "create",
        _fake_create,
    )
    monkeypatch.setattr(
        llm_client.usage_budget,
        "preflight",
        lambda **_kwargs: SimpleNamespace(
            allowed=True,
            reason=None,
            soft_cap_reached=False,
            snapshot=SimpleNamespace(calls_total=0, estimated_cost_usd=0.0),
        ),
    )
    recorded: list[dict] = []
    monkeypatch.setattr(
        llm_client.usage_budget,
        "record_call",
        lambda **kwargs: recorded.append(kwargs),
    )

    response, used_model_name, provider_name, blocked_reason = asyncio.run(
        client._create_completion_with_budget(
            client=client.gemini_client,
            agent_id=23,
            checkpoint_number=2,
            model_type="gm_gemini_2_0_flash_lite",
            model_name="gemini-2.0-flash-lite",
            system_prompt="system",
            user_prompt="user",
            max_tokens=128,
            temperature=0.7,
            fallback_used=False,
        )
    )

    assert blocked_reason is None
    assert provider_name == "gemini"
    assert used_model_name == "gemini-2.0-flash-lite"
    assert calls == {"gemini_throttle": 1, "openrouter_throttle": 0}
    assert response.usage.total_tokens == 18
    assert recorded and recorded[0]["provider"] == "gemini"
    assert recorded[0]["success"] is True
    assert "extra_body" not in create_kwargs[0]


def test_create_completion_disables_gemini_25_flash_thinking(monkeypatch):
    client = llm_client.LLMClient()
    create_kwargs: list[dict] = []

    async def _fake_create(**kwargs):
        create_kwargs.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"idle"}'))],
        )

    monkeypatch.setattr(client, "_throttle_gemini", lambda: asyncio.sleep(0))
    monkeypatch.setattr(
        client.gemini_client.chat.completions,
        "create",
        _fake_create,
    )
    monkeypatch.setattr(
        llm_client.usage_budget,
        "preflight",
        lambda **_kwargs: SimpleNamespace(
            allowed=True,
            reason=None,
            soft_cap_reached=False,
            snapshot=SimpleNamespace(calls_total=0, estimated_cost_usd=0.0),
        ),
    )
    monkeypatch.setattr(llm_client.usage_budget, "record_call", lambda **_kwargs: None)

    response, used_model_name, provider_name, blocked_reason = asyncio.run(
        client._create_completion_with_budget(
            client=client.gemini_client,
            agent_id=23,
            checkpoint_number=2,
            model_type="gm_gemini_2_0_flash",
            model_name="gemini-2.5-flash",
            system_prompt="system",
            user_prompt="user",
            max_tokens=128,
            temperature=0.7,
            fallback_used=False,
        )
    )

    assert blocked_reason is None
    assert provider_name == "gemini"
    assert used_model_name == "gemini-2.5-flash"
    assert response.usage.total_tokens == 18
    assert create_kwargs[0]["extra_body"] == {
        "extra_body": {"google": {"thinking_config": {"thinking_budget": 0}}}
    }


def test_provider_stabilized_cohort_labels_route_to_gemini_25_flash():
    client = llm_client.LLMClient()

    for model_type in (
        "gm_gemini_2_0_flash",
        "gm_gemini_2_0_flash_lite",
        "or_gpt_oss_20b_free",
        "or_qwen3_4b_free",
    ):
        routed_client, model_name = client._get_client_and_model(model_type)
        assert routed_client is client.gemini_client
        assert model_name == "gemini-2.5-flash"


def test_gemini_cohorts_route_to_vertex_when_enabled(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "VERTEX_GEMINI_ENABLED", True)
    monkeypatch.setattr(
        llm_client.settings,
        "VERTEX_GEMINI_SERVICE_ACCOUNT_JSON",
        '{"project_id":"emergencequest"}',
    )
    client = llm_client.LLMClient()

    for model_type in (
        "gm_gemini_2_5_flash",
        "gm_gemini_2_0_flash",
        "gm_gemini_2_0_flash_lite",
        "or_gpt_oss_20b_free",
        "or_qwen3_4b_free",
    ):
        routed_client, model_name = client._get_client_and_model(model_type)
        assert routed_client is client.vertex_gemini_client
        assert model_name == "gemini-2.5-flash"


def test_create_completion_with_budget_records_vertex_gemini(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "VERTEX_GEMINI_ENABLED", True)
    monkeypatch.setattr(
        llm_client.settings,
        "VERTEX_GEMINI_SERVICE_ACCOUNT_JSON",
        '{"project_id":"emergencequest"}',
    )
    client = llm_client.LLMClient()
    calls = {"gemini_throttle": 0}

    async def _fake_gemini_throttle():
        calls["gemini_throttle"] += 1

    async def _fake_vertex_completion(**_kwargs):
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=13, completion_tokens=5, total_tokens=18),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"idle"}'))],
        )

    monkeypatch.setattr(client, "_throttle_gemini", _fake_gemini_throttle)
    monkeypatch.setattr(client, "_create_vertex_gemini_completion", _fake_vertex_completion)
    monkeypatch.setattr(
        llm_client.usage_budget,
        "preflight",
        lambda **_kwargs: SimpleNamespace(
            allowed=True,
            reason=None,
            soft_cap_reached=False,
            snapshot=SimpleNamespace(calls_total=0, estimated_cost_usd=0.0),
        ),
    )
    recorded: list[dict] = []
    monkeypatch.setattr(
        llm_client.usage_budget,
        "record_call",
        lambda **kwargs: recorded.append(kwargs),
    )

    response, used_model_name, provider_name, blocked_reason = asyncio.run(
        client._create_completion_with_budget(
            client=client.vertex_gemini_client,
            agent_id=23,
            checkpoint_number=2,
            model_type="gm_gemini_2_5_flash",
            model_name="gemini-2.5-flash",
            system_prompt="system",
            user_prompt="user",
            max_tokens=128,
            temperature=0.7,
            fallback_used=False,
        )
    )

    assert blocked_reason is None
    assert provider_name == "google_vertex"
    assert used_model_name == "gemini-2.5-flash"
    assert response.usage.total_tokens == 18
    assert calls == {"gemini_throttle": 1}
    assert recorded and recorded[0]["provider"] == "google_vertex"
    assert recorded[0]["success"] is True


def test_openrouter_routed_cohort_labels_keep_openrouter_provider():
    client = llm_client.LLMClient()

    expected_models = {
        "or_gpt_oss_120b": "openai/gpt-oss-120b",
        "or_qwen3_235b_a22b_2507": "qwen/qwen3-235b-a22b-2507",
    }

    for model_type, expected_model in expected_models.items():
        routed_client, model_name = client._get_client_and_model(model_type)
        assert routed_client is client.openrouter_client
        assert model_name == expected_model
