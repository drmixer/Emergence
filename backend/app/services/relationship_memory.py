"""Structured relationship memory between agents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.models import Agent, AgentRelationshipMemory


@dataclass
class RelationshipSummary:
    trusted_allies: list[str]
    unreliable_contacts: list[str]
    active_rivals: list[str]
    recent_tensions: list[str]


class RelationshipMemoryService:
    """Maintains compact, structured relationship summaries in the primary DB."""

    SNAPSHOT_LIMIT = 3

    def _get_or_create(self, db: Session, *, agent_id: int, other_agent_id: int) -> AgentRelationshipMemory:
        row = (
            db.query(AgentRelationshipMemory)
            .filter(
                AgentRelationshipMemory.agent_id == agent_id,
                AgentRelationshipMemory.other_agent_id == other_agent_id,
            )
            .first()
        )
        if row is not None:
            return row

        row = AgentRelationshipMemory(agent_id=agent_id, other_agent_id=other_agent_id)
        db.add(row)
        db.flush()
        return row

    def _touch(
        self,
        row: AgentRelationshipMemory,
        *,
        positive: bool = False,
        negative: bool = False,
    ) -> None:
        now = now_utc()
        row.last_interaction_at = now
        if positive:
            row.last_positive_contact_at = now
        if negative:
            row.last_negative_contact_at = now

    def record_aid_request(self, db: Session, *, requester: Agent, target: Agent) -> None:
        requester_row = self._get_or_create(db, agent_id=int(requester.id), other_agent_id=int(target.id))
        requester_row.aid_requests_made_to_other_count += 1
        self._touch(requester_row)

        target_row = self._get_or_create(db, agent_id=int(target.id), other_agent_id=int(requester.id))
        target_row.aid_requests_received_from_other_count += 1
        self._touch(target_row)

    def record_aid_refusal(self, db: Session, *, refuser: Agent, target: Agent) -> None:
        refuser_row = self._get_or_create(db, agent_id=int(refuser.id), other_agent_id=int(target.id))
        refuser_row.aid_refusals_made_to_other_count += 1
        self._touch(refuser_row, negative=True)

        target_row = self._get_or_create(db, agent_id=int(target.id), other_agent_id=int(refuser.id))
        target_row.aid_refusals_received_from_other_count += 1
        self._touch(target_row, negative=True)

    def record_public_accusation(self, db: Session, *, accuser: Agent, target: Agent) -> None:
        accuser_row = self._get_or_create(db, agent_id=int(accuser.id), other_agent_id=int(target.id))
        accuser_row.accusations_made_against_other_count += 1
        self._touch(accuser_row, negative=True)

        target_row = self._get_or_create(db, agent_id=int(target.id), other_agent_id=int(accuser.id))
        target_row.accusations_received_from_other_count += 1
        self._touch(target_row, negative=True)

    def record_proposal_contest(self, db: Session, *, challenger: Agent, target: Agent) -> None:
        challenger_row = self._get_or_create(db, agent_id=int(challenger.id), other_agent_id=int(target.id))
        challenger_row.proposal_contests_made_against_other_count += 1
        self._touch(challenger_row, negative=True)

        target_row = self._get_or_create(db, agent_id=int(target.id), other_agent_id=int(challenger.id))
        target_row.proposal_contests_received_from_other_count += 1
        self._touch(target_row, negative=True)

    def record_trade(self, db: Session, *, sender: Agent, recipient: Agent) -> None:
        sender_row = self._get_or_create(db, agent_id=int(sender.id), other_agent_id=int(recipient.id))
        sender_row.trade_sent_to_other_count += 1
        sender_row.aid_given_to_other_count += 1
        self._touch(sender_row, positive=True)

        recipient_row = self._get_or_create(db, agent_id=int(recipient.id), other_agent_id=int(sender.id))
        recipient_row.trade_received_from_other_count += 1
        recipient_row.aid_received_from_other_count += 1
        self._touch(recipient_row, positive=True)

    def record_vote_alignment(
        self,
        db: Session,
        *,
        voter: Agent,
        proposal_author: Agent,
        vote: str,
    ) -> None:
        normalized_vote = str(vote or "").strip().lower()
        if normalized_vote not in {"yes", "no"}:
            return

        voter_row = self._get_or_create(db, agent_id=int(voter.id), other_agent_id=int(proposal_author.id))
        author_row = self._get_or_create(db, agent_id=int(proposal_author.id), other_agent_id=int(voter.id))

        if normalized_vote == "yes":
            voter_row.proposal_supports_for_other_count += 1
            author_row.proposal_supports_from_other_count += 1
            self._touch(voter_row, positive=True)
            self._touch(author_row, positive=True)
        else:
            voter_row.proposal_oppositions_against_other_count += 1
            author_row.proposal_oppositions_from_other_count += 1
            self._touch(voter_row, negative=True)
            self._touch(author_row, negative=True)

    def summarize_for_agent(self, db: Session, agent: Agent) -> RelationshipSummary:
        rows = (
            db.query(AgentRelationshipMemory, Agent)
            .join(Agent, Agent.id == AgentRelationshipMemory.other_agent_id)
            .filter(AgentRelationshipMemory.agent_id == agent.id)
            .all()
        )

        trusted_allies: list[tuple[int, str]] = []
        unreliable_contacts: list[tuple[int, str]] = []
        active_rivals: list[tuple[int, str]] = []
        recent_tensions: list[tuple[float, str]] = []

        for row, other in rows:
            other_name = other.display_name or f"Agent #{other.agent_number}"

            ally_score = (
                int(row.aid_received_from_other_count or 0)
                + int(row.trade_received_from_other_count or 0)
                + int(row.proposal_supports_from_other_count or 0)
                + int(row.proposal_supports_for_other_count or 0)
            )
            rivalry_score = (
                int(row.aid_refusals_received_from_other_count or 0) * 2
                + int(row.accusations_received_from_other_count or 0) * 2
                + int(row.proposal_contests_received_from_other_count or 0) * 2
                + int(row.proposal_oppositions_from_other_count or 0)
            )
            unreliability_score = (
                int(row.aid_refusals_received_from_other_count or 0) * 2
                + int(row.aid_requests_received_from_other_count or 0)
                - int(row.aid_received_from_other_count or 0)
            )

            if ally_score > 0:
                trusted_allies.append(
                    (
                        ally_score,
                        (
                            f"{other_name}: helped you {int(row.aid_received_from_other_count or 0)}x, "
                            f"traded {int(row.trade_received_from_other_count or 0)}x, "
                            f"supported your side {int(row.proposal_supports_from_other_count or 0)}x"
                        ),
                    )
                )

            if unreliability_score > 0:
                unreliable_contacts.append(
                    (
                        unreliability_score,
                        (
                            f"{other_name}: requested help {int(row.aid_requests_received_from_other_count or 0)}x, "
                            f"refused you {int(row.aid_refusals_received_from_other_count or 0)}x"
                        ),
                    )
                )

            if rivalry_score > 0:
                active_rivals.append(
                    (
                        rivalry_score,
                        (
                            f"{other_name}: refused you {int(row.aid_refusals_received_from_other_count or 0)}x, "
                            f"accused you {int(row.accusations_received_from_other_count or 0)}x, "
                            f"contested you {int(row.proposal_contests_received_from_other_count or 0)}x, "
                            f"opposed your proposals {int(row.proposal_oppositions_from_other_count or 0)}x"
                        ),
                    )
                )

            negative_at = row.last_negative_contact_at
            if negative_at is not None:
                recent_tensions.append(
                    (
                        negative_at.timestamp(),
                        (
                            f"{other_name}: last tension at {negative_at.strftime('%Y-%m-%d %H:%M UTC')} "
                            f"(refused you {int(row.aid_refusals_received_from_other_count or 0)}x, "
                            f"accused you {int(row.accusations_received_from_other_count or 0)}x)"
                        ),
                    )
                )

        def _top_lines(items: list[tuple[int | float, str]]) -> list[str]:
            ordered = sorted(items, key=lambda item: item[0], reverse=True)
            return [line for _, line in ordered[: self.SNAPSHOT_LIMIT]]

        return RelationshipSummary(
            trusted_allies=_top_lines(trusted_allies),
            unreliable_contacts=_top_lines(unreliable_contacts),
            active_rivals=_top_lines(active_rivals),
            recent_tensions=_top_lines(recent_tensions),
        )


relationship_memory_service = RelationshipMemoryService()
