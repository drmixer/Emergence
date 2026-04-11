"""Weekly digest builder with locked template and run-backed evidence links."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.models import Agent, AgentInventory, Event, Law
from app.services.survival_config import (
    active_energy_cost,
    active_food_cost,
    low_resource_warning_threshold,
)

WEEKLY_DIGEST_TEMPLATE_VERSION = "state-of-emergence-v2"
LOCKED_WEEKLY_DIGEST_HEADINGS = (
    "Run Context and Verification",
    "Episode Summary",
    "Who Rose and Who Fell",
    "What Changed",
    "Risk Next",
)


@dataclass
class WeeklyDigestPayload:
    run_id: str
    verification_state: str
    window_start: datetime
    window_end: datetime
    summary: str
    sections: list[dict[str, Any]]
    markdown: str
    markdown_path: str | None
    evidence_gate: dict[str, Any]
    template_version: str = WEEKLY_DIGEST_TEMPLATE_VERSION


class WeeklyDigestInsufficientEvidenceError(RuntimeError):
    """Raised when weekly digest generation is blocked by evidence minimums."""

    def __init__(self, decision: dict[str, Any]):
        super().__init__(str(decision.get("message") or "insufficient weekly digest evidence"))
        self.decision = decision


def _bounded_int(raw_value: Any, *, fallback: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = fallback
    return min(max(value, minimum), maximum)


def evaluate_weekly_digest_evidence(
    *,
    snapshot: dict[str, Any],
    min_events: int,
    min_llm_calls: int,
) -> dict[str, Any]:
    required_events = _bounded_int(min_events, fallback=1, minimum=0, maximum=100000)
    required_llm_calls = _bounded_int(min_llm_calls, fallback=1, minimum=0, maximum=100000)
    observed_events = int(snapshot.get("total_events") or 0)
    observed_llm_calls = int(snapshot.get("llm_calls") or 0)

    events_ok = observed_events >= required_events
    llm_ok = observed_llm_calls >= required_llm_calls
    passed = bool(events_ok and llm_ok)

    if passed:
        status = "ok"
        message = (
            f"Evidence gate passed: events {observed_events}/{required_events}, "
            f"llm_calls {observed_llm_calls}/{required_llm_calls}."
        )
    else:
        status = "insufficient_evidence"
        message = (
            f"Evidence gate failed: events {observed_events}/{required_events}, "
            f"llm_calls {observed_llm_calls}/{required_llm_calls}."
        )

    return {
        "status": status,
        "passed": passed,
        "message": message,
        "requirements": {
            "min_events": required_events,
            "min_llm_calls": required_llm_calls,
        },
        "observed": {
            "total_events": observed_events,
            "llm_calls": observed_llm_calls,
        },
    }


def _resolve_run_id(db: Session, preferred_run_id: str | None) -> str:
    preferred = str(preferred_run_id or "").strip()
    if preferred:
        return preferred

    latest = db.execute(
        text(
            """
            SELECT run_id
            FROM llm_usage
            WHERE run_id IS NOT NULL
              AND run_id <> ''
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
    ).first()
    return str((latest.run_id if latest else "") or "").strip() or "not-set"


def _agent_label(agent: Agent | None) -> str:
    if agent is None:
        return "Unknown Agent"
    if str(agent.display_name or "").strip():
        return str(agent.display_name).strip()
    return f"Agent #{int(agent.agent_number):02d}"


def _truncate_text(value: Any, *, limit: int = 140) -> str:
    text_value = " ".join(str(value or "").split()).strip()
    if len(text_value) <= limit:
        return text_value
    return text_value[: max(0, limit - 1)].rstrip() + "…"


def _join_labels(labels: list[str]) -> str:
    clean = [str(label).strip() for label in labels if str(label).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def _confidence_label(total_events: int) -> str:
    if total_events >= 1000:
        return "high"
    if total_events >= 250:
        return "medium"
    return "low"


def _episode_focus(snapshot: dict[str, Any]) -> str:
    deaths = int(snapshot.get("deaths") or 0)
    dormancies = len(snapshot.get("recent_dormancies") or [])
    laws_passed = int(snapshot.get("laws_passed") or 0)
    proposal_actions = int(snapshot.get("proposal_actions") or 0)
    vote_actions = int(snapshot.get("vote_actions") or 0)
    forum_actions = int(snapshot.get("forum_actions") or 0)
    revivals = len(snapshot.get("recent_revivals") or [])

    if deaths > 0 or dormancies > 0:
        return "survival pressure"
    if laws_passed > 0:
        return "rule changes"
    if (proposal_actions + vote_actions) >= max(1, forum_actions):
        return "governance conflict"
    if revivals > 0:
        return "mutual aid and recovery"
    return "coalition positioning"


def _build_digest_summary(
    *,
    run_id: str,
    window_start: datetime,
    window_end: datetime,
    snapshot: dict[str, Any],
) -> str:
    total_events = int(snapshot.get("total_events") or 0)
    focus = _episode_focus(snapshot)
    recent_laws = list(snapshot.get("recent_laws") or [])
    risk_watch = list(snapshot.get("risk_watch") or [])

    summary = (
        f"From {window_start.date().isoformat()} to {window_end.date().isoformat()} UTC, "
        f"run `{run_id}` produced {total_events:,} run-scoped events. "
        f"The dominant story was {focus}."
    )

    if recent_laws:
        top_law = recent_laws[0]
        summary += f" The clearest system shift was the passage of \"{top_law.get('title') or 'an unnamed law'}\"."

    if int(snapshot.get("deaths") or 0) > 0:
        summary += f" The window also recorded {int(snapshot.get('deaths') or 0):,} permanent deaths."

    if risk_watch:
        top_risk = risk_watch[0]
        risk_label = str(top_risk.get("display_name") or "").strip() or _agent_label(top_risk.get("agent"))
        summary += (
            f" The next watchpoint is {risk_label}, "
            f"now flagged {str(top_risk.get('level_label') or 'at risk').lower()}."
        )

    return summary


def _collect_run_snapshot(db: Session, *, run_id: str, since: datetime) -> dict[str, Any]:
    params = {"run_id": run_id, "since_ts": since}

    llm_totals = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS calls,
              COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_calls,
              COALESCE(SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END), 0) AS provider_model_fallback_calls,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
            FROM llm_usage
            WHERE run_id = :run_id
              AND created_at >= :since_ts
            """
        ),
        params,
    ).first()

    active_agents = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT agent_id) AS active_agents
            FROM llm_usage
            WHERE run_id = :run_id
              AND created_at >= :since_ts
              AND agent_id IS NOT NULL
            """
        ),
        params,
    ).scalar()

    tracked_agent_rows = db.execute(
        text(
            """
            SELECT DISTINCT agent_id
            FROM llm_usage
            WHERE run_id = :run_id
              AND created_at >= :since_ts
              AND agent_id IS NOT NULL
            """
        ),
        params,
    ).all()
    tracked_agent_ids = [
        int(row.agent_id)
        for row in tracked_agent_rows
        if row is not None and row.agent_id is not None
    ]
    tracked_agents = (
        db.query(Agent)
        .filter(Agent.id.in_(tracked_agent_ids))
        .order_by(Agent.agent_number.asc())
        .all()
        if tracked_agent_ids
        else []
    )
    tracked_agents_by_id = {int(agent.id): agent for agent in tracked_agents}

    runtime_actions = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS total_events,
              COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'checkpoint' THEN 1 ELSE 0 END), 0) AS checkpoint_actions,
              COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') = 'deterministic_forced_idle' THEN 1 ELSE 0 END), 0) AS deterministic_forced_idle_actions,
              COALESCE(SUM(CASE WHEN (e.event_metadata -> 'runtime' ->> 'mode') IN ('deterministic_routine_fallback', 'deterministic_fallback') THEN 1 ELSE 0 END), 0) AS deterministic_routine_fallback_actions,
              COALESCE(SUM(CASE WHEN e.event_type = 'create_proposal' THEN 1 ELSE 0 END), 0) AS proposal_actions,
              COALESCE(SUM(CASE WHEN e.event_type = 'vote' THEN 1 ELSE 0 END), 0) AS vote_actions,
              COALESCE(SUM(CASE WHEN e.event_type IN ('forum_post', 'forum_reply') THEN 1 ELSE 0 END), 0) AS forum_actions,
              COALESCE(SUM(CASE WHEN e.event_type = 'law_passed' THEN 1 ELSE 0 END), 0) AS laws_passed,
              COALESCE(SUM(CASE WHEN e.event_type = 'agent_died' THEN 1 ELSE 0 END), 0) AS deaths
            FROM events e
            WHERE e.created_at >= :since_ts
              AND (
                (e.event_metadata -> 'runtime' ->> 'run_id') = :run_id
                OR e.agent_id IN (
                  SELECT DISTINCT u.agent_id
                  FROM llm_usage u
                  WHERE u.agent_id IS NOT NULL
                    AND u.run_id = :run_id
                    AND u.created_at >= :since_ts
                )
              )
            """
        ),
        params,
    ).first()

    traces = db.execute(
        text(
            """
            SELECT
              e.id,
              e.event_type,
              e.description,
              e.created_at
            FROM events e
            WHERE e.created_at >= :since_ts
              AND (
                (e.event_metadata -> 'runtime' ->> 'run_id') = :run_id
                OR e.agent_id IN (
                  SELECT DISTINCT u.agent_id
                  FROM llm_usage u
                  WHERE u.agent_id IS NOT NULL
                    AND u.run_id = :run_id
                    AND u.created_at >= :since_ts
                )
              )
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 30
            """
        ),
        params,
    ).all()

    calls = int((llm_totals.calls if llm_totals else 0) or 0)
    trace_count = len(traces)
    if calls > 0 and trace_count > 0:
        verification_state = "verified"
    elif calls > 0:
        verification_state = "partial"
    else:
        verification_state = "unverified"

    normalized_traces: list[dict[str, Any]] = []
    for row in traces:
        event_id = int((row.id if row else 0) or 0)
        if event_id <= 0:
            continue
        normalized_traces.append(
            {
                "event_id": event_id,
                "event_type": str((row.event_type if row else "") or ""),
                "description": str((row.description if row else "") or "").strip(),
                "created_at": row.created_at.isoformat() if row and row.created_at else None,
            }
        )

    top_actors: list[dict[str, Any]] = []
    if tracked_agent_ids:
        action_count_expr = func.count(Event.id).label("action_count")
        top_actor_rows = (
            db.query(Event.agent_id, action_count_expr)
            .filter(
                Event.created_at >= since,
                Event.agent_id.in_(tracked_agent_ids),
            )
            .group_by(Event.agent_id)
            .order_by(action_count_expr.desc(), Event.agent_id.asc())
            .limit(3)
            .all()
        )
        for agent_id, action_count in top_actor_rows:
            agent = tracked_agents_by_id.get(int(agent_id))
            if agent is None:
                continue
            top_actors.append(
                {
                    "agent": agent,
                    "agent_number": int(agent.agent_number),
                    "display_name": _agent_label(agent),
                    "actions": int(action_count or 0),
                }
            )

    recent_laws: list[dict[str, Any]] = []
    if tracked_agent_ids:
        law_rows = (
            db.query(Law)
            .filter(
                Law.passed_at >= since,
                Law.author_agent_id.in_(tracked_agent_ids),
            )
            .order_by(Law.passed_at.desc(), Law.id.desc())
            .limit(3)
            .all()
        )
        for law in law_rows:
            author = tracked_agents_by_id.get(int(law.author_agent_id))
            recent_laws.append(
                {
                    "id": int(law.id),
                    "title": str(law.title or "").strip() or "Unnamed law",
                    "description": _truncate_text(law.description, limit=140),
                    "author": _agent_label(author),
                    "passed_at": law.passed_at.isoformat() if law.passed_at else None,
                }
            )

    recent_deaths: list[dict[str, Any]] = []
    recent_dormancies: list[dict[str, Any]] = []
    recent_revivals: list[dict[str, Any]] = []
    if tracked_agent_ids:
        fate_rows = (
            db.query(Event)
            .filter(
                Event.created_at >= since,
                Event.agent_id.in_(tracked_agent_ids),
                Event.event_type.in_(("agent_died", "became_dormant", "agent_revived")),
            )
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(20)
            .all()
        )
        for event in fate_rows:
            agent = tracked_agents_by_id.get(int(event.agent_id)) if event.agent_id is not None else None
            payload = {
                "event_id": int(event.id),
                "agent": agent,
                "agent_number": int(agent.agent_number) if agent is not None else None,
                "display_name": _agent_label(agent),
                "description": _truncate_text(event.description, limit=120),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            if event.event_type == "agent_died":
                recent_deaths.append(payload)
            elif event.event_type == "became_dormant":
                recent_dormancies.append(payload)
            elif event.event_type == "agent_revived":
                recent_revivals.append(payload)

    risk_watch: list[dict[str, Any]] = []
    if tracked_agent_ids:
        inventory_rows = (
            db.query(AgentInventory)
            .filter(AgentInventory.agent_id.in_(tracked_agent_ids))
            .all()
        )
        inventory_by_agent_id: dict[int, dict[str, float]] = {}
        for row in inventory_rows:
            agent_resources = inventory_by_agent_id.setdefault(int(row.agent_id), {})
            agent_resources[str(row.resource_type)] = float(row.quantity or 0)

        min_food = float(active_food_cost())
        min_energy = float(active_energy_cost())
        low_food = float(low_resource_warning_threshold(min_food))
        low_energy = float(low_resource_warning_threshold(min_energy))

        for agent in tracked_agents:
            if agent.status == "dead":
                continue
            resources = inventory_by_agent_id.get(int(agent.id), {})
            food = float(resources.get("food", 0.0))
            energy = float(resources.get("energy", 0.0))
            level = ""
            level_label = ""
            if agent.status == "dormant" or food < min_food or energy < min_energy:
                level = "critical"
                level_label = "At Risk"
            elif food < low_food or energy < low_energy:
                level = "elevated"
                level_label = "Exposed"
            if not level:
                continue
            risk_watch.append(
                {
                    "agent": agent,
                    "agent_number": int(agent.agent_number),
                    "display_name": _agent_label(agent),
                    "level": level,
                    "level_label": level_label,
                    "food": round(food, 2),
                    "energy": round(energy, 2),
                    "status": str(agent.status or "").strip() or "unknown",
                }
            )
        risk_watch.sort(
            key=lambda item: (
                0 if str(item.get("level")) == "critical" else 1,
                float(item.get("food") or 0.0) + float(item.get("energy") or 0.0),
                int(item.get("agent_number") or 0),
            )
        )

    return {
        "llm_calls": calls,
        "llm_success_calls": int((llm_totals.success_calls if llm_totals else 0) or 0),
        "llm_provider_model_fallback_calls": int(
            (llm_totals.provider_model_fallback_calls if llm_totals else 0) or 0
        ),
        "llm_fallback_calls": int((llm_totals.provider_model_fallback_calls if llm_totals else 0) or 0),
        "llm_total_tokens": int((llm_totals.total_tokens if llm_totals else 0) or 0),
        "llm_cost_usd": float((llm_totals.estimated_cost_usd if llm_totals else 0.0) or 0.0),
        "active_agents": int(active_agents or 0),
        "total_events": int((runtime_actions.total_events if runtime_actions else 0) or 0),
        "checkpoint_actions": int((runtime_actions.checkpoint_actions if runtime_actions else 0) or 0),
        "deterministic_forced_idle_actions": int(
            (runtime_actions.deterministic_forced_idle_actions if runtime_actions else 0) or 0
        ),
        "deterministic_routine_fallback_actions": int(
            (runtime_actions.deterministic_routine_fallback_actions if runtime_actions else 0) or 0
        ),
        "deterministic_actions": int(
            ((runtime_actions.deterministic_forced_idle_actions if runtime_actions else 0) or 0)
            + ((runtime_actions.deterministic_routine_fallback_actions if runtime_actions else 0) or 0)
        ),
        "proposal_actions": int((runtime_actions.proposal_actions if runtime_actions else 0) or 0),
        "vote_actions": int((runtime_actions.vote_actions if runtime_actions else 0) or 0),
        "forum_actions": int((runtime_actions.forum_actions if runtime_actions else 0) or 0),
        "laws_passed": int((runtime_actions.laws_passed if runtime_actions else 0) or 0),
        "deaths": int((runtime_actions.deaths if runtime_actions else 0) or 0),
        "verification_state": verification_state,
        "traces": normalized_traces,
        "top_actors": top_actors,
        "recent_laws": recent_laws,
        "recent_deaths": recent_deaths,
        "recent_dormancies": recent_dormancies,
        "recent_revivals": recent_revivals,
        "risk_watch": risk_watch[:3],
    }


def _base_run_links(*, run_id: str, hours_fallback: int) -> list[dict[str, str]]:
    safe_run_id = str(run_id).strip()
    run_ui_url = f"/runs/{safe_run_id}"
    run_api_url = (
        f"/api/analytics/runs/{safe_run_id}"
        f"?hours_fallback={int(hours_fallback)}&trace_limit=16&min_salience=55"
    )
    return [
        {"label": "Run Detail", "href": run_ui_url},
        {"label": "Run Evidence API", "href": run_api_url},
    ]


def _trace_link(trace: dict[str, Any], *, label_prefix: str) -> dict[str, str] | None:
    event_id = int(trace.get("event_id") or 0)
    if event_id <= 0:
        return None
    return {
        "label": f"{label_prefix} Event #{event_id}",
        "href": f"/api/events/{event_id}",
    }


def _first_trace_for_types(traces: list[dict[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
    for trace in traces:
        if str(trace.get("event_type") or "") in event_types:
            return trace
    return traces[0] if traces else None


def _merge_evidence_links(*link_groups: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in link_groups:
        for link in group:
            if not isinstance(link, dict):
                continue
            label = str(link.get("label") or "").strip()
            href = str(link.get("href") or "").strip()
            if not label or not href:
                continue
            key = (label, href)
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"label": label, "href": href})
    return deduped


def _claim_block(claim: str, evidence_links: list[dict[str, str]]) -> dict[str, Any]:
    normalized_links = [
        {"label": str(link.get("label") or "").strip(), "href": str(link.get("href") or "").strip()}
        for link in evidence_links
        if str(link.get("label") or "").strip() and str(link.get("href") or "").strip()
    ]
    if not normalized_links:
        raise ValueError("Every digest claim must include at least one evidence link")
    return {
        "claim": str(claim).strip(),
        "evidence_links": normalized_links,
    }


def _claims_to_archive_section(heading: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    claim_blocks = [
        {
            "claim": str(claim.get("claim") or "").strip(),
            "evidence_links": [
                {
                    "label": str(link.get("label") or "").strip(),
                    "href": str(link.get("href") or "").strip(),
                }
                for link in (claim.get("evidence_links") or [])
                if str(link.get("label") or "").strip() and str(link.get("href") or "").strip()
            ],
        }
        for claim in claims
        if str(claim.get("claim") or "").strip()
    ]
    if not claim_blocks:
        raise ValueError("Digest sections must include at least one claim block")

    references = _merge_evidence_links(
        *[list(block.get("evidence_links") or []) for block in claim_blocks]
    )
    return {
        "heading": heading,
        "paragraphs": [str(block["claim"]) for block in claim_blocks],
        "claim_blocks": claim_blocks,
        "references": references,
        "locked": True,
        "template_version": WEEKLY_DIGEST_TEMPLATE_VERSION,
    }


def _build_locked_sections(
    *,
    run_id: str,
    verification_state: str,
    window_start: datetime,
    window_end: datetime,
    snapshot: dict[str, Any],
    hours_fallback: int,
) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = list(snapshot.get("traces") or [])
    base_links = _base_run_links(run_id=run_id, hours_fallback=hours_fallback)

    participation_trace = _first_trace_for_types(traces, {"forum_post", "forum_reply"})
    governance_trace = _first_trace_for_types(traces, {"create_proposal", "vote", "law_passed"})
    survival_trace = _first_trace_for_types(traces, {"agent_died"})
    revival_trace = _first_trace_for_types(traces, {"agent_revived"})

    participation_links = _merge_evidence_links(
        base_links,
        [
            _trace_link(participation_trace, label_prefix="Participation")
            if participation_trace
            else None
        ],
    )
    governance_links = _merge_evidence_links(
        base_links,
        [
            _trace_link(governance_trace, label_prefix="Governance")
            if governance_trace
            else None
        ],
    )
    survival_links = _merge_evidence_links(
        base_links,
        [
            _trace_link(survival_trace, label_prefix="Survival")
            if survival_trace
            else None
        ],
    )
    recovery_links = _merge_evidence_links(
        base_links,
        [
            _trace_link(revival_trace, label_prefix="Recovery")
            if revival_trace
            else None
        ],
    )

    checkpoint_actions = int(snapshot.get("checkpoint_actions") or 0)
    deterministic_forced_idle_actions = int(snapshot.get("deterministic_forced_idle_actions") or 0)
    deterministic_routine_fallback_actions = int(
        snapshot.get("deterministic_routine_fallback_actions") or 0
    )
    deterministic_actions = deterministic_forced_idle_actions + deterministic_routine_fallback_actions
    total_runtime_actions = checkpoint_actions + deterministic_actions
    deterministic_share = (
        (deterministic_actions / total_runtime_actions)
        if total_runtime_actions > 0
        else 0.0
    )

    total_events = int(snapshot.get("total_events") or 0)
    confidence = _confidence_label(total_events)
    focus = _episode_focus(snapshot)
    top_actors = list(snapshot.get("top_actors") or [])
    recent_deaths = list(snapshot.get("recent_deaths") or [])
    recent_dormancies = list(snapshot.get("recent_dormancies") or [])
    recent_revivals = list(snapshot.get("recent_revivals") or [])
    recent_laws = list(snapshot.get("recent_laws") or [])
    risk_watch = list(snapshot.get("risk_watch") or [])

    top_actor_labels = _join_labels([str(item.get("display_name") or "") for item in top_actors[:2]])
    fall_labels = _join_labels(
        [str(item.get("display_name") or "") for item in (recent_deaths[:2] + recent_dormancies[:2])]
    )

    lead_law = recent_laws[0] if recent_laws else None
    law_links = _merge_evidence_links(
        governance_links,
        [
            {
                "label": f"Law #{int(lead_law.get('id') or 0)}",
                "href": f"/laws/{int(lead_law.get('id') or 0)}",
            }
            if lead_law and int(lead_law.get("id") or 0) > 0
            else None
        ],
    )

    risk_links = _merge_evidence_links(
        base_links,
        [
            {
                "label": f"Agent #{int(item.get('agent_number') or 0):02d}",
                "href": f"/agents/{int(item.get('agent_number') or 0)}",
            }
            for item in risk_watch
            if int(item.get("agent_number") or 0) > 0
        ],
    )
    actor_links = _merge_evidence_links(
        participation_links,
        [
            {
                "label": f"Agent #{int(item.get('agent_number') or 0):02d}",
                "href": f"/agents/{int(item.get('agent_number') or 0)}",
            }
            for item in top_actors
            if int(item.get("agent_number") or 0) > 0
        ],
    )

    sections: list[dict[str, Any]] = [
        _claims_to_archive_section(
            LOCKED_WEEKLY_DIGEST_HEADINGS[0],
            [
                _claim_block(
                    (
                        f"Window {window_start.date().isoformat()} to {window_end.date().isoformat()} UTC "
                        f"is attributed to run `{run_id}` with `{verification_state}` verification state."
                    ),
                    base_links,
                ),
                _claim_block(
                    (
                        f"Run telemetry recorded {int(snapshot.get('llm_calls') or 0):,} LLM calls "
                        f"({int(snapshot.get('llm_success_calls') or 0):,} successful)."
                    ),
                    base_links,
                ),
            ],
        ),
        _claims_to_archive_section(
            LOCKED_WEEKLY_DIGEST_HEADINGS[1],
            [
                _claim_block(
                    (
                        f"This window read most clearly as {focus}: "
                        f"{int(snapshot.get('total_events') or 0):,} run-scoped events, "
                        f"{int(snapshot.get('laws_passed') or 0):,} law-pass events, "
                        f"{int(snapshot.get('deaths') or 0):,} deaths, and "
                        f"{len(recent_dormancies):,} fresh dormancy signals."
                    ),
                    participation_links,
                ),
                _claim_block(
                    (
                        f"{int(snapshot.get('active_agents') or 0):,} distinct agents produced run-attributed model traffic, "
                        f"with {int(snapshot.get('forum_actions') or 0):,} forum actions and "
                        f"{int(snapshot.get('vote_actions') or 0):,} vote events shaping the public record."
                    ),
                    participation_links,
                ),
            ],
        ),
        _claims_to_archive_section(
            LOCKED_WEEKLY_DIGEST_HEADINGS[2],
            [
                _claim_block(
                    (
                        f"Who rose: {top_actor_labels or 'No single actor clearly dominated the window'}, "
                        f"driving the most visible action in the observed run traces."
                    ),
                    actor_links,
                ),
                _claim_block(
                    (
                        f"Who fell: {fall_labels or 'no major collapse event was recorded'}, "
                        "which marks the clearest loss of position in this window."
                    ),
                    survival_links,
                ),
            ],
        ),
        _claims_to_archive_section(
            LOCKED_WEEKLY_DIGEST_HEADINGS[3],
            [
                _claim_block(
                    (
                        f"The strongest system-level shift was "
                        f"\"{str(lead_law.get('title') or 'no decisive law') if lead_law else 'no decisive law'}\"."
                        + (
                            f" Proposed by {str(lead_law.get('author') or 'an unknown author')}, "
                            f"it landed with the public-facing consequence: {str(lead_law.get('description') or '').strip()}"
                            if lead_law
                            else f" Governance still generated {int(snapshot.get('proposal_actions') or 0):,} proposal events "
                            f"and {int(snapshot.get('vote_actions') or 0):,} votes, but no single rule change cleanly defined the week."
                        )
                    ),
                    law_links,
                ),
                _claim_block(
                    (
                        f"Recovery signals recorded {len(recent_revivals):,} revivals, while checkpoint actions accounted for "
                        f"{checkpoint_actions:,} of {total_runtime_actions:,} tracked runtime actions."
                    ),
                    recovery_links if recent_revivals else governance_links,
                ),
            ],
        ),
        _claims_to_archive_section(
            LOCKED_WEEKLY_DIGEST_HEADINGS[4],
            [
                _claim_block(
                    (
                        (
                            f"The next watchlist centers on {_join_labels([str(item.get('display_name') or '') for item in risk_watch[:2]])}: "
                            + "; ".join(
                                f"{str(item.get('display_name') or '')} at {str(item.get('level_label') or '').lower()} "
                                f"(food {float(item.get('food') or 0.0):.2f}, energy {float(item.get('energy') or 0.0):.2f})"
                                for item in risk_watch[:2]
                            )
                        )
                        if risk_watch
                        else "No agent is currently flashing a clear public risk signal from reserve levels alone."
                    ),
                    risk_links,
                ),
                _claim_block(
                    (
                        f"Digest confidence for this window is **{confidence}**; deterministic fallback share was "
                        f"{deterministic_share:.1%} ({deterministic_actions:,}/{total_runtime_actions:,} runtime actions), "
                        f"split across {deterministic_forced_idle_actions:,} forced idle actions and "
                        f"{deterministic_routine_fallback_actions:,} routine continuity actions."
                    ),
                    base_links,
                ),
            ],
        ),
    ]

    observed_headings = tuple(section.get("heading") for section in sections)
    if observed_headings != LOCKED_WEEKLY_DIGEST_HEADINGS:
        raise ValueError("Weekly digest locked template headings changed unexpectedly")

    for section in sections:
        for claim in section.get("claim_blocks") or []:
            if not list(claim.get("evidence_links") or []):
                raise ValueError("Every claim block must include at least one evidence link")

    return sections


def render_weekly_digest_markdown(
    *,
    anchor_date: date,
    run_id: str,
    verification_state: str,
    summary: str,
    sections: list[dict[str, Any]],
    generated_at: datetime,
) -> str:
    lines: list[str] = [
        f"# State of Emergence Weekly Digest - {anchor_date.isoformat()}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Verification: `{verification_state}`",
        f"- Template: `{WEEKLY_DIGEST_TEMPLATE_VERSION}`",
        f"- Generated (UTC): `{generated_at.isoformat()}`",
        "",
        f"> {summary}",
        "",
    ]

    for section in sections:
        heading = str(section.get("heading") or "").strip()
        if not heading:
            continue
        lines.append(f"## {heading}")
        lines.append("")

        claim_blocks = section.get("claim_blocks") or []
        for claim_block in claim_blocks:
            claim_text = str(claim_block.get("claim") or "").strip()
            evidence_links = claim_block.get("evidence_links") or []
            if not claim_text:
                continue
            lines.append(f"- Claim: {claim_text}")
            evidence_md = ", ".join(
                f"[{str(link.get('label')).strip()}]({str(link.get('href')).strip()})"
                for link in evidence_links
                if str(link.get("label") or "").strip() and str(link.get("href") or "").strip()
            )
            if evidence_md:
                lines.append(f"  Evidence: {evidence_md}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_weekly_digest_markdown(
    markdown: str,
    *,
    anchor_date: date,
    outdir: str | Path | None = None,
) -> str:
    if outdir is None:
        repo_root = Path(__file__).resolve().parents[3]
        output_dir = repo_root / "output" / "digests"
    else:
        output_dir = Path(outdir).expanduser().resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"state_of_emergence_{anchor_date.isoformat()}"
    path = output_dir / f"{base_name}.md"
    suffix = 2
    while path.exists():
        path = output_dir / f"{base_name}-{suffix}.md"
        suffix += 1

    path.write_text(markdown, encoding="utf-8")
    latest_path = output_dir / "state_of_emergence_latest.md"
    latest_path.write_text(markdown, encoding="utf-8")

    return str(path)


def build_weekly_digest(
    db: Session,
    *,
    lookback_days: int,
    anchor_date: date | None = None,
    now_ts: datetime | None = None,
    preferred_run_id: str | None = None,
    outdir: str | Path | None = None,
    enforce_minimum_evidence: bool = True,
    min_events: int = 1,
    min_llm_calls: int = 1,
) -> WeeklyDigestPayload:
    now_value = now_ts or now_utc()
    lookback = _bounded_int(lookback_days, fallback=7, minimum=1, maximum=30)
    since = now_value - timedelta(days=lookback)

    run_id = _resolve_run_id(db, preferred_run_id)
    snapshot = _collect_run_snapshot(db, run_id=run_id, since=since)
    verification_state = str(snapshot.get("verification_state") or "unverified")
    evidence_gate = evaluate_weekly_digest_evidence(
        snapshot=snapshot,
        min_events=min_events,
        min_llm_calls=min_llm_calls,
    )
    if enforce_minimum_evidence and not bool(evidence_gate.get("passed")):
        raise WeeklyDigestInsufficientEvidenceError(evidence_gate)
    hours_fallback = max(1, int(lookback * 24))

    sections = _build_locked_sections(
        run_id=run_id,
        verification_state=verification_state,
        window_start=since,
        window_end=now_value,
        snapshot=snapshot,
        hours_fallback=hours_fallback,
    )

    summary = _build_digest_summary(
        run_id=run_id,
        window_start=since,
        window_end=now_value,
        snapshot=snapshot,
    )

    digest_anchor = anchor_date or now_value.date()
    markdown = render_weekly_digest_markdown(
        anchor_date=digest_anchor,
        run_id=run_id,
        verification_state=verification_state,
        summary=summary,
        sections=sections,
        generated_at=now_value,
    )
    markdown_path = write_weekly_digest_markdown(markdown, anchor_date=digest_anchor, outdir=outdir)

    return WeeklyDigestPayload(
        run_id=run_id,
        verification_state=verification_state,
        window_start=since,
        window_end=now_value,
        summary=summary,
        sections=sections,
        markdown=markdown,
        markdown_path=markdown_path,
        evidence_gate=evidence_gate,
    )
