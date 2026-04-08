# Handoff For Next Chat

## Objective
Continue implementation from the checklist at **Section 5: Long-Term Agent Memory**.

## Source Docs
- Plan: `/Users/drmixer/code/Emergence/notes/REVISION_PLAN.md`
- Checklist: `/Users/drmixer/code/Emergence/notes/REVISION_IMPLEMENTATION_CHECKLIST.md`
- Behavior eval handoff: `/Users/drmixer/code/Emergence/notes/BEHAVIOR_EVAL_HANDOFF.md`
- Behavior eval runbook: `/Users/drmixer/code/Emergence/docs/BEHAVIOR_EVAL_RUNBOOK.md`

## Current Status (already completed)
- Section 1 complete (summary reliability + context denominator).
- Section 2 complete (budget settings, `llm_usage` ledger/counters, LLM budget enforcement).
- Section 3 complete (50-agent seed/runtime defaults; kept DB `agent_number <= 100` constraint).
- Section 4 complete (checkpoint scheduling + interrupts + deterministic between-checkpoint routine layer + persisted intent horizon).

## Important Existing Changes (do not undo)
- New migration: `/Users/drmixer/code/Emergence/backend/alembic/versions/1f2e3d4c5b6a_add_llm_usage_budget_tracking.py`
- New migration: `/Users/drmixer/code/Emergence/backend/alembic/versions/4a9d3e6f7b8c_add_agent_checkpoint_intent_fields.py`
- New service: `/Users/drmixer/code/Emergence/backend/app/services/usage_budget.py`
- New service: `/Users/drmixer/code/Emergence/backend/app/services/routine_executor.py`
- `agent_loop` now replans at checkpoints/interrupts and executes deterministic actions between checkpoints.

## Locked Decisions
- 50 agents for v1.
- Checkpointed + trimmed decision model (no full-throttle LLM loop).
- Daily cost target <= $1/day.
- Add per-agent long-term memory with salience-based updates.
- Neon remains primary DB.

## Start Here (Section 5 only)
1. Execute checklist **5.1 Storage**:
- Add `agent_memory` table migration in `/Users/drmixer/code/Emergence/backend/alembic/versions/`.
- Include fields: `agent_id`, `summary_text`, `last_updated_at`, `last_checkpoint_number` (or equivalent).
2. Execute checklist **5.2 Update policy**:
- Implement salience detector service in `/Users/drmixer/code/Emergence/backend/app/services/`.
- Trigger memory updates only on salient deltas or every N checkpoints (use existing config knobs from Section 2).
- Enforce memory length cap and cheap compaction path.
3. Execute checklist **5.3 Prompt injection**:
- Inject per-agent long-term memory into decision context in `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`.
- Keep strict memory char/token budget.
4. Validation:
- Verify memory rows are created/updated for salient events and/or checkpoint cadence.
- Verify `agent_loop` + checkpoint flow still runs without runtime errors.
- Verify context output includes bounded memory block when present.
5. Mark completed Section 5 checklist items in `/Users/drmixer/code/Emergence/notes/REVISION_IMPLEMENTATION_CHECKLIST.md`.

## Constraints
- Keep this pass scoped to **Section 5 only**.
- Preserve existing Section 1-4 behavior.
- Minimal/surgical changes; avoid unrelated refactors.

## Additional Current Context
- A behavior eval harness now exists at `/Users/drmixer/code/Emergence/backend/scripts/run_behavior_eval.py`.
- It supports two modes:
  - `control`
  - `interestingness`
- `interestingness` now enforces a `900s` minimum dwell before early stop and only exits early on richer social/governance signals.
- The verified April 5 eval artifacts live under:
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t114052z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t121215z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t122137z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t140359z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t150536z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t161623z/`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t165539z-b1/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t172055z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t174336z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t181750z/`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t185932z/`
- For reset-backed dev evals, stop-time `technical_report.json` is the durable scoring source.
- `behavior_eval_results.json` now also includes `batch.runs[].summary.vote_diagnostics`.
- `behavior_eval_results.json` now also includes `batch.runs[].summary.proposal_diagnostics`.
- `behavior_eval_results.json` now also includes `batch.runs[].summary.law_effect_diagnostics`.
- Autonomy-preserving law-visibility changes were added after the last eval:
  - `/Users/drmixer/code/Emergence/backend/app/services/scheduler.py` now emits a `system_alert` when a law is enacted
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py` now shows recent law changes, active law IDs, and short law descriptions
  - this is meant to make laws legible/actionable without forcing any post-law behavior
- A minimal law-consequence hook was then added:
  - `/Users/drmixer/code/Emergence/backend/app/services/actions.py` now diverts `15%` of food/energy work output into the common pool when a survival-reserve law is active
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py` now shows the common pool and the active reserve-law effect
  - rollback-only verification showed `farm` work splitting into personal output plus reserve contribution under an active reserve law
- A fresh interestingness rerun then exercised that hook:
  - `behavior-eval-20260405t192356z-b1`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t192356z/behavior_eval_results.json`
  - result:
    - `66` LLM calls
    - `7` proposals
    - `192` votes
    - `1` passed law
    - `6` forum actions
    - `0` trade
    - `0` conflict
  - the passed law was `Emergency Aid Law`, but its text required a shared reserve, so the reserve-law detector matched it and post-law work events showed reserve contributions
  - `law_effect_diagnostics` after the first passed law:
    - `77` non-governance follow-on events
    - `76` work
    - `1` forum
    - `0` trade
    - `0` conflict
  - interpretation:
    - the first consequence hook works and remains non-forcing
    - it still broadens activity only slightly, and mostly through work/resource flow rather than trade or conflict
  - caveat:
    - the run emitted `simulation_stopped_guardrail` near the end due to repeated provider failures, so tail behavior may be somewhat truncated
- A second autonomy-preserving consequence layer was then added after that run:
  - reserve-bearing laws now also permit survival-boundary withdrawals from the common pool during survival processing
  - dormant agents are prioritized ahead of active agents for reserve aid
  - new event types:
    - `reserve_aid`
    - `reserve_shortfall`
  - context now shows the reserve access rule and recent reserve activity
  - eval harness now counts those events as post-law non-governance consequences
  - rollback-only verification:
    - a dormant low-resource agent was topped up from `0.10 food / 0.05 energy` to the `0.25 / 0.25` dormant survival threshold
    - reserve pools fell from `5.00/5.00` to `4.85/4.80`
    - event emitted: `Shared reserve covered Tensor-01's survival deficit (food 0.15, energy 0.20)`
  - a fresh rerun was then executed:
    - `behavior-eval-20260405t1910-reserve-access-b1`
    - per-run artifacts:
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1910-reserve-access-b1/technical_report.json`
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1910-reserve-access-b1/run_report_summary.json`
    - result:
      - `62` LLM calls
      - `12` proposals
      - `177` votes
      - `3` passed reserve-bearing laws
      - `0` trade
      - `0` conflict
    - crucial finding:
      - `reserve_aid = 0`
      - `reserve_shortfall = 0`
      - so the access-layer mechanic still has not been exercised in a real post-law survival cycle
    - interpretation:
      - governance remains strong
      - reserve laws now pass reliably
      - but this eval window is still too short, or too low-pressure, to actually trigger reserve withdrawals after those laws pass
- A follow-up eval recommendation was then implemented:
  - prefer shorter high-signal reserve tests over much longer runs
  - new path:
    - keep `interestingness` at about `25-30` minutes
    - apply eval-only `DAY_LENGTH_MINUTES=20`
  - code changes:
    - `DAY_LENGTH_MINUTES` is runtime-mutable in `/Users/drmixer/code/Emergence/backend/app/services/runtime_config.py`
    - scheduler day-based tasks now use dynamic interval reads in `/Users/drmixer/code/Emergence/backend/app/services/scheduler.py`
    - simulation day calculations now respect runtime override in `/Users/drmixer/code/Emergence/backend/app/services/simulation_time.py`
    - harness supports `--day-length-minutes` in `/Users/drmixer/code/Emergence/backend/scripts/run_behavior_eval.py`
    - `interestingness` preset now defaults to `DAY_LENGTH_MINUTES=20`
  - a fresh short-day reserve run was then executed:
    - `behavior-eval-20260405t1942-short-reserve-b1`
    - artifacts:
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/technical_report.json`
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/run_report_summary.json`
    - result:
      - `64` LLM calls
      - `9` proposals
      - `177` votes
      - `0` laws passed
      - `0` reserve_aid
      - `0` reserve_shortfall
    - takeaway:
      - faster day length alone is not enough
      - the next bottleneck is still reliable formal law passage in the short window
  - a follow-up non-forcing law-conversion prompt tweak was then added in `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
    - recurring aid/reserve systems are now more explicitly mapped to `proposal_type="law"`
    - one-off aid is more explicitly mapped to `proposal_type="allocation"`
  - that exact prompt tweak was then rerun as:
    - `behavior-eval-20260405t2008-short-law-b1`
    - artifacts:
      - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t2008-short-law/behavior_eval_results.json`
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t2008-short-law-b1/run_report_summary.json`
      - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t2008-short-law-b1/technical_report.json`
    - result:
      - `59` LLM calls
      - `16` proposal actions
      - `212` votes
      - `14` laws passed
      - all `16` proposal actions were `proposal_type="law"`
      - `0` reserve_aid
      - `0` reserve_shortfall
    - takeaway:
      - short-window law conversion is now working
      - reserve laws can pass reliably in the compressed eval
      - the next bottleneck is not governance mechanics, but whether any agent actually needs reserve support after those laws pass
- Latest governance-debug finding:
  - the `behavior-eval-20260405t140359z` rerun had `0` proposals and `0` proposal-deadline interrupts
  - the `behavior-eval-20260405t150536z` rerun had `1` proposal, `0` invalid proposal attempts, and still `0` proposal-deadline interrupts / `0` votes
  - the `behavior-eval-20260405t161623z` rerun, after the prompt salience change, had `19` proposals from `19` agents, `0` invalid proposal attempts, and still `0` proposal-deadline interrupts / `0` votes
  - the focused rerun `behavior-eval-20260405t165539z-b1`, after fixing proposal creation to respect runtime voting-window overrides, had `11` proposals and `177` votes with `0` laws passed
  - the law-affordance rerun `behavior-eval-20260405t172055z-b1` produced `2` law proposals, but both expired while an allocation proposal passed
  - the law-support rerun `behavior-eval-20260405t174336z-b1` then produced `14` proposals, `287` votes, `23` proposal-deadline interrupt actions, and `3` laws passed
  - passed law rows included `Emergency Aid Law` and `Shared Survival Reserve Initiative`, both as `proposal_type="law"`
  - the law-effect rerun `behavior-eval-20260405t181750z-b1` then produced `17` proposals, `261` votes, and `5` passed laws
  - its new `law_effect_diagnostics` showed all `5` passed laws had non-governance follow-on activity, but the first-law follow-on was still entirely `work` rather than trade/conflict/forum
  - the law-visibility rerun `behavior-eval-20260405t185932z-b1` then produced `10` proposals, `190` votes, `2` passed laws, and `7` forum actions
  - after the first passed law, the new `law_effect_diagnostics` showed `161` non-governance follow-on events: still `160` work, but now also `1` forum action
  - the short-law rerun `behavior-eval-20260405t2008-short-law-b1` then produced `16` proposal actions, `212` votes, and `14` passed laws in the compressed `20m` day setting
  - its proposal diagnostics showed full conversion to `proposal_type="law"` with `16` unique authors and no invalid proposal attempts
  - its law-effect diagnostics still showed zero trade, zero conflict, zero reserve_aid, and zero reserve_shortfall
  - current conclusion: governance conversion now works in the short window, but the world still does not create enough post-law survival pressure for the reserve-access mechanic to become behaviorally relevant

## Output Expectation For Next Chat
- Code changes for Section 5 only.
- Quick verification report (passed/failed + evidence).
- Updated checklist markers for Section 5.
