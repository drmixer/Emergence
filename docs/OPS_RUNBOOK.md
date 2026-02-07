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
9. When done, click `Stop Run` and confirm:
   - `Paused = yes`.
10. If you need a clean world, click `Reset Dev World` and confirm:
    - Success notice: `Dev world reset + reseeded`.

## Incident/Failure Handling
- If page data fails to load:
  - Click `Refresh`.
  - Check for warning/error banners.
- If admin calls return `403 Admin IP not allowed`:
  - Update backend `ADMIN_IP_ALLOWLIST`.
- If metrics are unavailable:
  - `/ops` should still load status/config/audit; metrics panel can be temporarily empty.

## Prod Guardrail Checks
Run periodically:
1. `/api/admin/status` returns `admin_write_enabled=false`.
2. Write endpoints (for example `POST /api/admin/control/run/start`) return `403`.
3. Worker logs show idle behavior when `SIMULATION_ACTIVE=false` (no active simulation loop traffic).

