"""Helpers for interpreting active law effects."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import GlobalResources, Law
from app.services.live_run_scope import get_live_run_window
from app.services.survival_config import reserve_auto_contribution_enabled


SURVIVAL_RESERVE_CONTRIBUTION_BASE_RATES = {
    "food": Decimal("0.10"),
    "energy": Decimal("0.25"),
}
SURVIVAL_RESERVE_CONTRIBUTION_LOW_ENERGY_RATES = {
    "food": Decimal("0.05"),
    "energy": Decimal("0.40"),
}
SURVIVAL_RESERVE_LOW_ENERGY_THRESHOLD = Decimal("10.0")


def normalize_law_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_survival_reserve_law_value(*, title: str | None, description: str | None) -> bool:
    text = normalize_law_text(f"{title or ''} {description or ''}")
    reserve_equivalent = any(
        marker in text
        for marker in (
            "reserve",
            "common pool",
            "shared pool",
            "collective pool",
            "shared resource",
            "shared resources",
            "common resource",
            "common resources",
            "collective fund",
            "shared fund",
        )
    )
    if not reserve_equivalent:
        return False
    return any(
        keyword in text
        for keyword in ("survival", "shared", "aid", "dormant", "death", "contribution")
    )


def is_survival_reserve_law(law: Law) -> bool:
    return is_survival_reserve_law_value(title=law.title, description=law.description)


def active_survival_reserve_laws(db: Session) -> list[Law]:
    run_window = get_live_run_window(db)
    if run_window.run_id is None:
        return []

    query = db.query(Law).filter(Law.active.is_(True))
    if run_window.started_at is not None:
        query = query.filter(Law.passed_at >= run_window.started_at)
    if run_window.ended_at is not None:
        query = query.filter(Law.passed_at <= run_window.ended_at)

    active_laws = query.all()
    return [law for law in active_laws if is_survival_reserve_law(law)]


def survival_reserve_law_active(db: Session) -> bool:
    return bool(active_survival_reserve_laws(db))


def survival_reserve_contribution_rate(resource_type: str, *, energy_reserve: Decimal | None = None) -> Decimal:
    if not reserve_auto_contribution_enabled():
        return Decimal("0")
    normalized = str(resource_type or "").strip().lower()
    if energy_reserve is not None and Decimal(str(energy_reserve)) < SURVIVAL_RESERVE_LOW_ENERGY_THRESHOLD:
        return SURVIVAL_RESERVE_CONTRIBUTION_LOW_ENERGY_RATES.get(normalized, Decimal("0"))
    return SURVIVAL_RESERVE_CONTRIBUTION_BASE_RATES.get(normalized, Decimal("0"))


def current_energy_reserve(db: Session) -> Decimal:
    row = db.query(GlobalResources).filter(GlobalResources.resource_type == "energy").first()
    return Decimal(str(row.in_common_pool or 0)) if row else Decimal("0")
