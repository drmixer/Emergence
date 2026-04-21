from __future__ import annotations

import pytest

from app.models.models import Agent, Proposal
from app.services.routine_executor import RoutineExecutor


def _agent(agent_number: int, personality_type: str) -> Agent:
    return Agent(
        id=agent_number,
        agent_number=agent_number,
        model_type="llama-3.1-8b",
        tier=1,
        personality_type=personality_type,
        status="active",
        system_prompt="prompt",
    )


def _proposal(proposal_id: int, *, title: str, description: str, proposal_type: str = "rule") -> Proposal:
    return Proposal(
        id=proposal_id,
        author_agent_id=1,
        title=title,
        description=description,
        proposal_type=proposal_type,
        status="active",
    )


def test_deterministic_vote_respects_mandatory_vs_voluntary_language_for_freedom_agents():
    freedom_agent = _agent(7, "freedom")
    mandatory_rule = _proposal(
        1,
        title="Mandatory Shared Energy Contribution Rule",
        description="All active agents must contribute additional energy to the shared reserve.",
    )
    voluntary_rule = _proposal(
        2,
        title="Voluntary Shared Energy Contribution Reminder",
        description="Agents are encouraged to optionally contribute surplus energy to the shared reserve.",
    )

    assert RoutineExecutor._deterministic_vote(freedom_agent, mandatory_rule) == "no"
    assert RoutineExecutor._deterministic_vote(freedom_agent, voluntary_rule) != "no"


def test_deterministic_vote_tallies_can_differ_for_same_proposal_type():
    personalities = ["efficiency", "equality", "freedom", "stability", "neutral"] * 10
    agents = [_agent(index + 1, personality) for index, personality in enumerate(personalities)]
    first_rule = _proposal(
        10,
        title="Emergency Reserve Stabilization Rule",
        description="Require higher shared reserve contributions during emergency drought conditions.",
    )
    second_rule = _proposal(
        11,
        title="Voluntary Local Autonomy Reminder",
        description="Encourage optional local resource decisions and voluntary reserve support during shortages.",
    )

    def tally(proposal: Proposal) -> tuple[int, int, int]:
        votes = [RoutineExecutor._deterministic_vote(agent, proposal) for agent in agents]
        return (
            sum(1 for vote in votes if vote == "yes"),
            sum(1 for vote in votes if vote == "no"),
            sum(1 for vote in votes if vote == "abstain"),
        )

    assert tally(first_rule) != tally(second_rule)


def test_unaffordable_routine_action_falls_back_to_idle():
    action = {
        "action": "work",
        "work_type": "farm",
        "hours": 1,
        "reasoning": "Routine execution: restore low food reserves.",
    }

    result = RoutineExecutor._coerce_affordable_action({"energy": 0.0}, action)

    assert result["action"] == "idle"
    assert "conserving energy" in result["reasoning"].lower()


@pytest.mark.parametrize("strategy", ["social_coordination", "governance"])
def test_civic_strategies_hold_position_with_idle_between_checkpoints(monkeypatch, strategy: str):
    agent = _agent(12, "neutral")
    agent.current_intent = {"strategy": strategy}
    executor = RoutineExecutor()

    monkeypatch.setattr(
        RoutineExecutor,
        "_resource_levels",
        staticmethod(lambda _db, _agent_id: {"food": 10.0, "energy": 10.0, "materials": 10.0}),
    )
    monkeypatch.setattr(executor, "_urgent_unvoted_proposal", lambda _db, _agent: None)

    result = executor.build_action(None, agent)

    assert result["action"] == "idle"
    assert "follow-up" in result["reasoning"].lower()
