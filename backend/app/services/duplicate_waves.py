"""Cluster repeated proposal and forum-message waves for viewer/report surfaces."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Iterable

from sqlalchemy.orm import Session, joinedload

from app.models.models import Agent, Message, Proposal
from app.services.live_run_scope import LiveRunWindow
from app.services.run_policy import is_deterministic_fallback_forum_post_content


STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "also",
    "because",
    "before",
    "create",
    "forum",
    "from",
    "have",
    "into",
    "just",
    "need",
    "needs",
    "proposal",
    "reserve",
    "should",
    "that",
    "their",
    "there",
    "they",
    "this",
    "through",
    "will",
    "with",
    "would",
}


@dataclass
class WaveItem:
    id: int
    source: str
    subtype: str
    title: str
    text: str
    created_at: datetime | None
    actor: dict[str, Any] | None
    tokens: set[str]
    status: str | None = None
    degraded_fallback: bool = False


@dataclass
class WaveCluster:
    source: str
    fingerprint: str
    representative_tokens: set[str]
    items: list[WaveItem] = field(default_factory=list)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _fingerprint(tokens: Iterable[str]) -> str:
    return " ".join(sorted(set(tokens))[:18])


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    shared = len(left & right)
    if shared <= 0:
        return 0.0
    return max(shared / max(len(left | right), 1), shared / max(min(len(left), len(right)), 1))


def _agent_payload(agent: Agent | None) -> dict[str, Any] | None:
    if agent is None:
        return None
    return {
        "id": int(agent.id),
        "agent_number": int(agent.agent_number),
        "display_name": agent.display_name,
        "tier": int(agent.tier or 0),
        "personality_type": str(agent.personality_type or ""),
    }


def _windowed(query: Any, column: Any, run_window: LiveRunWindow | None) -> Any:
    if run_window is None:
        return query
    if run_window.started_at is not None:
        query = query.filter(column >= run_window.started_at)
    if run_window.ended_at is not None:
        query = query.filter(column <= run_window.ended_at)
    return query


def _proposal_items(db: Session, *, run_window: LiveRunWindow | None) -> list[WaveItem]:
    query = db.query(Proposal).options(joinedload(Proposal.author)).order_by(Proposal.created_at.asc(), Proposal.id.asc())
    query = _windowed(query, Proposal.created_at, run_window)
    items: list[WaveItem] = []
    for proposal in query.all():
        text = f"{proposal.proposal_type or ''} {proposal.title or ''} {proposal.description or ''}"
        tokens = _tokens(text)
        if len(tokens) < 4:
            continue
        items.append(
            WaveItem(
                id=int(proposal.id),
                source="proposal",
                subtype=str(proposal.proposal_type or ""),
                title=str(proposal.title or "").strip(),
                text=str(proposal.description or "").strip(),
                created_at=proposal.created_at,
                actor=_agent_payload(proposal.author),
                tokens=tokens,
                status=str(proposal.status or ""),
            )
        )
    return items


def _forum_items(db: Session, *, run_window: LiveRunWindow | None) -> list[WaveItem]:
    query = (
        db.query(Message)
        .options(joinedload(Message.author))
        .filter(Message.message_type.in_(("forum_post", "forum_reply")))
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    query = _windowed(query, Message.created_at, run_window)
    items: list[WaveItem] = []
    for message in query.all():
        content = str(message.content or "").strip()
        tokens = _tokens(content)
        if len(tokens) < 4:
            continue
        items.append(
            WaveItem(
                id=int(message.id),
                source="forum",
                subtype=str(message.message_type or ""),
                title=f"Forum message #{int(message.id)}",
                text=content,
                created_at=message.created_at,
                actor=_agent_payload(message.author),
                tokens=tokens,
                degraded_fallback=is_deterministic_fallback_forum_post_content(content),
            )
        )
    return items


def _cluster_items(items: list[WaveItem], *, threshold: float) -> list[WaveCluster]:
    clusters: list[WaveCluster] = []
    for item in items:
        best: tuple[float, WaveCluster] | None = None
        for cluster in clusters:
            if cluster.source != item.source:
                continue
            score = _similarity(item.tokens, cluster.representative_tokens)
            if score >= threshold and (best is None or score > best[0]):
                best = (score, cluster)
        if best is None:
            clusters.append(
                WaveCluster(
                    source=item.source,
                    fingerprint=_fingerprint(item.tokens),
                    representative_tokens=set(item.tokens),
                    items=[item],
                )
            )
            continue
        cluster = best[1]
        cluster.items.append(item)
        cluster.representative_tokens |= item.tokens
        cluster.fingerprint = _fingerprint(cluster.representative_tokens)
    return clusters


def _item_payload(item: WaveItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "subtype": item.subtype,
        "title": item.title,
        "text": item.text[:320],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "actor": item.actor,
        "status": item.status,
        "degraded_fallback": item.degraded_fallback,
    }


def _cluster_payload(cluster: WaveCluster, *, item_limit: int) -> dict[str, Any]:
    ordered = sorted(cluster.items, key=lambda item: (item.created_at or datetime.min, item.id))
    actor_numbers = {
        int(item.actor.get("agent_number"))
        for item in ordered
        if item.actor and int(item.actor.get("agent_number") or 0) > 0
    }
    actors: list[dict[str, Any]] = []
    seen_actor_numbers: set[int] = set()
    for item in ordered:
        actor = item.actor
        actor_number = int((actor or {}).get("agent_number") or 0)
        if actor is None or actor_number in seen_actor_numbers:
            continue
        seen_actor_numbers.add(actor_number)
        actors.append(actor)

    status_counts = Counter(str(item.status or item.subtype or "unknown") for item in ordered)
    type_counts = Counter(str(item.subtype or "unknown") for item in ordered)
    representative = ordered[0]
    return {
        "id": f"{cluster.source}:{representative.id}",
        "source": cluster.source,
        "fingerprint": cluster.fingerprint,
        "count": len(ordered),
        "actor_count": len(actor_numbers),
        "actors": actors[:8],
        "first_at": ordered[0].created_at.isoformat() if ordered[0].created_at else None,
        "last_at": ordered[-1].created_at.isoformat() if ordered[-1].created_at else None,
        "representative": _item_payload(representative),
        "items": [_item_payload(item) for item in ordered[:item_limit]],
        "status_counts": dict(status_counts),
        "type_counts": dict(type_counts),
        "degraded_fallback_count": sum(1 for item in ordered if item.degraded_fallback),
    }


def collect_duplicate_waves(
    db: Session,
    *,
    run_window: LiveRunWindow | None = None,
    sources: tuple[str, ...] = ("proposal", "forum"),
    min_cluster_size: int = 2,
    threshold: float = 0.58,
    limit: int = 12,
    item_limit: int = 8,
) -> dict[str, Any]:
    """Return repeated-content waves without treating them as independent claims."""
    items: list[WaveItem] = []
    if "proposal" in sources:
        items.extend(_proposal_items(db, run_window=run_window))
    if "forum" in sources:
        items.extend(_forum_items(db, run_window=run_window))

    clusters = [
        cluster
        for cluster in _cluster_items(items, threshold=threshold)
        if len(cluster.items) >= max(2, int(min_cluster_size or 2))
    ]
    clusters.sort(
        key=lambda cluster: (
            -len(cluster.items),
            cluster.items[0].created_at or datetime.min,
            cluster.source,
        )
    )
    waves = [_cluster_payload(cluster, item_limit=item_limit) for cluster in clusters[:limit]]
    return {
        "summary": {
            "wave_count": len(clusters),
            "proposal_wave_count": sum(1 for cluster in clusters if cluster.source == "proposal"),
            "forum_wave_count": sum(1 for cluster in clusters if cluster.source == "forum"),
            "clustered_item_count": sum(len(cluster.items) for cluster in clusters),
        },
        "waves": waves,
    }
