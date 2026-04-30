from app.services.run_policy import build_terminal_llm_failure_action


def test_special_exploratory_terminal_failure_does_not_emit_public_speech():
    actions = {
        build_terminal_llm_failure_action(
            agent_id=agent_id,
            reason="json_not_found",
            run_class="special_exploratory",
            failure_stage="terminal_llm_failure",
        )["action"]
        for agent_id in range(1, 80)
    }

    assert actions <= {"work", "idle"}
    assert "forum_post" not in actions
