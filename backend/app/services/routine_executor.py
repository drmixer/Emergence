"""
Deterministic routine executor for between-checkpoint actions.

This keeps agents active between strategic LLM checkpoints.
"""
from __future__ import annotations

from datetime import timedelta
from sqlalchemy.orm import Session

from app.models.models import Agent, AgentInventory, Proposal, Vote


class RoutineExecutor:
    """Build deterministic low-level actions from current intent + world state."""

    URGENT_PROPOSAL_WINDOW_MINUTES = 90

    def build_action(self, db: Session, agent: Agent) -> dict:
        resources = self._resource_levels(db, agent.id)
        food = resources.get("food", 0.0)
        energy = resources.get("energy", 0.0)
        materials = resources.get("materials", 0.0)

        # Survival-first deterministic behavior.
        if food < 2.0:
            return self._work_action("farm", "Routine execution: restore low food reserves.")
        if energy < 2.0:
            return self._work_action("generate", "Routine execution: restore low energy reserves.")

        urgent = self._urgent_unvoted_proposal(db, agent)
        if urgent is not None:
            return {
                "action": "vote",
                "proposal_id": urgent.id,
                "vote": self._deterministic_vote(agent, urgent),
                "reasoning": "Routine execution: voting before proposal deadline.",
            }

        strategy = str((agent.current_intent or {}).get("strategy") or "stabilize")
        if strategy == "accumulate_food":
            return self._work_action("farm", "Routine execution: continue food accumulation strategy.")
        if strategy == "accumulate_energy":
            return self._work_action("generate", "Routine execution: continue energy accumulation strategy.")
        if strategy == "accumulate_materials":
            return self._work_action("gather", "Routine execution: continue materials accumulation strategy.")
        if strategy == "conserve_energy":
            return {"action": "idle", "reasoning": "Routine execution: conserving energy between checkpoints."}
        if strategy in {"governance", "social_coordination"}:
            # Keep civic agents productive between strategic replans.
            return self._work_action(self._lowest_resource_work_type(food, energy, materials), "Routine execution: maintain baseline production while monitoring governance.")
        if strategy == "resource_exchange":
            if materials < 12.0:
                return self._work_action("gather", "Routine execution: building trade inventory.")
            return self._work_action("farm", "Routine execution: preparing food inventory for possible trade.")

        return self._work_action(self._lowest_resource_work_type(food, energy, materials), "Routine execution: maintain balanced resources.")

    @staticmethod
    def _work_action(work_type: str, reasoning: str) -> dict:
        return {"action": "work", "work_type": work_type, "hours": 1, "reasoning": reasoning}

    @staticmethod
    def _resource_levels(db: Session, agent_id: int) -> dict[str, float]:
        rows = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id == agent_id)
            .all()
        )
        return {row.resource_type: float(row.quantity) for row in rows}

    def _urgent_unvoted_proposal(self, db: Session, agent: Agent) -> Proposal | None:
        from app.core.time import now_utc

        now = now_utc()
        deadline = now + timedelta(minutes=self.URGENT_PROPOSAL_WINDOW_MINUTES)
        proposals = (
            db.query(Proposal)
            .filter(
                Proposal.status == "active",
                Proposal.voting_closes_at > now,
                Proposal.voting_closes_at <= deadline,
            )
            .order_by(Proposal.voting_closes_at.asc())
            .all()
        )
        for proposal in proposals:
            has_voted = (
                db.query(Vote)
                .filter(Vote.proposal_id == proposal.id, Vote.agent_id == agent.id)
                .first()
            )
            if not has_voted:
                return proposal
        return None

    @staticmethod
    def _deterministic_vote(agent: Agent, proposal: Proposal) -> str:
        personality = str(agent.personality_type or "neutral")
        ptype = str(proposal.proposal_type or "other")

        if personality == "efficiency":
            return "yes" if ptype in {"infrastructure", "law"} else "abstain"
        if personality == "equality":
            return "yes" if ptype in {"allocation", "law"} else "abstain"
        if personality == "freedom":
            return "no" if ptype in {"constitutional", "rule"} else "abstain"
        if personality == "stability":
            return "yes" if ptype in {"law", "rule", "constitutional"} else "abstain"
        return "abstain"

    @staticmethod
    def _lowest_resource_work_type(food: float, energy: float, materials: float) -> str:
        levels = {"farm": food, "generate": energy, "gather": materials}
        return min(levels, key=levels.get)


routine_executor = RoutineExecutor()
