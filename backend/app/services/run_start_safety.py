"""Safety checks for starting new simulation runs."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.models import Agent, Law, Proposal, SimulationRun


class RunStartSafetyError(ValueError):
    """Raised when a new run would start from an invalid world state."""


@dataclass(frozen=True)
class WorldStartSnapshot:
    dead_agents: int
    dormant_agents: int
    starving_agents: int
    active_proposals: int
    active_laws: int

    def is_dirty(self) -> bool:
        return any(
            value > 0
            for value in (
                self.dead_agents,
                self.dormant_agents,
                self.starving_agents,
            )
        )


def collect_world_start_snapshot(db: Session) -> WorldStartSnapshot:
    dead_agents = int(
        db.query(Agent)
        .filter((Agent.status == "dead") | Agent.died_at.isnot(None))
        .count()
        or 0
    )
    dormant_agents = int(
        db.query(Agent)
        .filter(Agent.status == "dormant")
        .count()
        or 0
    )
    starving_agents = int(
        db.query(Agent)
        .filter(Agent.starvation_cycles > 0)
        .count()
        or 0
    )
    active_proposals = int(
        db.query(Proposal)
        .filter(Proposal.status == "active")
        .count()
        or 0
    )
    active_laws = int(
        db.query(Law)
        .filter(Law.active.is_(True))
        .count()
        or 0
    )

    return WorldStartSnapshot(
        dead_agents=dead_agents,
        dormant_agents=dormant_agents,
        starving_agents=starving_agents,
        active_proposals=active_proposals,
        active_laws=active_laws,
    )


def assert_new_run_startable(db: Session, *, run_id: str) -> WorldStartSnapshot:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        raise RunStartSafetyError("run_id is required")

    existing = (
        db.query(SimulationRun)
        .filter(SimulationRun.run_id == clean_run_id)
        .first()
    )
    if existing is not None:
        raise RunStartSafetyError(
            f"run_id `{clean_run_id}` already exists; starting a new run requires a fresh run_id."
        )

    snapshot = collect_world_start_snapshot(db)
    if not snapshot.is_dirty():
        return snapshot

    issues: list[str] = []
    if snapshot.dead_agents > 0:
        issues.append(f"{snapshot.dead_agents} dead agents")
    if snapshot.dormant_agents > 0:
        issues.append(f"{snapshot.dormant_agents} dormant agents")
    if snapshot.starving_agents > 0:
        issues.append(f"{snapshot.starving_agents} agents with starvation counters")
    issue_text = ", ".join(issues) if issues else "dirty world state"
    raise RunStartSafetyError(
        f"Cannot start run `{clean_run_id}` from existing world state: {issue_text}. "
        "Reset/reseed or run an explicit transfer workflow before starting a new run."
    )
