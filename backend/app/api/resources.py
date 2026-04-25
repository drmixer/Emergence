"""
Resources API Router
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Agent, AgentInventory, Event, GlobalResources, Transaction
from app.services.live_run_scope import apply_live_run_window, get_live_run_window

router = APIRouter()


RESOURCE_TYPES = ("food", "energy", "materials", "land")


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _gini(values: List[float]) -> float:
    xs = [v for v in values if v is not None]
    if not xs:
        return 0.0
    xs = sorted(max(0.0, float(v)) for v in xs)
    n = len(xs)
    total = sum(xs)
    if total == 0 or n == 0:
        return 0.0
    cum = 0.0
    for i, x in enumerate(xs, start=1):
        cum += i * x
    return (2.0 * cum) / (n * total) - (n + 1.0) / n


def _event_runtime_run_id(event: Event) -> str:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    runtime = metadata.get("runtime") if isinstance(metadata, dict) else {}
    return str((runtime or {}).get("run_id") or "").strip()


def _event_action(event: Event) -> dict:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    action = metadata.get("action") if isinstance(metadata, dict) else {}
    return action if isinstance(action, dict) else {}


def _agent_label(agent: Agent | None) -> dict[str, Any] | None:
    if agent is None:
        return None
    return {
        "id": int(agent.id),
        "agent_number": int(agent.agent_number),
        "display_name": agent.display_name,
        "tier": int(agent.tier or 0),
        "personality_type": str(agent.personality_type or ""),
        "status": str(agent.status or ""),
    }


@router.get("")
def get_resources(
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Global resource totals and common pool (if available)."""
    run_window = get_live_run_window(db)
    if scope != "all" and run_window.run_id is None:
        return {
            "totals": {r: 0.0 for r in RESOURCE_TYPES},
            "common_pool": {r: 0.0 for r in RESOURCE_TYPES},
            "agent_count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": "inactive",
            "simulation_active": False,
        }

    totals = {r: 0.0 for r in RESOURCE_TYPES}
    rows = (
        db.query(AgentInventory.resource_type, func.sum(AgentInventory.quantity))
        .group_by(AgentInventory.resource_type)
        .all()
    )
    for resource_type, total in rows:
        totals[str(resource_type)] = _to_float(total)

    common_pool = {r: 0.0 for r in RESOURCE_TYPES}
    gr_rows = db.query(GlobalResources).all()
    for gr in gr_rows:
        common_pool[str(gr.resource_type)] = _to_float(gr.in_common_pool)

    return {
        "totals": totals,
        "common_pool": common_pool,
        "agent_count": db.query(Agent).count(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": "all" if scope == "all" else "active_run",
        "simulation_active": True if scope == "all" else run_window.run_id is not None,
    }


@router.get("/distribution")
def get_resource_distribution(
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Per-agent resource breakdown plus inequality metrics (Gini)."""
    run_window = get_live_run_window(db)
    if scope != "all" and run_window.run_id is None:
        return {
            "distribution": [],
            "gini": {
                "total_wealth": 0.0,
                **{r: 0.0 for r in RESOURCE_TYPES},
            },
            "scope": "inactive",
            "simulation_active": False,
        }

    agents = db.query(Agent).order_by(Agent.agent_number).all()
    inventories = db.query(AgentInventory).all()

    by_agent: Dict[int, Dict[str, float]] = defaultdict(
        lambda: {r: 0.0 for r in RESOURCE_TYPES}
    )
    for inv in inventories:
        by_agent[int(inv.agent_id)][str(inv.resource_type)] = _to_float(inv.quantity)

    items: list[dict] = []
    total_wealth_values: list[float] = []
    per_resource_values: Dict[str, List[float]] = {r: [] for r in RESOURCE_TYPES}

    for agent in agents:
        resources = by_agent[int(agent.id)]
        total_wealth = sum(resources.values())
        total_wealth_values.append(total_wealth)
        for r in RESOURCE_TYPES:
            per_resource_values[r].append(resources.get(r, 0.0))

        items.append(
            {
                "agent_number": agent.agent_number,
                "display_name": agent.display_name,
                "status": agent.status,
                "resources": resources,
                "total_wealth": total_wealth,
            }
        )

    return {
        "distribution": items,
        "gini": {
            "total_wealth": _gini(total_wealth_values),
            **{r: _gini(vals) for r, vals in per_resource_values.items()},
        },
        "scope": "all" if scope == "all" else "active_run",
        "simulation_active": True if scope == "all" else run_window.run_id is not None,
    }


@router.get("/aid-lifecycle")
def get_aid_lifecycle(
    limit: int = Query(100, ge=1, le=300),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Request -> response trace for direct aid requests in the current run window."""
    run_window = get_live_run_window(db)
    if scope != "all" and run_window.run_id is None:
        return {
            "scope": "inactive",
            "run_id": None,
            "total": 0,
            "status_counts": {
                "fulfilled_by_trade": 0,
                "refused": 0,
                "reserve_covered": 0,
                "mechanically_unaffordable": 0,
                "unresolved": 0,
            },
            "items": [],
        }

    query = db.query(Event).filter(Event.event_type == "request_aid").order_by(Event.created_at.desc())
    if scope != "all":
        query = apply_live_run_window(query, Event.created_at, run_window)
    requests = query.limit(limit).all()

    agent_ids = {int(event.agent_id) for event in requests if event.agent_id is not None}
    target_numbers: set[int] = set()
    for event in requests:
        target_number = int(_event_action(event).get("target_agent_id") or 0)
        if target_number > 0:
            target_numbers.add(target_number)

    agents_by_id = {
        int(agent.id): agent
        for agent in db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
    } if agent_ids else {}
    targets_by_number = {
        int(agent.agent_number): agent
        for agent in db.query(Agent).filter(Agent.agent_number.in_(target_numbers)).all()
    } if target_numbers else {}

    run_id = str(run_window.run_id or "").strip()
    all_trace_events_query = db.query(Event).filter(
        Event.event_type.in_(("trade", "refuse_aid", "reserve_aid", "reserve_shortfall", "became_dormant"))
    )
    if scope != "all":
        all_trace_events_query = apply_live_run_window(all_trace_events_query, Event.created_at, run_window)
    all_trace_events = all_trace_events_query.order_by(Event.created_at.asc(), Event.id.asc()).all()
    if run_id:
        all_trace_events = [
            event for event in all_trace_events
            if _event_runtime_run_id(event) in {"", run_id}
        ]

    items: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {
        "fulfilled_by_trade": 0,
        "refused": 0,
        "reserve_covered": 0,
        "mechanically_unaffordable": 0,
        "unresolved": 0,
    }

    for request in requests:
        requester = agents_by_id.get(int(request.agent_id or 0))
        action = _event_action(request)
        target_number = int(action.get("target_agent_id") or 0)
        target = targets_by_number.get(target_number)
        requester_number = int(requester.agent_number) if requester else 0
        target_id = int(target.id) if target else 0
        request_at = request.created_at

        first_trade = None
        first_refusal = None
        first_reserve = None
        first_unaffordable = None
        for event in all_trace_events:
            if request_at and event.created_at and event.created_at < request_at:
                continue
            trace_action = _event_action(event)
            if event.event_type == "trade":
                if int(event.agent_id or 0) == target_id and int(trace_action.get("recipient_agent_id") or 0) == requester_number:
                    first_trade = first_trade or event
            elif event.event_type == "refuse_aid":
                if int(event.agent_id or 0) == target_id and int(trace_action.get("target_agent_id") or 0) == requester_number:
                    first_refusal = first_refusal or event
            elif event.event_type == "reserve_aid":
                if int(event.agent_id or 0) == int(request.agent_id or 0):
                    first_reserve = first_reserve or event
            elif event.event_type in {"reserve_shortfall", "became_dormant"}:
                if int(event.agent_id or 0) == target_id:
                    first_unaffordable = first_unaffordable or event

        first_response = sorted(
            [event for event in (first_trade, first_refusal, first_reserve, first_unaffordable) if event is not None],
            key=lambda event: (event.created_at, event.id),
        )
        response = first_response[0] if first_response else None
        if response is first_trade:
            status = "fulfilled_by_trade"
        elif response is first_refusal:
            status = "refused"
        elif response is first_reserve:
            status = "reserve_covered"
        elif response is first_unaffordable:
            status = "mechanically_unaffordable"
        else:
            status = "unresolved"
        status_counts[status] += 1

        items.append(
            {
                "request_event_id": int(request.id),
                "request_at": request.created_at.isoformat() if request.created_at else None,
                "requester": _agent_label(requester),
                "target": _agent_label(target),
                "resource_type": str(action.get("resource_type") or ""),
                "amount": str(action.get("amount") or ""),
                "reason": str(action.get("reason") or "").strip(),
                "status": status,
                "response_event_id": int(response.id) if response else None,
                "response_event_type": str(response.event_type) if response else None,
                "response_at": response.created_at.isoformat() if response and response.created_at else None,
                "request_description": request.description,
                "response_description": response.description if response else None,
            }
        )

    return {
        "scope": "active_run" if scope != "all" else "all",
        "run_id": run_id or None,
        "total": len(items),
        "status_counts": status_counts,
        "items": items,
    }


@router.get("/history")
def get_resource_history(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("active_run", description="active_run|all"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Time series derived from transactions (production/consumption only).
    Trades/transfers are excluded from global net change.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    run_window = get_live_run_window(db)
    if scope != "all":
        if run_window.run_id is None:
            return {"from": start.isoformat(), "to": now.isoformat(), "series": [], "scope": "inactive", "simulation_active": False}
        if run_window.started_at is not None:
            start = run_window.started_at
        if run_window.ended_at is not None and run_window.ended_at < now:
            now = run_window.ended_at

    production_types = ("work_production", "awakening", "initial_distribution")
    consumption_types = (
        "consumption",
        "survival_consumption",
        "dormant_survival",
        "action_cost",
        "building",
    )

    day = func.date(Transaction.created_at).label("day")
    produced = func.sum(
        case((Transaction.transaction_type.in_(production_types), Transaction.amount), else_=0)
    ).label("produced")
    consumed = func.sum(
        case((Transaction.transaction_type.in_(consumption_types), Transaction.amount), else_=0)
    ).label("consumed")

    rows = (
        db.query(day, Transaction.resource_type, produced, consumed)
        .filter(Transaction.created_at >= start)
        .group_by(day, Transaction.resource_type)
        .order_by(day.asc())
        .all()
    )

    series = []
    for d, resource_type, p, c in rows:
        produced_f = _to_float(p)
        consumed_f = _to_float(c)
        series.append(
            {
                "day": str(d),
                "resource_type": str(resource_type),
                "produced": produced_f,
                "consumed": consumed_f,
                "net": produced_f - consumed_f,
            }
        )

    return {
        "from": start.isoformat(),
        "to": now.isoformat(),
        "series": series,
        "scope": "all" if scope == "all" else "active_run",
        "simulation_active": True if scope == "all" else run_window.run_id is not None,
    }
