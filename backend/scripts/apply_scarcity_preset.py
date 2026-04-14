"""Apply a named scarcity preset to runtime overrides and resource baselines."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.runtime_config import runtime_config_service
from app.services.scarcity_presets import get_scarcity_preset, list_scarcity_presets


def _apply_resource_targets(*, agent_targets: dict[str, float], pool_targets: dict[str, float]) -> dict[str, object]:
    db = SessionLocal()
    try:
        for resource_type, value in agent_targets.items():
            db.execute(
                text(
                    """
                    UPDATE agent_inventory
                    SET quantity = :quantity
                    WHERE resource_type = :resource_type
                    """
                ),
                {"resource_type": resource_type, "quantity": str(Decimal(str(value)))},
            )

        for resource_type, value in pool_targets.items():
            db.execute(
                text(
                    """
                    UPDATE global_resources
                    SET in_common_pool = :quantity,
                        total_amount = CASE
                            WHEN total_amount < :quantity THEN :quantity
                            ELSE total_amount
                        END
                    WHERE resource_type = :resource_type
                    """
                ),
                {"resource_type": resource_type, "quantity": str(Decimal(str(value)))},
            )

        db.execute(
            text(
                """
                UPDATE agents
                SET status = 'active',
                    starvation_cycles = 0,
                    died_at = NULL,
                    death_cause = NULL,
                    sanctioned_until = NULL,
                    exiled = FALSE
                """
            )
        )

        db.commit()
        return {
            "applied": True,
            "agent_resource_targets": {k: float(v) for k, v in agent_targets.items()},
            "common_pool_targets": {k: float(v) for k, v in pool_targets.items()},
            "agent_state_reset": True,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a named scarcity preset.")
    parser.add_argument("--preset", choices=[preset.name for preset in list_scarcity_presets()], required=True)
    parser.add_argument("--actor", default="scarcity-preset-cli")
    parser.add_argument("--reason", default=None)
    parser.add_argument("--skip-runtime-overrides", action="store_true")
    parser.add_argument("--skip-resource-reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    preset = get_scarcity_preset(args.preset)
    reason = str(args.reason or f"Apply scarcity preset {preset.name}")
    payload: dict[str, object] = {
        "preset": preset.name,
        "description": preset.description,
        "recommended_run_class": preset.recommended_run_class,
    }

    if args.dry_run:
        payload["dry_run"] = True
        payload["runtime_overrides"] = dict(preset.runtime_overrides)
        payload["agent_resource_targets"] = dict(preset.agent_resource_targets)
        payload["common_pool_targets"] = dict(preset.common_pool_targets)
        print(json.dumps(payload, indent=2))
        return

    if not args.skip_runtime_overrides:
        db = SessionLocal()
        try:
            payload["runtime"] = runtime_config_service.update_settings(
                db,
                dict(preset.runtime_overrides),
                changed_by=str(args.actor),
                reason=reason,
            )
        finally:
            db.close()

    if not args.skip_resource_reset:
        payload["resources"] = _apply_resource_targets(
            agent_targets=preset.agent_resource_targets,
            pool_targets=preset.common_pool_targets,
        )

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
