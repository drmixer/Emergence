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
from app.models.models import Agent, AgentInventory, GlobalResources, Transaction

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


@router.get("")
def get_resources(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Global resource totals and common pool (if available)."""
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
    }


@router.get("/distribution")
def get_resource_distribution(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Per-agent resource breakdown plus inequality metrics (Gini)."""
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
    }


@router.get("/history")
def get_resource_history(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Time series derived from transactions (production/consumption only).
    Trades/transfers are excluded from global net change.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

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

    return {"from": start.isoformat(), "to": now.isoformat(), "series": series}

