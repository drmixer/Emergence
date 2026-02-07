# Map Feature Gate (Phase 1)

## Current Decision
- Decision date: 2026-02-07 (UTC)
- Decision: **NO-GO (defer Phase 1 map visuals)**
- Reason: retention/engagement proxy data is below gate thresholds and D7 sample size is insufficient.

Phase 1 map should not block launch readiness. Re-evaluate weekly until thresholds pass.

## Measurable Gate Criteria
All criteria must pass in the same weekly check:

- `distinct_bettors_7d >= 10`
- `total_bets_7d >= 30`
- `active_users_7d >= 10`
- `d7_cohort_size >= 10`
- `d7_retention >= 0.20`

Retention proxies currently use existing prediction-market interaction tables:
- `prediction_bets`
- `user_points.last_active_at`

## Reproducible Check Command
Run from `/Users/drmixer/code/Emergence/backend`:

```bash
./venv/bin/python scripts/evaluate_map_gate.py
```

Artifacts:
- `output/launch_readiness/map_gate_latest.json`
- `output/launch_readiness/map_gate_<timestamp>.json`

## Trigger Conditions To Flip To GO
Switch to **GO** only when:

- All measurable criteria above pass in a check, and
- The same pass is repeated in a second weekly check (to avoid one-off spikes).

If GO is reached, implement only Phase 1 visuals first:
- region model + agent region assignment
- overlays for resource pressure and conflict intensity
- no location-aware mechanics until Phase 1 impact is validated
