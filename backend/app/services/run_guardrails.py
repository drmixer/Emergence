"""Runtime stop-condition guardrails for worker safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.core.time import now_utc
from app.models.models import Event, SimulationRun
from app.services.run_reports import maybe_generate_run_closeout_bundle
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StopDecision:
    should_stop: bool
    reason: str | None = None
    details: dict[str, Any] | None = None


class RunGuardrailService:
    """
    Evaluate and enforce runtime stop conditions.

    Stop conditions:
    - hard budget breach
    - repeated provider failures in recent window
    - sustained DB pool exhaustion pressure
    """

    def __init__(self) -> None:
        self._db_pressure_streak = 0

    def evaluate(self) -> StopDecision:
        if not bool(
            runtime_config_service.get_effective_value_cached(
                "STOP_CONDITION_ENFORCEMENT_ENABLED"
            )
        ):
            self._db_pressure_streak = 0
            return StopDecision(False)

        if bool(runtime_config_service.get_effective_value_cached("SIMULATION_PAUSED")):
            return StopDecision(False)
        if not bool(
            runtime_config_service.get_effective_value_cached("SIMULATION_ACTIVE")
        ):
            return StopDecision(False)

        budget_decision = self._check_budget_hard_stop()
        if budget_decision.should_stop:
            return budget_decision

        scheduled_stop_decision = self._check_scheduled_stop()
        if scheduled_stop_decision.should_stop:
            return scheduled_stop_decision

        provider_decision = self._check_provider_failures()
        if provider_decision.should_stop:
            return provider_decision

        db_pool_decision = self._check_db_pool_pressure()
        if db_pool_decision.should_stop:
            return db_pool_decision

        return StopDecision(False)

    def evaluate_and_enforce(self) -> StopDecision:
        decision = self.evaluate()
        if decision.should_stop:
            self._enforce_stop(decision)
        return decision

    @staticmethod
    def _check_budget_hard_stop() -> StopDecision:
        hard_budget = float(
            runtime_config_service.get_effective_value_cached(
                "LLM_DAILY_BUDGET_USD_HARD"
            )
            or 0.0
        )
        if hard_budget <= 0:
            return StopDecision(False)

        snapshot = usage_budget.get_snapshot()
        if float(snapshot.estimated_cost_usd) > hard_budget:
            details = {
                "day_key": snapshot.day_key.isoformat(),
                "estimated_cost_usd": float(snapshot.estimated_cost_usd),
                "hard_budget_usd": hard_budget,
            }
            return StopDecision(True, "hard_budget_exceeded", details)
        return StopDecision(False)

    @staticmethod
    def _parse_scheduled_stop_at(raw_value: Any) -> datetime | None:
        text_value = str(raw_value or "").strip()
        if not text_value:
            return None
        normalized = text_value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            logger.warning("Ignoring invalid SIMULATION_AUTO_STOP_AT value: %s", text_value)
            return None
        if parsed.tzinfo is None:
            logger.warning("Ignoring naive SIMULATION_AUTO_STOP_AT value: %s", text_value)
            return None
        return parsed.astimezone(timezone.utc)

    def _check_scheduled_stop(self) -> StopDecision:
        stop_at = self._parse_scheduled_stop_at(
            runtime_config_service.get_effective_value_cached("SIMULATION_AUTO_STOP_AT")
        )
        scheduled_run_id = str(
            runtime_config_service.get_effective_value_cached("SIMULATION_AUTO_STOP_RUN_ID") or ""
        ).strip()
        if stop_at is None or not scheduled_run_id:
            return StopDecision(False)

        current_run_id = str(
            runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or ""
        ).strip()
        if current_run_id and current_run_id != scheduled_run_id:
            self._clear_scheduled_stop(
                reason="scheduled_stop_stale_run_mismatch",
                details={
                    "scheduled_run_id": scheduled_run_id,
                    "active_run_id": current_run_id,
                    "scheduled_stop_at": stop_at.isoformat(),
                },
            )
            return StopDecision(False)

        current_time = now_utc()
        if current_time < stop_at:
            return StopDecision(False)

        details = {
            "scheduled_run_id": scheduled_run_id,
            "active_run_id": current_run_id or None,
            "scheduled_stop_at": stop_at.isoformat(),
            "checked_at": current_time.isoformat(),
        }
        return StopDecision(True, "scheduled_stop_reached", details)

    @staticmethod
    def _check_provider_failures() -> StopDecision:
        threshold = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_PROVIDER_FAILURE_THRESHOLD"
            )
            or 0
        )
        failure_rate_threshold = float(
            runtime_config_service.get_effective_value_cached(
                "STOP_PROVIDER_FAILURE_RATE_THRESHOLD"
            )
            or 0.0
        )
        window_minutes = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_PROVIDER_FAILURE_WINDOW_MINUTES"
            )
            or 0
        )
        if threshold <= 0 or window_minutes <= 0:
            return StopDecision(False)

        since_ts = now_utc() - timedelta(minutes=window_minutes)
        current_run_id = str(
            runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or ""
        ).strip()
        db = SessionLocal()
        try:
            params: dict[str, Any] = {"since_ts": since_ts}
            where_clauses = ["created_at >= :since_ts"]
            if current_run_id:
                where_clauses.append("run_id = :run_id")
                params["run_id"] = current_run_id
            row = db.execute(
                text(
                    f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN success THEN 1 ELSE 0 END), 0) AS success_count,
                        COALESCE(SUM(CASE WHEN success THEN 0 ELSE 1 END), 0) AS failure_count
                    FROM llm_usage
                    WHERE {' AND '.join(where_clauses)}
                    """
                ),
                params,
            ).first()
        except Exception as exc:
            logger.warning("Provider-failure stop check unavailable: %s", exc)
            return StopDecision(False)
        finally:
            db.close()

        successes = int((row.success_count if row else 0) or 0)
        failures = int((row.failure_count if row else 0) or 0)
        if failures < threshold:
            return StopDecision(False)

        total = successes + failures
        failure_rate = (failures / total) if total > 0 else 1.0
        if failure_rate < failure_rate_threshold:
            return StopDecision(False)
        details = {
            "run_id": current_run_id or None,
            "window_minutes": window_minutes,
            "failure_threshold": threshold,
            "failure_rate_threshold": round(failure_rate_threshold, 4),
            "failures": failures,
            "successes": successes,
            "failure_rate": round(failure_rate, 4),
        }
        return StopDecision(True, "provider_failures_repeated", details)

    def _check_db_pool_pressure(self) -> StopDecision:
        threshold = float(
            runtime_config_service.get_effective_value_cached(
                "STOP_DB_POOL_UTILIZATION_THRESHOLD"
            )
            or 0.0
        )
        required_checks = int(
            runtime_config_service.get_effective_value_cached(
                "STOP_DB_POOL_CONSECUTIVE_CHECKS"
            )
            or 0
        )
        if threshold <= 0 or required_checks <= 0:
            self._db_pressure_streak = 0
            return StopDecision(False)

        pool = getattr(engine, "pool", None)
        if pool is None or not hasattr(pool, "checkedout") or not hasattr(pool, "size"):
            self._db_pressure_streak = 0
            return StopDecision(False)

        checked_out = max(0, int(pool.checkedout()))
        base_size = max(1, int(pool.size()))
        max_overflow = int(getattr(pool, "_max_overflow", 0))
        if max_overflow < 0:
            capacity = max(base_size, checked_out)
        else:
            capacity = max(1, base_size + max_overflow)
        utilization = checked_out / capacity

        if utilization >= threshold:
            self._db_pressure_streak += 1
        else:
            self._db_pressure_streak = 0
            return StopDecision(False)

        if self._db_pressure_streak < required_checks:
            return StopDecision(False)

        details = {
            "checked_out": checked_out,
            "capacity": capacity,
            "utilization": round(utilization, 4),
            "utilization_threshold": threshold,
            "consecutive_checks_required": required_checks,
            "consecutive_checks_observed": self._db_pressure_streak,
        }
        return StopDecision(True, "db_pool_pressure", details)

    @staticmethod
    def _mark_run_registry_stop(*, db, run_id: str, reason: str) -> None:
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            return
        row = db.query(SimulationRun).filter(SimulationRun.run_id == clean_run_id).first()
        if row is None:
            return
        row.ended_at = now_utc()
        row.end_reason = reason
        db.add(row)

    @staticmethod
    def _clear_scheduled_stop(*, reason: str, details: dict[str, Any] | None = None) -> None:
        db = SessionLocal()
        try:
            runtime_config_service.update_settings(
                db,
                {
                    "SIMULATION_AUTO_STOP_AT": "",
                    "SIMULATION_AUTO_STOP_RUN_ID": "",
                },
                changed_by="system:guardrail",
                reason=reason,
            )
            if details:
                db.add(
                    Event(
                        event_type="simulation_stop_schedule_cleared",
                        description="Cleared stale simulation auto-stop schedule",
                        event_metadata={"reason": reason, "details": details},
                    )
                )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to clear scheduled stop override: %s", exc)
        finally:
            db.close()

    @staticmethod
    def _enforce_stop(decision: StopDecision) -> None:
        reason = decision.reason or "unknown_stop_condition"
        if reason == "scheduled_stop_reached":
            reason_text = "Scheduled stop reached"
            run_end_reason = "Scheduled stop via run_guardrails"
        else:
            reason_text = f"Stop condition tripped: {reason}"
            run_end_reason = reason_text
        run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip()
        condition_name = str(runtime_config_service.get_effective_value_cached("SIMULATION_CONDITION_NAME") or "").strip()
        season_number = int(runtime_config_service.get_effective_value_cached("SIMULATION_SEASON_NUMBER") or 0)
        metadata = {
            "reason": reason,
            "details": decision.details or {},
            "triggered_at": now_utc().isoformat(),
            "run_id": run_id or None,
            "condition_name": condition_name or None,
            "season_number": (season_number if season_number > 0 else None),
        }

        db = SessionLocal()
        try:
            try:
                runtime_config_service.update_settings(
                    db,
                    {
                        "SIMULATION_ACTIVE": False,
                        "SIMULATION_PAUSED": True,
                        "SIMULATION_AUTO_STOP_AT": "",
                        "SIMULATION_AUTO_STOP_RUN_ID": "",
                    },
                    changed_by="system:guardrail",
                    reason=reason_text,
                )
            except Exception as exc:
                db.rollback()
                logger.error(
                    "Failed to persist runtime stop overrides for guardrail: %s", exc
                )

            if run_id:
                try:
                    RunGuardrailService._mark_run_registry_stop(
                        db=db,
                        run_id=run_id,
                        reason=run_end_reason,
                    )
                except Exception as exc:
                    db.rollback()
                    logger.error("Failed to mark run registry stop for guardrail: %s", exc)

            db.add(
                Event(
                    event_type="simulation_stopped_guardrail",
                    description=reason_text,
                    event_metadata=metadata,
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Failed to persist guardrail stop event: %s", exc)
        finally:
            db.close()

        if run_id:
            maybe_generate_run_closeout_bundle(
                run_id=run_id,
                actor_id="system:guardrail",
                condition_name=(condition_name or None),
                season_number=(season_number if season_number > 0 else None),
            )

        logger.error(
            "Simulation stop condition triggered (%s): %s",
            reason,
            decision.details or {},
        )


run_guardrail_service = RunGuardrailService()
