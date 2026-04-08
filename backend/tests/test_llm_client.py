import asyncio

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
