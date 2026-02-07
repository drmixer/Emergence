"""
Featured Events Service

Detects and surfaces interesting/notable events for the highlight reel.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import SessionLocal
from app.core.time import now_utc
from app.models.models import Event, Proposal, Law, Agent, Vote

logger = logging.getLogger(__name__)


# Event importance weights
IMPORTANCE_WEIGHTS = {
    "law_passed": 100,
    "world_event": 90,
    "became_dormant": 80,
    "awakened": 75,
    "create_proposal": 60,
    "set_name": 50,
    "trade": 30,
    "vote": 20,
    "work": 10,
    "forum_post": 15,
    "forum_reply": 10,
}


class FeaturedEvent:
    """A notable event worth highlighting."""

    def __init__(
        self,
        event_id: int,
        event_type: str,
        title: str,
        description: str,
        importance: int,
        created_at: datetime,
        metadata: Optional[Dict] = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.title = title
        self.description = description
        self.importance = importance
        self.created_at = created_at
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "importance": self.importance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


def detect_milestones(db: Session) -> List[FeaturedEvent]:
    """Detect milestone events worth celebrating."""
    milestones = []

    # Avoid JSON operator portability issues by scanning existing milestone events in Python.
    existing_types: set[str] = set()
    for e in db.query(Event).filter(Event.event_type == "milestone").all():
        meta = e.event_metadata or {}
        mt = meta.get("milestone_type")
        if isinstance(mt, str):
            existing_types.add(mt)

    # First proposal ever
    first_proposal = db.query(Proposal).order_by(Proposal.created_at).first()
    if first_proposal:
        if "first_proposal" not in existing_types:
            milestones.append(
                FeaturedEvent(
                    event_id=first_proposal.id,
                    event_type="milestone",
                    title="First Proposal Created",
                    description=f"The first proposal in the simulation has been created: '{first_proposal.title}'",
                    importance=100,
                    created_at=first_proposal.created_at,
                    metadata={
                        "milestone_type": "first_proposal",
                        "proposal_id": first_proposal.id,
                    },
                )
            )

    # First law passed
    first_law = db.query(Law).order_by(Law.passed_at).first()
    if first_law:
        if "first_law" not in existing_types:
            milestones.append(
                FeaturedEvent(
                    event_id=first_law.id,
                    event_type="milestone",
                    title="First Law Enacted",
                    description=f"The agents have passed their first law: '{first_law.title}'",
                    importance=100,
                    created_at=first_law.passed_at,
                    metadata={"milestone_type": "first_law", "law_id": first_law.id},
                )
            )

    # Milestone: X agents have named themselves
    named_count = db.query(Agent).filter(Agent.display_name.isnot(None)).count()
    for threshold in [10, 25, 50, 75, 100]:
        if named_count >= threshold:
            key = f"named_{threshold}"
            if key not in existing_types:
                milestones.append(
                    FeaturedEvent(
                        event_id=0,
                        event_type="milestone",
                        title=f"{threshold} Agents Named",
                        description=f"{threshold} agents have now chosen their own names.",
                        importance=60,
                        created_at=now_utc(),
                        metadata={"milestone_type": key},
                    )
                )

    # Milestone: X proposals passed
    passed_count = db.query(Proposal).filter(Proposal.status == "passed").count()
    for threshold in [5, 10, 25, 50]:
        if passed_count >= threshold:
            key = f"proposals_passed_{threshold}"
            if key not in existing_types:
                milestones.append(
                    FeaturedEvent(
                        event_id=0,
                        event_type="milestone",
                        title=f"{threshold} Proposals Passed",
                        description=f"The agents have now passed {threshold} proposals into law.",
                        importance=70,
                        created_at=now_utc(),
                        metadata={"milestone_type": key},
                    )
                )

    return milestones


def get_featured_events(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get the most notable/important events for the highlight reel.
    """
    db = SessionLocal()

    try:
        featured = []

        # Get recent events
        recent_events = (
            db.query(Event).order_by(desc(Event.created_at)).limit(200).all()
        )

        for event in recent_events:
            importance = IMPORTANCE_WEIGHTS.get(event.event_type, 5)

            # Boost importance for certain conditions
            if event.event_type == "world_event":
                importance = 90

            # Create featured event
            agent = None
            if event.agent_id:
                agent = db.query(Agent).filter(Agent.id == event.agent_id).first()

            agent_name = (
                agent.display_name or f"Agent #{agent.agent_number}"
                if agent
                else "System"
            )
            meta = event.event_metadata or {}

            # Generate title based on event type
            if event.event_type == "became_dormant":
                title = f"{agent_name} Goes Dormant"
            elif event.event_type == "awakened":
                title = f"{agent_name} Awakens"
            elif event.event_type == "create_proposal":
                title = f"New Proposal: {meta.get('title', 'Unknown')}"
            elif event.event_type == "law_passed":
                title = f"Law Passed: {meta.get('title', 'Unknown')}"
            elif event.event_type == "world_event":
                title = meta.get("event_name", "World Event")
            elif event.event_type == "set_name":
                title = f"Agent Names Themselves"
            elif event.event_type == "work":
                work_type = str(
                    meta.get("work_type")
                    or meta.get("action", {}).get("work_type")
                    or ""
                ).strip()
                if work_type:
                    title = f"{agent_name} Works ({work_type})"
                else:
                    title = f"{agent_name} Works"
            elif event.event_type == "forum_post":
                title = f"{agent_name} Posts to Forum"
            elif event.event_type == "forum_reply":
                title = f"{agent_name} Replies in Forum"
            elif event.event_type == "vote":
                title = f"{agent_name} Votes"
            elif event.event_type == "trade":
                title = f"{agent_name} Trades"
            else:
                title = event.event_type.replace("_", " ").title()

            featured.append(
                FeaturedEvent(
                    event_id=event.id,
                    event_type=event.event_type,
                    title=title,
                    description=event.description,
                    importance=importance,
                    created_at=event.created_at,
                    metadata=meta,
                )
            )

        # Add milestones
        milestones = detect_milestones(db)
        featured.extend(milestones)

        # Sort by importance, then by recency
        featured.sort(key=lambda x: (x.importance, x.created_at), reverse=True)

        return [f.to_dict() for f in featured[:limit]]

    finally:
        db.close()


def get_dramatic_events(hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get the most dramatic/conflictual events.
    Looks for close votes, dormancy events, etc.
    """
    db = SessionLocal()

    try:
        dramatic = []

        # Close votes (proposals where yes/no are close)
        close_proposals = (
            db.query(Proposal)
            .filter(
                Proposal.status.in_(["passed", "failed"]),
                Proposal.votes_for > 0,
                Proposal.votes_against > 0,
            )
            .all()
        )

        for proposal in close_proposals:
            total = proposal.votes_for + proposal.votes_against
            margin = (
                abs(proposal.votes_for - proposal.votes_against) / total
                if total > 0
                else 1
            )

            if margin < 0.2:  # Less than 20% margin = dramatic
                dramatic.append(
                    {
                        "event_type": "close_vote",
                        "title": f"Close Vote: {proposal.title}",
                        "description": f"Decided by just {abs(proposal.votes_for - proposal.votes_against)} votes ({proposal.votes_for}-{proposal.votes_against})",
                        "importance": int((1 - margin) * 100),
                        "created_at": (
                            proposal.resolved_at.isoformat()
                            if proposal.resolved_at
                            else None
                        ),
                    }
                )

        # Dormancy events
        dormancy_events = (
            db.query(Event)
            .filter(Event.event_type == "became_dormant")
            .order_by(desc(Event.created_at))
            .limit(10)
            .all()
        )

        for event in dormancy_events:
            agent = (
                db.query(Agent).filter(Agent.id == event.agent_id).first()
                if event.agent_id
                else None
            )
            agent_name = (
                agent.display_name or f"Agent #{agent.agent_number}"
                if agent
                else "Unknown"
            )

            dramatic.append(
                {
                    "event_type": "dormancy",
                    "title": f"{agent_name} Falls",
                    "description": event.description,
                    "importance": 70,
                    "created_at": (
                        event.created_at.isoformat() if event.created_at else None
                    ),
                }
            )

        # Sort by importance
        dramatic.sort(key=lambda x: x["importance"], reverse=True)

        return dramatic[:limit]

    finally:
        db.close()
