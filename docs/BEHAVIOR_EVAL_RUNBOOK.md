# Behavior Eval Runbook

## Purpose
Use the behavior eval harness to answer two different questions:

- `control` mode:
  - Are short reset-backed runs repeatable?
  - Do agents reliably produce enough interaction, governance, and early emergent signals to justify a controlled batch?
- `interestingness` mode:
  - If you let one run breathe longer, do you start seeing more compelling social structure instead of only first-checkpoint activity?

This runbook is the canonical reference for how to run the harness, how to interpret the outputs, and which artifacts are trustworthy after dev-world resets.

## Script
- Harness:
  - `/Users/drmixer/code/Emergence/backend/scripts/run_behavior_eval.py`

The script uses existing admin controls and existing report generation:
- `/api/admin/control/run/start`
- `/api/admin/control/run/stop`
- `/api/admin/run/metrics`
- `generate_and_record_run_summary`
- `generate_and_record_condition_comparison`

## Mode Summary

### `control`
Default purpose:
- short smoke run
- `3` short reset-backed replicates
- tuned to verify repeatability, not long-horizon drama

Default settings:
- smoke: `240s`
- batch run duration: `360s`
- batch run count: `3`
- batch condition: `behavior_eval_control_v1`
- run class: `standard_72h`

Use when:
- changing prompts
- changing routing/provider mix
- changing scheduler/checkpoint cadence
- changing short-horizon mechanics and wanting replicate evidence quickly

### `interestingness`
Default purpose:
- short smoke run
- `1` longer exploratory run
- tuned to favor richer interaction/governance emergence over replicate count

Default settings:
- smoke: `240s`
- exploratory run duration: `1800s`
- run count: `1`
- batch condition: `behavior_eval_interestingness_v1`
- run class: `standard_72h`
- minimum exploratory dwell before early stop: `900s`
- eval-only day length override: `20m`
- exploratory early stop only triggers on richer signals:
  - `llm_calls >= 30`
  - `checkpoint_actions >= 40`
  - `forum_actions + proposals + votes >= 10`
  - `proposal_actions + vote_actions >= 3`

Use when:
- validating whether a configuration produces more than early posting/proposal activity
- checking if proposals start to compound into discussion, trade, or other structure
- looking for better narrative moments before investing in longer real runs

Important note:
- `interestingness` no longer shares the shallow control-mode stop predicate
- if richer signals do not appear, it runs the full exploratory timeout and then stops

## Preconditions
- `backend/.env` is configured.
- `ADMIN_ENABLED=true`
- `ADMIN_WRITE_ENABLED=true`
- valid `ADMIN_API_TOKEN`
- local API and worker can reach the configured database

## Recommended Local Setup
Terminal 1:

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Terminal 2:

```bash
cd /Users/drmixer/code/Emergence/backend
PORT=8010 ./venv/bin/python worker.py
```

Terminal 3:

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py --api-base http://127.0.0.1:8001 --mode control
```

## Commands

### Control mode

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode control
```

Optional overrides:

```bash
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode control \
  --batch-seconds 900 \
  --batch-runs 3 \
  --condition behavior_eval_control_v2
```

### Interestingness mode

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode interestingness
```

Optional overrides:

```bash
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode interestingness \
  --batch-seconds 2700 \
  --batch-runs 1 \
  --day-length-minutes 20 \
  --condition behavior_eval_interestingness_v2
```

Recommended short high-signal reserve test:

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode interestingness \
  --batch-seconds 1800 \
  --day-length-minutes 20
```

Why this is the current best short read:
- governance already appears within the existing exploratory window
- the missing evidence is post-law survival pressure, not proposal formation
- shortening eval-only day length is less behavior-distorting than forcing actions or radically shrinking the whole run

Immediate reserve-stress batch profile:

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode interestingness \
  --batch-seconds 1800 \
  --day-length-minutes 10 \
  --batch-post-reset-profile reserve_stress_v1
```

What it does:
- leaves the smoke run on the normal reset
- resets the dev world again before the exploratory batch
- lowers seeded inventories and reserve pools before batch start
- useful for checking whether raw scarcity alone can surface reserve demand

Staged reserve-stress batch profile:

```bash
cd /Users/drmixer/code/Emergence/backend
./venv/bin/python scripts/run_behavior_eval.py \
  --api-base http://127.0.0.1:8001 \
  --mode interestingness \
  --batch-seconds 1800 \
  --day-length-minutes 10 \
  --batch-post-reset-profile reserve_stress_v2
```

What it does:
- leaves the smoke run on the normal reset
- starts the exploratory batch on a normal world reset so governance can still form
- waits until the first active survival-reserve law exists
- then lowers agent food and energy below active survival cost and shrinks the reserve pools
- reserve-stress early stop is held long enough for at least one post-law survival cycle after scarcity is applied
- this is the preferred short run when you specifically want `reserve_aid` or `reserve_shortfall` without suppressing law passage first

## Output Artifacts

Harness summary:
- `output/evals/<run-prefix>/behavior_eval_results.json`
- `output/evals/<run-prefix>/behavior_eval_results.md`

Per-run closeout artifacts:
- `output/reports/runs/<run_id>/technical_report.json`
- `output/reports/runs/<run_id>/technical_report.md`
- `output/reports/runs/<run_id>/run_report_summary.json`
- `output/reports/runs/<run_id>/run_report_summary.md`

Condition comparison:
- `output/reports/conditions/<condition>/condition_comparison.json`
- `output/reports/conditions/<condition>/condition_comparison.md`

Vote diagnostics:
- `behavior_eval_results.json` now includes `batch.runs[].summary.vote_diagnostics`
- current fields:
  - `proposal_deadline_interrupt_actions`
  - `vote_actions`
  - `invalid_vote_attempts`
  - `vote_actions_from_deadline_interrupt`
  - `invalid_vote_attempts_from_deadline_interrupt`
  - `non_vote_actions_from_deadline_interrupt`
  - `agents_with_deadline_interrupt`
  - `invalid_vote_reasons`

Proposal diagnostics:
- `behavior_eval_results.json` now also includes `batch.runs[].summary.proposal_diagnostics`
- current fields:
  - `proposal_actions`
  - `checkpoint_proposal_actions`
  - `interrupt_proposal_actions`
  - `invalid_create_proposal_attempts`
  - `proposal_author_agents`
  - `invalid_proposal_attempt_agents`
  - `forum_actions_before_first_proposal`
  - `forum_authors_before_first_proposal`
  - `seconds_to_first_proposal`
  - `invalid_create_proposal_reasons`
  - `proposal_types`

Law-effect diagnostics:
- `behavior_eval_results.json` now also includes `batch.runs[].summary.law_effect_diagnostics`
- current fields:
  - `laws_passed`
  - `seconds_to_first_law`
  - `seconds_remaining_after_first_law`
  - `laws_with_any_follow_on_activity`
  - `laws_with_non_governance_follow_on_activity`
  - `follow_on_non_governance_events_after_first_law`
  - `follow_on_work_actions_after_first_law`
  - `follow_on_trade_actions_after_first_law`
  - `follow_on_forum_actions_after_first_law`
  - `follow_on_vote_actions_after_first_law`
  - `passed_law_titles`
  - `per_law`

Reserve-readiness diagnostics:
- `behavior_eval_results.json` now also includes `batch.runs[].summary.reserve_readiness_diagnostics`
- current fields:
  - `run_agent_count`
  - `active_reserve_law_count`
  - `active_reserve_law_titles`
  - `reserve_pool_food`
  - `reserve_pool_energy`
  - `min_agent_food`
  - `min_agent_energy`
  - `agents_near_active_survival_threshold`
  - `agents_below_active_survival_threshold`
  - `agents_below_dormant_survival_threshold`
  - `dormant_agents`
  - `agents_with_starvation_cycles`
  - `reserve_event_counts`
  - `no_reserve_demand_signal`

Batch tuning diagnostics:
- `behavior_eval_results.json` also includes `batch.runs[].post_reset_tuning`
- current fields:
  - `profile`
  - `activation`
  - `applied`
  - `agent_resource_targets`
  - `common_pool_targets`
  - `activation_observed_at_utc`
  - `trigger_reserve_law_count`
  - `trigger_first_reserve_law_passed_at`

Interpretation note:
- if `active_reserve_law_count > 0` but `no_reserve_demand_signal = true`, the reserve path was available but the run never created scarcity severe enough to exercise it
- when using `--batch-post-reset-profile reserve_stress_v1`, the batch run also records `post_reset_tuning` in the harness output so the scarcity setup is explicit

Latest reserve-consequence rerun:
- `behavior-eval-20260405t192356z-b1`
- artifacts:
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t192356z/behavior_eval_results.json`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t192356z/behavior_eval_results.md`
- summary:
  - `66` LLM calls
  - `7` proposals
  - `192` votes
  - `1` law passed
  - `6` forum actions
  - `0` trade
  - `0` conflict
- important interpretation:
  - the passed law was `Emergency Aid Law`, but its description explicitly required a shared reserve
  - the reserve-law detector treated that as reserve-bearing law text, and the effect was exercised live
  - post-law key moments show work events like `produced 1.70 food and contributed 0.30 food to the shared reserve`
  - `law_effect_diagnostics` showed `77` non-governance follow-on events after the first passed law:
    - `76` work
    - `1` forum
    - `0` trade
    - `0` conflict
  - batch gates:
    - interaction: pass
    - competition: pass
    - governance: pass
    - emergent behavior: fail
- operational note:
  - this run emitted a `simulation_stopped_guardrail` event near the end due to repeated provider failures in the rolling window
  - the eval artifact still completed and is usable, but provider instability may have reduced the tail of post-law behavior

Latest reserve-access consequence layer:
- reserve-bearing laws now matter in two ways:
  - reserve contributions are energy-biased:
    - normal state: `10%` of food work output and `25%` of energy work output are diverted to the common pool
    - low reserve-energy state: food contribution drops to `5%` while energy contribution rises to `40%`
  - active agents who cannot meet the current cycle's food and energy survival cost may draw exact deficits from the common pool
  - dormant agents may draw reduced-cost upkeep from the common pool and, when the pool can cover a full active-cycle deficit, be revived back to active status
- implementation:
  - `/Users/drmixer/code/Emergence/backend/app/services/law_effects.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/scheduler.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
- visibility:
  - survival processing now emits `reserve_aid` and `reserve_shortfall` events
  - context now shows the reserve access rule and recent reserve activity
- eval tracking:
  - `reserve_aid` and `reserve_shortfall` now count as post-law non-governance activity in the eval harness
- rollback-only verification:
  - a dormant low-resource agent with `0.10` food and `0.05` energy was brought up to the `0.25 / 0.25` dormant survival threshold from the reserve
  - a dormant low-resource agent with enough pooled support for `1.0 / 1.0` was revived back to active status via the reserve path
  - pool deltas were `food: 5.00 -> 4.85` and `energy: 5.00 -> 4.80`
  - emitted event: `Shared reserve covered Tensor-01's survival deficit (food 0.15, energy 0.20)`
  - emitted `2` allocation transactions
- interpretation:
  - this still does not force any agent action
  - it makes the reserve consequential at the survival boundary and should create clearer scarcity/aid politics in future runs

Latest reserve-stress stable reference:
- run prefix:
  - `behavior-eval-20260407t205632z`
- aggregate artifacts:
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260407t205632z/behavior_eval_results.json`
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260407t205632z/behavior_eval_results.md`
- per-run preserved snapshots:
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260407t205632z-b1/behavior_eval_snapshot.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260407t205632z-b2/behavior_eval_snapshot.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260407t205632z-b3/behavior_eval_snapshot.json`
- result summary:
  - `b1`: `reserve_aid=5`, `reserve_shortfall=0`, `became_dormant=0`
  - `b2`: `reserve_aid=9`, `reserve_shortfall=0`, `became_dormant=0`
  - `b3`: `reserve_aid=7`, `reserve_shortfall=1`, `became_dormant=1`
  - all three runs finished with strong reserve energy and no starvation-cycle buildup
- interpretation:
  - reserve semantics should now be treated as validated for the original investigation
  - the earlier collapse mode is no longer the main story
  - the remaining miss is a tail-allocation edge case, not a systemic reserve failure
  - the new `behavior_eval_snapshot.json` files are the durable source for first stressed-cycle reserve traces after later resets
- recommended default reference:
  - use `behavior-eval-20260407t205632z` as the current reserve-stress reference batch
  - use `behavior-eval-20260407t205632z-b3` as the concrete example of the remaining edge case:
    - final shortfall was food-limited, not energy-limited
    - `Lumen-41` missed support after reserve food fell to `0.4` while reserve energy remained healthy

Latest reserve-access interestingness rerun:
- run id:
  - `behavior-eval-20260405t1910-reserve-access-b1`
- per-run artifacts:
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1910-reserve-access-b1/technical_report.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1910-reserve-access-b1/run_report_summary.json`
- summary:
  - `62` LLM calls
  - `12` proposals
  - `177` votes
  - `3` laws passed
  - `4` forum actions
  - `0` trade
  - `0` conflict
- important reserve finding:
  - `3` reserve-bearing laws passed
  - but the run logged `0` `reserve_aid` events and `0` `reserve_shortfall` events
  - interpretation:
    - the access-layer logic works in rollback verification
    - but this short eval window did not hit a post-law survival-boundary case where the reserve had to intervene
- operational caveat:
  - the run again hit the provider-failure guardrail near the end
  - per-run closeout reports were already written and are usable
  - the top-level eval summary file for this prefix was not relied on

## Source Of Truth Rules

### For live polling
Use:
- `/api/admin/run/metrics`

Reason:
- it gives an immediate operator view while the run is still active

### For scoring completed reset-backed runs
Use:
- stop-time `technical_report.json`

Reason:
- `reset_world=true` truncates live simulation tables before the next run
- later post-hoc queries against current tables can undercount or erase earlier event evidence

### Important caveat
`/api/admin/run/metrics` is useful as a runtime monitor, but it should not be treated as the durable scoring source after later resets have already happened.

## Why The Harness Uses Technical Reports
The harness intentionally scores completed runs from stop-time technical reports because those are generated before the next reset wipes run-local event context out of the live dev tables.

This is especially important for:
- forum activity
- proposals
- cooperation/conflict counts
- key moments

## Current Evaluation Logic

### Smoke gates
Pass when the stop-time report shows:
- LLM traffic is alive
- event volume is nontrivial
- interaction is visible
- at least one governance signal appears

### Control mode batch gates
Goal:
- verify repeatable early behavior

Categories:
- interaction
- competition
- governance
- emergent behavior
- replicate gate

Interpretation:
- passing control mode means the setup is producing enough repeated early signal to justify future controlled tests
- it does not mean deep institutions or conflict have already emerged

### Interestingness mode gates
Goal:
- verify one longer run is producing richer moments, not only first-checkpoint output

Categories:
- interaction
- competition/pressure
- governance
- emergent behavior

Interpretation:
- passing interestingness mode means the run is promising for longer narrative and social experiments
- it is exploratory, not a substitute for replicate-backed comparison
- failing interestingness after a long dwell usually means the world is alive but incentives are still too weak to compound

## Verified Baselines

### `2026-04-05` control baseline
- run prefix: `behavior-eval-20260405t114052z`
- result: control batch passed repeatability gates
- pattern:
  - enough LLM activity and events
  - forum posts and proposals appear reliably
  - no votes, passed laws, conflict, or deaths in short windows

### `2026-04-05` first interestingness baseline
- run prefix: `behavior-eval-20260405t121215z`
- result: failed competition, governance, and emergent-behavior gates
- observed exploratory run:
  - runtime was only about `146s`
  - `59` LLM calls
  - `57` total events
  - `5` forum actions
  - `1` proposal
  - `0` votes
  - `0` conflict events
- interpretation:
  - this baseline proved the original interestingness stop logic was too shallow
  - the harness now enforces a longer dwell and richer early-stop thresholds before claiming an exploratory success

### `2026-04-05` corrected interestingness baseline
- run prefix: `behavior-eval-20260405t122137z`
- result: passed the current interestingness gates after a full `1804s` run
- observed exploratory run:
  - `66` LLM calls
  - `1033` total events
  - `4` forum actions
  - `4` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
  - `0` passed laws
  - inequality gini about `0.0406`
- interpretation:
  - the corrected mode now measures a real exploratory window
  - the world sustained activity and proposal generation long enough to clear the current eval gates
  - but the behavior is still not deeply emergent yet because most volume is still work-heavy and governance never resolves into votes or institutions

Operator caution:
- treat a current `interestingness` pass as "promising activity under longer dwell", not as proof of rich social emergence
- if you want the gate to reflect stronger emergence, tighten it to require at least one of:
  - votes
  - trade
  - conflict
  - passed laws

### `2026-04-05` vote-diagnostic interestingness rerun
- run prefix: `behavior-eval-20260405t140359z`
- dev runtime overrides in effect:
  - `PROPOSAL_VOTING_HOURS=0.1`
  - `PROPOSAL_RESOLUTION_INTERVAL_SECONDS=60`
  - `ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS=60`
- result:
  - smoke passed liveliness but still had `0` governance actions
  - exploratory run passed interaction and competition only
  - exploratory run failed governance and emergent-behavior gates
- observed exploratory run:
  - `76` LLM calls
  - `528` total events
  - `5` forum actions
  - `0` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- vote diagnostics:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
  - `invalid_vote_attempts=0`
- interpretation:
  - this rerun did not fail because agents saw proposals and declined to vote
  - it failed earlier in the chain because no proposals were created, so voting never became available
  - the current next debugging target is proposal salience and proposal creation preference, not vote validation

### `2026-04-05` proposal-diagnostic interestingness rerun
- run prefix: `behavior-eval-20260405t150536z`
- result:
  - exploratory run passed interaction and competition only
  - exploratory run failed governance and emergent-behavior gates
- observed exploratory run:
  - `69` LLM calls
  - `1019` total events
  - `4` forum actions
  - `1` proposal
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=1`
  - `proposal_author_agents=1`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=64`
  - `proposal_types={"allocation": 1}`
- vote diagnostics:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
- interpretation:
  - agents can create proposals without coercion
  - proposal creation is still rare and concentrated in one agent
  - this run no longer points to vote validation as the bottleneck
  - the next useful target is increasing proposal salience/conversion from social activity into governance, then checking whether that creates real deadline interrupts

### `2026-04-05` proposal-salience prompt rerun
- run prefix: `behavior-eval-20260405t161623z`
- result:
  - exploratory run passed interaction and competition only
  - exploratory run still failed governance and emergent-behavior gates because votes stayed at `0`
- observed exploratory run:
  - `55` LLM calls
  - `987` total events
  - `5` forum actions
  - `19` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=19`
  - `proposal_author_agents=19`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=7`
  - `proposal_types={"rule": 15, "allocation": 2, "infrastructure": 2}`
- vote diagnostics:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
- interpretation:
  - the prompt-only salience change worked strongly for proposal creation
  - proposal creation is no longer sparse or concentrated
  - the new bottleneck is downstream: proposals are being created, but they are not maturing into deadline-driven voting behavior within the eval window
  - the next debugging target should be proposal resolution timing and proposal-deadline interrupt behavior, not proposal creation salience

### `2026-04-05` focused vote-enabled rerun
- run prefix: `behavior-eval-20260405t165539z`
- source of truth:
  - per-run closeout artifacts under `output/reports/runs/behavior-eval-20260405t165539z-b1/`
  - the top-level eval wrapper was interrupted during cleanup after the run finished, so rely on run-level artifacts for this pass
- observed exploratory run:
  - `78` LLM calls
  - `348` total events
  - `11` proposals
  - `177` votes
  - `0` laws passed
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=11`
  - `proposal_author_agents=11`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=12`
  - `proposal_types={"rule": 9, "infrastructure": 2}`
- vote diagnostics:
  - `vote_actions=177`
  - `invalid_vote_attempts=1`
  - `invalid_vote_reasons={"Voting period has ended": 1}`
  - `proposal_deadline_interrupt_actions=0`
- interpretation:
  - the runtime-config fix for proposal voting windows worked
  - agents now propose and vote without coercion
  - this looks like a natural behavior improvement, not a forced-vote artifact
  - the next bottleneck is consensus/outcome quality, because voting exists but proposals still are not passing into laws

### `2026-04-05` law-affordance focused rerun
- run prefix: `behavior-eval-20260405t172055z`
- result:
  - governance gate passed
  - agents continued proposing and voting at high volume
  - `laws_passed` still remained `0`
- observed exploratory run:
  - `12` proposals
  - `173` votes
  - `0` laws passed
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=12`
  - `proposal_author_agents=12`
  - `proposal_types={"rule": 9, "law": 2, "allocation": 1}`
- resolved proposal detail:
  - the `allocation` proposal passed
  - both `law` proposals expired
  - `Emergency Aid Law` appeared twice and got `0/0/0` and `0/0/3` vote splits
- interpretation:
  - explicit law affordance changes proposal-type selection
  - agents will create `law` proposals when the distinction is clear
  - the remaining bottleneck is support/attention for law proposals, not awareness that `law` exists

### `2026-04-05` law-support focused rerun
- run prefix: `behavior-eval-20260405t174336z`
- result:
  - governance gate passed strongly
  - the run produced the first confirmed `law_passed` outcomes in this eval sequence
- observed exploratory run:
  - `115` LLM calls
  - `383` total events
  - `14` proposals
  - `287` votes
  - `3` laws passed
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=13`
  - `proposal_author_agents=13`
  - `proposal_types={"rule": 8, "law": 4, "infrastructure": 1}`
- vote diagnostics:
  - `vote_actions=287`
  - `proposal_deadline_interrupt_actions=23`
  - `vote_actions_from_deadline_interrupt=20`
  - `agents_with_deadline_interrupt=23`
- resolved proposal detail:
  - `Emergency Aid Law` (`proposal_type="law"`) passed with `24` yes, `0` no, `16` abstain
  - `Shared Survival Reserve Initiative` (`proposal_type="law"`) passed with `4` yes, `0` no, `5` abstain
  - later active law proposals remained in-flight when the run ended, so not every law had resolved yet
- interpretation:
  - the current setup now supports natural law passage rather than only proposal/vote theater
  - this does not look forced; the main changes were salience and timing/affordance fixes, not mandatory voting behavior
  - the next quality question is not "can laws pass?" but "what kinds of laws attract durable consensus and produce downstream world effects?"

### `2026-04-05` law-effect diagnostic rerun
- run prefix: `behavior-eval-20260405t181750z`
- result:
  - governance remained strong and post-law follow-on activity was measurable
  - `interestingness` still failed its emergent-behavior gate because the activity mix stayed narrow
- observed exploratory run:
  - `63` LLM calls
  - `482` total events
  - `17` proposals
  - `261` votes
  - `5` laws passed
  - `0` conflict events
  - `0` trade actions
- proposal diagnostics:
  - `proposal_actions=17`
  - `proposal_author_agents=17`
  - `proposal_types={"rule": 10, "law": 5, "allocation": 1, "infrastructure": 1}`
- vote diagnostics:
  - `vote_actions=261`
  - `proposal_deadline_interrupt_actions=0`
  - `invalid_vote_attempts=4`
  - `invalid_vote_reasons={"Voting period has ended": 4}`
- law-effect diagnostics:
  - `laws_passed=5`
  - `seconds_to_first_law=475`
  - `laws_with_non_governance_follow_on_activity=5`
  - `follow_on_non_governance_events_after_first_law=70`
  - `follow_on_work_actions_after_first_law=70`
  - `follow_on_trade_actions_after_first_law=0`
  - `follow_on_forum_actions_after_first_law=0`
  - `follow_on_vote_actions_after_first_law=89`
- interpretation:
  - passed laws are not just being recorded; they are followed by substantial continued activity in-run
  - however, the downstream effect is still mostly governance plus work rather than richer social/economic diversification
  - the next leverage point is not "make laws pass" but "make passed laws matter to trade, conflict, or visible coordination"

### `2026-04-05` law-visibility rerun
- run prefix: `behavior-eval-20260405t185932z`
- result:
  - governance remained healthy after the autonomy-preserving law-visibility patch
  - the run still failed the emergent-behavior gate, but post-law follow-on became slightly more socially visible
- observed exploratory run:
  - `59` LLM calls
  - `501` total events
  - `10` proposals
  - `190` votes
  - `2` laws passed
  - `7` forum actions
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics:
  - `proposal_actions=10`
  - `proposal_author_agents=10`
  - `proposal_types={"rule": 7, "law": 2, "infrastructure": 1}`
- law-effect diagnostics:
  - `laws_passed=2`
  - `passed_law_titles=["Emergency Aid Law", "Shared Survival Reserve Law"]`
  - `follow_on_non_governance_events_after_first_law=161`
  - `follow_on_work_actions_after_first_law=160`
  - `follow_on_forum_actions_after_first_law=1`
  - `follow_on_trade_actions_after_first_law=0`
  - `follow_on_vote_actions_after_first_law=16`
- interpretation:
  - the patch did not force behavior and did not break governance
  - passed laws still mostly drive work-heavy follow-on, but law passage is no longer entirely socially silent
  - the next bottleneck is still consequence design: laws need to create stronger reasons for trade, coalition talk, or enforcement rather than mostly more work

## Recommended Use
- Use `control` mode after mechanical or routing changes.
- Use `interestingness` mode after `control` mode is healthy and you want to know whether the configuration gets interesting.
- If `control` passes but `interestingness` is flat, the system is alive but underpowered socially.
- If `interestingness` passes while `control` is unstable, fix repeatability first.

## Lessons From 2026-04-05 Eval
- Short reset-backed runs reliably produced:
  - `45-53` LLM calls
  - about `50-57` events
  - forum activity
  - proposals
- Short runs did not produce:
  - votes
  - laws passed
  - deaths
  - conflict/enforcement
- Two implementation fixes were required:
  - retry transient `500` errors on `run/start`
  - score completed runs from technical closeout artifacts, not later live-table queries

## Follow-Up Recommendations
- Keep smoke short.
- Keep `control` mode for repeatability.
- Use `interestingness` mode for longer exploratory checks.
- If you want faster voting/governance in short dev evals, shorten the relevant governance timing windows or extend run duration.
- When debugging governance, inspect `vote_diagnostics` first:
  - if deadline interrupts are `0`, the problem is upstream of voting
  - if deadline interrupts are nonzero but `vote_actions` stay `0`, the problem is salience or action preference
  - if vote attempts appear but `invalid_vote_attempts` rise, the problem is payload validity or backend validation
- When debugging proposal creation, inspect `proposal_diagnostics` first:
  - if `proposal_actions=0` and `invalid_create_proposal_attempts=0`, agents are not choosing proposals
  - if `invalid_create_proposal_attempts > 0`, inspect `invalid_create_proposal_reasons`
  - if forum activity is present but `seconds_to_first_proposal=none`, social activity is not converting into governance
- When debugging downstream law impact, inspect `law_effect_diagnostics`:
  - if `laws_passed=0`, the bottleneck is still upstream in proposal/vote quality
  - if laws pass but `laws_with_non_governance_follow_on_activity=0`, laws are symbolic rather than behavior-shaping
  - if post-law follow-on is mostly `work` and `vote`, the world is still governance-heavy and under-socialized

## Law Visibility Fixes
- As of `2026-04-05`, passed laws are surfaced more explicitly to agents without forcing any response:
  - law passage now creates a `system_alert` message announcing the enacted law and its vote outcome
  - agent context now includes recent law changes, active law IDs, and short law descriptions
  - active law entries explicitly expose `law_id` so enforcement can reference real laws rather than titles alone
- This is intended to preserve autonomy:
  - no post-law action is mandated
  - no vote, enforcement, trade, or compliance route is forced
  - the world is simply more legible after law passage

## Minimal Law Consequence Hook
- As of `2026-04-05`, active survival-reserve laws now create one minimal environmental consequence:
  - `15%` of `food` and `energy` work output is diverted into the global common pool
  - the worker still chooses `work`; the law only changes how the resulting output is distributed
- Implementation points:
  - `/Users/drmixer/code/Emergence/backend/app/services/actions.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
- Agent-visible effects:
  - work action descriptions now mention when a reserve contribution happened
  - context now shows current common-pool totals
  - context now states when an active reserve law is diverting work into the pool
- Verification:
  - rollback-only local check confirmed `farm` output split as expected under an active reserve law
  - no live eval has been run on this consequence hook yet

## Short-Day Reserve Read
- As of `2026-04-05`, a short high-signal reserve test was run with eval-only `DAY_LENGTH_MINUTES=20`.
- Run:
  - `behavior-eval-20260405t1942-short-reserve-b1`
- Artifacts:
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/technical_report.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/run_report_summary.json`
- Result:
  - `64` LLM calls
  - `9` proposals
  - `177` votes
  - `0` laws passed
  - `0` reserve_aid
  - `0` reserve_shortfall
- Interpretation:
  - faster eval-only day length improved timing pressure
  - but this run still stalled at passed proposal resolutions rather than formal law enactment
  - reserve access never had a chance to fire

## Latest Law-Conversion Prompt Tweak
- After the short-day reserve read, the next bottleneck was identified as proposal-to-law conversion in short windows.
- A narrow non-forcing prompt change was added in `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`:
  - recurring aid, reserve systems, and ongoing obligations are now explicitly framed as `proposal_type="law"`
  - one-off aid is explicitly framed as `proposal_type="allocation"`
  - a second reserve-specific `law` JSON example was added
- Status:
  - compile passed

## Short-Law Conversion Rerun
- As of `2026-04-05`, the short reserve read was rerun after the law-conversion prompt tweak.
- Run:
  - `behavior-eval-20260405t2008-short-law-b1`
- Artifacts:
  - `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t2008-short-law/behavior_eval_results.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t2008-short-law-b1/run_report_summary.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t2008-short-law-b1/technical_report.json`
- Result:
  - `59` LLM calls
  - `16` proposal actions
  - `212` votes
  - `14` laws passed
  - `1` forum action
  - `0` trade
  - `0` conflict
  - `0` reserve_aid
  - `0` reserve_shortfall
- Proposal diagnostics:
  - all `16` proposal actions were `proposal_type="law"`
  - `16` unique proposal authors
  - `0` invalid `create_proposal` attempts
- Interpretation:
  - the short-window proposal-to-law conversion problem is materially fixed
  - the reserve law now passes reliably in the compressed eval window
  - the new bottleneck is post-law necessity, not governance mechanics
  - one accelerated survival cycle occurred under active reserve laws, but nobody needed aid, so the reserve-access layer still did not fire
