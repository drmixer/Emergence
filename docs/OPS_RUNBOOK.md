# Ops Runbook (`/ops`)

## Purpose
Use `/ops` to control simulation runs in dev and inspect runtime health/metrics in both dev and prod.

## Preconditions
- You have a valid `ADMIN_API_TOKEN`.
- Your source IP is allowlisted by backend `ADMIN_IP_ALLOWLIST` (dev/prod as applicable).
- For write actions, backend `ADMIN_WRITE_ENABLED=true` in that environment.

## Environment Expectations
- `DEVELOPMENT`:
  - Write actions enabled.
  - Start/stop/pause/resume/reset controls available.
- `PRODUCTION`:
  - Expected read-only (`ADMIN_WRITE_ENABLED=false`).
  - UI disables unsafe start/reset actions.
  - Guardrail: write endpoints should return `403`.

## Standard Dev Operator Flow
1. Open `/ops`.
2. Enter:
   - `Admin token`
   - `Actor name`
3. Click `Connect`.
4. Confirm banner shows `DEVELOPMENT` and `Write controls enabled`.
5. In **Run Controls**:
   - Optional: set `Run ID`.
   - Optional: set `Run reason`.
   - For clean test runs, leave `Reset + reseed world before test start` enabled.
6. Click `Start Test Run` and confirm the prompt.
7. Validate in **Status**:
   - `Simulation active = yes`
   - `Paused = no`
   - `Run ID` matches expected.
8. Validate in **Run Metrics** (after a short wait + refresh):
   - `Runtime actions` > 0 as activity begins.
   - `Proposal actions`, `Vote actions`, `Forum actions` counters are present.
9. Validate in **KPI Rollups**:
   - Latest day row is present.
   - Funnel rates are populated (`Landing -> Run CTR`, `Run -> Replay Start`, `Replay Completion`).
   - Alert panel behavior:
     - `KPI Alerts` shows `critical` / `warning` counts when drop-offs breach thresholds.
     - Alerts are based on latest day values and 7-day averages for `Landing -> Run CTR`, `Replay Completion`, `D1`, `D7`.
     - D1/D7 alerts are gated on mature cohorts (minimum cohort size) to avoid early false positives.
     - Optional webhook delivery for critical alerts:
       - `KPI_ALERT_WEBHOOK_ENABLED=true`
       - `KPI_ALERT_WEBHOOK_URL=https://...`
       - `KPI_ALERT_NOTIFY_COOLDOWN_MINUTES=60` (dedupe window for identical alert payloads).
   - Retention fields (`D1`, `D7`) show `n/a` for immature cohorts and percentages once cohort windows complete.
10. When done, click `Stop Run` and confirm:
   - `Paused = yes`.
11. If you need a clean world, click `Reset Dev World` and confirm:
    - Success notice: `Dev world reset + reseeded`.

## Baseline Snapshot Capture
Run this before major tuning changes and after major rollout changes:

```bash
cd backend
./venv/bin/python scripts/capture_baseline.py --windows 24 --window-minutes 5
```

Expected outputs:
- `output/baseline/baseline_latest.json`
- `output/baseline/metrics/metrics_latest.json`

These include:
- active budget + stop-condition thresholds
- current daily LLM spend/call counters
- recent provider failure rate
- rolling emergence metrics windows

## Weekly Digest Generation
Generate the Milestone 3 weekly digest (locked template + run-backed evidence links):

```bash
cd backend
./venv/bin/python scripts/generate_weekly_digest.py --lookback-days 7
```

Optional flags:
- `--anchor-date YYYY-MM-DD` to pin the digest date.
- `--print-markdown` to print the publish-ready markdown in terminal.
- `--allow-duplicate-anchor` to create a second draft for the same week.

Evidence gate:
- Draft creation is skipped when minimum evidence is not met.
- Control thresholds via `ARCHIVE_WEEKLY_DRAFT_MIN_EVENTS` and `ARCHIVE_WEEKLY_DRAFT_MIN_LLM_CALLS` (defaults: `25` and `5`).
- API/CLI responses return `status=insufficient_evidence` with observed vs required counts.

## Runtime Stop Conditions
Worker guardrails stop a run when any of these trip:
- hard budget exceeded (`LLM_DAILY_BUDGET_USD_HARD`)
- repeated provider failures in trailing window (`STOP_PROVIDER_FAILURE_*`)
- sustained DB pool pressure (`STOP_DB_POOL_*`)

Enforcement behavior:
- writes runtime overrides: `SIMULATION_ACTIVE=false`, `SIMULATION_PAUSED=true`
- writes an event row: `simulation_stopped_guardrail`
- worker exits cleanly so scheduler/agent loops stop

## Incident/Failure Handling
- If page data fails to load:
  - Click `Refresh`.
  - Check for warning/error banners.
- If admin calls return `403 Admin IP not allowed`:
  - Update backend `ADMIN_IP_ALLOWLIST`.
- If metrics are unavailable:
  - `/ops` should still load status/config/audit; metrics panel can be temporarily empty.
- If provider outage causes repeated fallback:
  - Confirm stop event `simulation_stopped_guardrail` reason `provider_failures_repeated`.
  - Reduce LLM traffic or switch route, then re-enable run via admin config.
- If DB pool pressure trips:
  - Confirm stop event reason `db_pool_pressure`.
  - Check DB saturation, pool sizing, and long-running queries before restarting.
- If Redis is unavailable:
  - Usage budget counters fall back to DB reads/writes; continue with higher latency.
  - Restore Redis and monitor for warning clearance in worker logs.

## Failure-Mode Drill Commands
Use these in development before launch:

```bash
# 1) Provider outage fallback behavior (no API keys / invalid keys)
cd backend
OPENROUTER_API_KEY= GROQ_API_KEY= ./venv/bin/python scripts/run_agent_once.py --agent-id 1

# 2) DB reconnect behavior (temporarily point to invalid DB)
DATABASE_URL=postgresql://invalid ./venv/bin/python worker.py

# 3) Redis unavailable behavior (force bad REDIS_URL and capture baseline)
REDIS_URL=redis://localhost:6399 ./venv/bin/python scripts/capture_baseline.py
```

## Prod Guardrail Checks
Run periodically:
1. `/api/admin/status` returns `admin_write_enabled=false`.
2. Write endpoints (for example `POST /api/admin/control/run/start`) return `403`.
3. Worker logs show idle behavior when `SIMULATION_ACTIVE=false` (no active simulation loop traffic).
