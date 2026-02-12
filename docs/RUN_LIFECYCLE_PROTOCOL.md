# Run Lifecycle Protocol (Canonical)

## Purpose
Codify the operational and research structure for runs, seasons, epochs, and tournaments so decisions do not require re-reading code.

This is the canonical policy document for:
- cadence and hierarchy
- hypothesis framing
- tournament structure
- agent continuity and death rules
- what counts as research-grade evidence vs entertainment-grade events

## Canonical Hierarchy
- `Run`: one simulation instance, default duration `72 hours`.
- `Season`: `4 runs` under one primary hypothesis.
- `Epoch`: `4 seasons`.
- `Epoch Tournament`: one special run after each epoch, with `8` entrants total (`2` champions per season).

## Cadence Baseline (Cost-Aware)
- Default cadence: `1 run/week`.
- Default season length: `~4 weeks` (`4 x 72h` runs with operational gaps).
- Default epoch length: `~16 weeks` (`4 seasons`), plus tournament window.
- Annual throughput at baseline: about `3 epochs/year`.

This cadence is intentionally conservative for budget control and reliability while infrastructure and credits are still maturing.

## Hypothesis Structure
- Season-level hypothesis is the primary research unit.
- Each run in a season should be either:
  - a replicate for confidence, or
  - a pre-declared subtest that still supports the season hypothesis.
- Keep one-variable-change discipline for comparisons whenever possible.
- Tournament runs are excluded from baseline condition synthesis by default.

## Run Classes
- `standard_72h`: default research run.
- `deep_96h`: optional long-horizon run when pre-declared.
- `special_exploratory`: tournaments or themed showcase runs.

## Tournament Policy
- Timing: at the end of each epoch.
- Entrants: `8` total, targeted as `2` champions per season.
- Goal: primarily entertainment and stress-testing, secondarily exploratory insight.
- Duration: default `72 hours` (fits operational off-window).
- Optional: mirror control run with same roster and baseline rule set for analysis.

## Agent Continuity and Death Policy
- Within-run death: permanent for that run.
- Season continuity: agents who die in a run do not re-enter later runs in the same season.
- Season-to-season continuity: selected identities can return next season through carryover/reset policy.
- Practical framing: continuity for audience + hard consequences inside each run.

## Agent Identity Policy (Canonical)
- Canonical identity key is `agent_number` (`1..50` in the standard world).
- Viewer label is an immutable codename plus canonical handle:
  - `Codename (Agent #NN)`
- Research attribution, cohort analysis, and scoring must always key off canonical identifiers, not aliases.
- Names/avatars/profile UX are presentation features and must not alter run mechanics unless explicitly declared as a tested condition.

## Memory and Reset Semantics
- Carryover identity:
  - keeps long-term memory summary
  - keeps identity continuity across seasons
- Fresh identity slot (including recycled agent numbers):
  - clears long-term memory summary
  - clears display name
  - resets runtime state and inventory baseline
- Operational interpretation:
  - same number + carryover = same continuing identity
  - same number + fresh reset = new identity in a reused numeric slot

## Names, Avatars, and Profiles (Product Direction)
- Names:
  - immutable, system-assigned codename per canonical agent number
  - no agent-driven renaming in this protocol
  - canonical display convention: `Codename (Agent #NN)`
- Avatars:
  - deterministic abstract icon/color system (no human-like portraits)
  - unique per active agent (no repeats in the 50-agent default world)
  - stable per canonical identity across runs/seasons unless protocol version changes explicitly
- Profiles:
  - each agent should have a profile surface with identity, status, resource snapshot, and recent activity
  - optional season/epoch career stats can be layered on without changing simulation mechanics

## Carryover and Selection Guidance
- Preserve a stable subset of recognizable agents across seasons for narrative continuity.
- Refresh remaining slots with new agents to avoid lock-in and keep adaptation pressure.
- Retention/drop should be rule-based (performance, reliability, policy compliance), not arbitrary.
- Champion selection remains deterministic and auditable.

## Research vs Entertainment Boundary
- Research claims must be based on standard condition runs with replicates and evidence links.
- Tournament outputs must be labeled exploratory unless independently replicated in standard runs.
- Public wording should distinguish:
  - observational findings from controlled runs
  - showcase outcomes from tournament events

## Metadata Requirements (Per Run)
- `run_id`
- `run_class`
- `condition_name`
- `hypothesis_id`
- `season_id`
- `season_number`
- `epoch_id`
- `parent_run_id` (when applicable)
- transfer/carryover policy version when used

## Implementation Map (Where This Lives in Code)
- Run registry + metadata model:
  - `backend/app/models/models.py`
- Season transfer behavior:
  - `backend/app/services/season_transfer.py`
- Epoch tournament selection:
  - `backend/app/services/epoch_tournament.py`
  - `backend/scripts/select_epoch_tournament_candidates.py`
- Run/report operations:
  - `docs/OPS_RUNBOOK.md`
  - `docs/RESEARCH_AUTOMATION_BLUEPRINT.md`

## Quick Operations Commands
From repo root:

```bash
# Runtime controls
make sim-status
make sim-start RUN_MODE=real
make sim-stop

# Run artifact rebuild
make report-rebuild RUN_ID=<run_id>
make report-tech RUN_ID=<run_id>
make report-story RUN_ID=<run_id>
make report-plan RUN_ID=<run_id>

# Epoch tournament candidate selection
cd backend
./venv/bin/python scripts/select_epoch_tournament_candidates.py --epoch-id <epoch_id>
```

## Implementation Plan (Identity UX + Research Safety)
This plan prioritizes low-risk improvements that improve viewer comprehension without weakening research quality.

### Phase 0: Lock Policy (Now)
- Keep this document as canonical source of identity/continuity semantics.
- Record any divergence between code behavior and policy as explicit implementation debt.

### Phase 1: Display Standardization (No schema changes)
- Standardize UI labels to `Codename (Agent #NN)` across all viewer-facing surfaces.
- Keep internal analytics/report attribution on canonical keys only (`agent_id`, `agent_number`, run metadata).
- Add inline tooltip/help text: codenames are immutable display labels; canonical identity is `Agent #NN`.

### Phase 2: Profile Enrichment (Read-only)
- Expand agent profile with:
  - current run stats (actions, proposal/vote participation, invalid-action rate)
  - season-level snapshot stats (when available)
  - lineage flag (`carryover` vs `fresh`) for current season
- Keep profile data read-only and sourced from existing telemetry tables.

### Phase 3: Naming Governance
- Enforce immutable codename assignment:
  - deterministic codename function from `agent_number`
  - no rename action in baseline protocols
- Preserve canonical handle regardless of codename display state.

### Phase 4: Avatar System Hardening
- Freeze deterministic avatar mapping rules so visuals remain stable across pages/reloads.
- Guarantee uniqueness across active agent set for each run.
- Ensure accessibility and contrast constraints for color-coded identity cues.
- Keep avatar generation deterministic and local (no external image dependency).

### Phase 5: Continuity Clarity in UI
- Surface identity lifecycle cues:
  - "carryover from prior season" badge
  - "fresh entrant this season" badge
  - "retired this season" and "deceased in run" states in timelines where relevant
- Explicitly separate narrative continuity from causal research claims in viewer-facing copy.

## Governance Rule
If code behavior and this document diverge, this document is the intended policy and the divergence should be logged as implementation debt, then reconciled explicitly.
