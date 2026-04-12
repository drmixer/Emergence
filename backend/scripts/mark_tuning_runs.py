"""Mark existing simulation runs as tuning runs."""

from __future__ import annotations

import argparse
import json

from app.core.database import SessionLocal
from app.models.models import SimulationRun


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark existing simulation runs as tuning runs.")
    parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    parser.add_argument("--condition-contains", action="append", dest="condition_fragments", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(SimulationRun)
        rows = query.order_by(SimulationRun.started_at.desc(), SimulationRun.id.desc()).all()
        selected = []
        fragments = [str(item).strip().lower() for item in (args.condition_fragments or []) if str(item).strip()]
        run_ids = {str(item).strip() for item in (args.run_ids or []) if str(item).strip()}

        for row in rows:
            condition_name = str(row.condition_name or "").strip().lower()
            if row.run_id in run_ids or any(fragment in condition_name for fragment in fragments):
                selected.append(row)

        payload = {
            "count": len(selected),
            "run_ids": [row.run_id for row in selected],
        }
        if args.dry_run:
            print(json.dumps(payload, indent=2))
            return

        for row in selected:
            row.protocol_deviation = True
            row.deviation_reason = "tuning_run"
            db.add(row)
        db.commit()
        print(json.dumps(payload, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
