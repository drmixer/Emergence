# Behavior Eval Handoff

## What Exists
- Harness:
  - `/Users/drmixer/code/Emergence/backend/scripts/run_behavior_eval.py`
- Runbook:
  - `/Users/drmixer/code/Emergence/docs/BEHAVIOR_EVAL_RUNBOOK.md`

## Current Modes
- `control`
  - short smoke + `3` short reset-backed replicates
- `interestingness`
  - short smoke + `1` longer exploratory run
  - minimum dwell before early stop: `900s`
  - early stop now requires materially richer signals, not just shallow liveliness

## Verified Session
Date:
- `2026-04-05`

Primary run prefix:
- `behavior-eval-20260405t114052z`

Run IDs:
- smoke:
  - `behavior-eval-20260405t114052z-smoke`
- control batch:
  - `behavior-eval-20260405t114052z-b1`
  - `behavior-eval-20260405t114052z-b2`
  - `behavior-eval-20260405t114052z-b3`

Primary outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t114052z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t114052z/behavior_eval_results.md`

Interestingness baseline prefix:
- `behavior-eval-20260405t121215z`

Interestingness outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t121215z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t121215z/behavior_eval_results.md`

Corrected interestingness prefix:
- `behavior-eval-20260405t122137z`

Corrected interestingness outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t122137z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t122137z/behavior_eval_results.md`

Vote-diagnostic interestingness rerun prefix:
- `behavior-eval-20260405t140359z`

Vote-diagnostic rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t140359z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t140359z/behavior_eval_results.md`

Proposal-diagnostic rerun prefix:
- `behavior-eval-20260405t150536z`

Proposal-diagnostic rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t150536z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t150536z/behavior_eval_results.md`

Proposal-salience prompt rerun prefix:
- `behavior-eval-20260405t161623z`

Proposal-salience prompt rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t161623z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t161623z/behavior_eval_results.md`

Focused vote-enabled rerun prefix:
- `behavior-eval-20260405t165539z`

Focused vote-enabled rerun outputs:
- `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t165539z-b1/technical_report.json`
- `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t165539z-b1/run_report_summary.json`

Law-affordance focused rerun prefix:
- `behavior-eval-20260405t172055z`

Law-affordance focused rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t172055z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t172055z/behavior_eval_results.md`

Law-support focused rerun prefix:
- `behavior-eval-20260405t174336z`

Law-support focused rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t174336z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t174336z/behavior_eval_results.md`

Law-effect diagnostic rerun prefix:
- `behavior-eval-20260405t181750z`

Law-effect diagnostic rerun outputs:
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t181750z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t181750z/behavior_eval_results.md`

## Verified Findings
- Smoke run passed all smoke gates using stop-time technical evidence.
- Control batch passed:
  - interaction
  - competition
  - governance
  - emergent behavior
  - replicate gate

Observed short-run pattern:
- strong checkpoint activity
- forum posting
- proposals
- almost no downstream voting
- no conflict or enforcement
- no deaths

Interpretation:
- the system is alive and repeatable in short windows
- short windows are still mostly first-checkpoint and early social behavior
- longer exploratory windows are needed for richer institutional behavior

Latest governance conclusion:
- the latest law-support rerun crossed the threshold into meaningful governance rather than only governance mechanics
- it produced `287` votes, `23` proposal-deadline interrupt actions, and `3` laws passed
- passed law rows included `Emergency Aid Law` and `Shared Survival Reserve Initiative`, both with `proposal_type="law"`
- the current path still looks non-forcing: the lift came from better salience plus fixing runtime voting-window propagation for created proposals

Latest downstream-law-effect conclusion:
- the `behavior-eval-20260405t181750z-b1` rerun added explicit post-law diagnostics and still produced `5` passed laws
- all `5` passed laws had non-governance follow-on activity in the next `300s`
- the first passed law was followed by `70` non-governance events, all of them `work`
- the run was governance-strong but still narrow: `261` votes, `17` proposals, `0` trade, `0` conflict, and the emergent-behavior gate still failed on key-moment diversity
- practical conclusion: the system can now pass laws naturally, but passed laws are not yet producing richer economic or conflict structure

Latest autonomy-preserving consequence-visibility change:
- passed laws now emit a `system_alert` message on enactment in `/Users/drmixer/code/Emergence/backend/app/services/scheduler.py`
- agent context in `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py` now shows:
  - recent law changes
  - active laws with `law_id`
  - short law descriptions
  - explicit reminder that `law_id` is what enforcement actions cite
- intent:
  - increase law legibility and consequence visibility
  - do not force any specific reaction after a law passes
- verification status:
  - compile passed
  - live context snapshot confirmed active law IDs and recent-law visibility
  - no new law passed after this patch during the paused verification window, so the new enactment alert path was not re-exercised end-to-end yet

Latest law-visibility rerun result:
- `behavior-eval-20260405t185932z-b1`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t185932z/behavior_eval_results.json`
- `/Users/drmixer/code/Emergence/output/evals/behavior-eval-20260405t185932z/behavior_eval_results.md`
- summary:
  - `59` LLM calls
  - `10` proposals
  - `190` votes
  - `2` laws passed
  - `7` forum actions
  - `0` trade
  - `0` conflict
- post-law follow-on:
  - first passed law was followed by `161` non-governance events in `300s`
  - that was still overwhelmingly `work` (`160`)
  - but it now included `1` forum action, which is slightly less socially silent than the prior rerun
- interpretation:
  - the law-visibility patch preserved autonomy and governance viability
  - it may have improved law salience slightly
  - it did not yet unlock richer economic or conflict dynamics

Latest minimal consequence hook:
- active survival-reserve laws now divert `15%` of food/energy work output into the common pool
- implemented in:
  - `/Users/drmixer/code/Emergence/backend/app/services/actions.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
- rationale:
  - law changes incentives/resource distribution
  - no agent is forced to work, trade, vote, or comply in a specific way
  - consequence is environmental, not behavioral scripting
- rollback-only verification:
  - with an active reserve law, a `farm` action produced `1.70` food kept by the agent and `0.30` food contributed to the pool
  - context now shows the common pool and the active reserve-law effect line
- status:
  - compile passed
  - no fresh full eval has been run on this consequence hook yet

Latest reserve-consequence rerun:
- `behavior-eval-20260405t192356z-b1`
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
- proposal mix:
  - `3` law proposals
  - `4` rule proposals
- important nuance:
  - the passed law was `Emergency Aid Law`, not a title literally called `Shared Survival Reserve`
  - its text explicitly required maintaining and using a shared reserve, so the new reserve-law detector matched it and the consequence hook activated
  - per-run event evidence then showed multiple work events with shared-reserve contributions, for example `produced 1.70 food and contributed 0.30 food to the shared reserve`
- downstream effect:
  - first-law follow-on in `300s`:
    - `77` non-governance events
    - `76` work
    - `1` forum
    - `0` trade
    - `0` conflict
    - `0` further proposal actions
  - governance stayed viable, but richer post-law behavior still did not emerge
- eval interpretation:
  - the minimal consequence hook is real, visible, and autonomy-preserving
  - it currently shifts work/resource flow more than it creates new strategic behavior
  - next likely path is a second consequence mechanism that creates actual coordination or access pressure around the shared reserve
- operational caveat:
  - this run logged a `simulation_stopped_guardrail` event near the end from repeated provider failures
  - treat the run as valid, but do not overread the tail

Latest reserve-access consequence layer:
- reserve-bearing laws no longer only skim future production
- they now also authorize survival-boundary withdrawals from the common pool during survival processing
- behavior:
  - if an agent cannot meet the current cycle's food and energy survival requirement
  - and enough pooled food and energy exist
  - the shared reserve covers the exact deficits
  - if the pool cannot fully cover the deficits, a `reserve_shortfall` event is emitted instead
- implementation:
  - `/Users/drmixer/code/Emergence/backend/app/services/law_effects.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/scheduler.py`
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
  - `/Users/drmixer/code/Emergence/backend/scripts/run_behavior_eval.py`
- extra details:
  - dormant agents are prioritized ahead of active agents when reserve aid is applied in the survival cycle
  - context now shows:
    - reserve access rule
    - recent `reserve_aid` / `reserve_shortfall` activity
  - eval harness now treats `reserve_aid` and `reserve_shortfall` as post-law non-governance events
- rollback-only verification:
  - compile passed
  - a dormant low-resource agent was topped up from `food=0.10 / energy=0.05` to `0.25 / 0.25`
  - reserve pools dropped from `5.00/5.00` to `4.85/4.80`
  - emitted event:
    - `Shared reserve covered Tensor-01's survival deficit (food 0.15, energy 0.20)`
  - emitted `2` allocation transactions
- current interpretation:
  - this is still autonomy-preserving
  - it should create more meaningful reserve scarcity and aid consequences than contribution-only mode
  - no fresh full eval has been run on this new access layer yet

Latest reserve-access rerun:
- `behavior-eval-20260405t1910-reserve-access-b1`
- source artifacts:
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
- law result:
  - scheduler resolved multiple reserve-bearing proposals as passed:
    - `Shared Survival Reserve Policy`
    - `Shared Survival Reserve Initiative`
    - `Shared Survival Reserve Fund`
- reserve-access result:
  - DB-scoped run query showed:
    - `reserve_aid = 0`
    - `reserve_shortfall = 0`
    - `law_passed = 3`
  - practical interpretation:
    - the new access layer did not fail
    - the run simply never reached a post-law survival cycle where an agent needed rescue from the pool
    - this means the next useful test may require either a longer horizon or a faster survival cadence in eval mode
- operational caveat:
  - the run again hit the provider-failure guardrail near the end
  - the harness process was manually interrupted after the per-run closeout reports were written, so rely on the per-run artifacts above rather than a top-level eval summary for this prefix

Latest short-read recommendation:
- use a shorter eval with faster eval-only survival cadence rather than a much longer exploratory window
- concrete recommendation:
  - keep `interestingness` around `25-30` minutes
  - set eval-only `DAY_LENGTH_MINUTES=20`
  - keep proposal/enforcement resolution at `60s`
  - keep proposal voting window short
- rationale:
  - governance already emerges in the current window
  - the missing evidence is a post-law survival cycle where reserve access actually matters
  - faster day length is the shortest clean way to exercise that without forcing behavior

Implementation added:
- `DAY_LENGTH_MINUTES` is now runtime-mutable
- scheduler daily tasks now re-read day length dynamically
- `simulation_time` also reads the runtime day-length override
- harness supports `--day-length-minutes`
- `interestingness` default now applies eval-only `DAY_LENGTH_MINUTES=20`

Interestingness baseline lesson:
- the first `interestingness` baseline ended after about `146s`
- it produced more activity than silence, but still only:
  - `59` LLM calls
  - `57` total events
  - `5` forum actions
  - `1` proposal
  - `0` votes
  - `0` conflict events
- this showed the original exploratory stop rule was still too close to the control smoke predicate
- harness fix already applied:
  - `interestingness` now enforces a `900s` minimum dwell
  - early stop only triggers after richer checkpoint/social/governance thresholds

Corrected interestingness baseline lesson:
- the corrected run lasted about `1804s` and passed the current interestingness gates
- it produced:
  - `66` LLM calls
  - `1033` total events
  - `4` forum actions
  - `4` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
  - `0` passed laws
- interpretation:
  - the harness is now testing the right time horizon
  - the current world still looks work-heavy and institution-light
  - current interestingness pass means "more sustained activity" more than "strong emergence"

Vote-diagnostic rerun lesson:
- the rerun used development governance timing overrides:
  - `PROPOSAL_VOTING_HOURS=0.1`
  - `PROPOSAL_RESOLUTION_INTERVAL_SECONDS=60`
  - `ENFORCEMENT_RESOLUTION_INTERVAL_SECONDS=60`
- it produced:
  - `76` LLM calls
  - `528` total events
  - `5` forum actions
  - `0` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- new vote diagnostics showed:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
  - `invalid_vote_attempts=0`
- interpretation:
  - the current failure mode in that rerun was upstream of voting
  - no proposal was created, so agents never reached a real vote opportunity
  - the next debugging target is proposal salience and proposal creation preference, not vote validation

Proposal-diagnostic rerun lesson:
- the rerun produced:
  - `69` LLM calls
  - `1019` total events
  - `4` forum actions
  - `1` proposal
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics showed:
  - `proposal_actions=1`
  - `proposal_author_agents=1`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=64`
  - `proposal_types={"allocation": 1}`
- vote diagnostics still showed:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
- interpretation:
  - non-forced proposal creation is possible
  - proposal generation is still sparse, and one proposal was not enough to create meaningful voting pressure
  - the next likely leverage point is proposal salience and conversion from forum/social context into governance actions

Proposal-salience prompt rerun lesson:
- the rerun produced:
  - `55` LLM calls
  - `987` total events
  - `5` forum actions
  - `19` proposals
  - `0` votes
  - `0` trade actions
  - `0` conflict events
- proposal diagnostics showed:
  - `proposal_actions=19`
  - `proposal_author_agents=19`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=7`
  - `proposal_types={"rule": 15, "allocation": 2, "infrastructure": 2}`
- vote diagnostics still showed:
  - `proposal_deadline_interrupt_actions=0`
  - `agents_with_deadline_interrupt=0`
  - `vote_actions=0`
- interpretation:
  - the prompt-only proposal salience change worked
  - proposal creation is now broad rather than sparse
  - the next bottleneck is downstream of proposal creation: deadline interrupts and voting/resolution timing

Focused vote-enabled rerun lesson:
- the rerun produced:
  - `78` LLM calls
  - `348` total events
  - `11` proposals
  - `177` votes
  - `0` laws passed
- proposal diagnostics showed:
  - `proposal_actions=11`
  - `proposal_author_agents=11`
  - `invalid_create_proposal_attempts=0`
  - `seconds_to_first_proposal=12`
- vote diagnostics showed:
  - `vote_actions=177`
  - `invalid_vote_attempts=1`
  - `invalid_vote_reasons={"Voting period has ended": 1}`
  - `proposal_deadline_interrupt_actions=0`
- interpretation:
  - the runtime-config fix for proposal voting windows worked
  - agents now propose and vote without coercion
  - the next bottleneck is not participation, but whether proposal quality/consensus is strong enough to pass laws

Law-affordance focused rerun lesson:
- the rerun produced:
  - `12` proposals
  - `173` votes
  - `0` laws passed
- proposal diagnostics showed:
  - `proposal_actions=12`
  - `proposal_author_agents=12`
  - `proposal_types={"rule": 9, "law": 2, "allocation": 1}`
- resolved proposal detail showed:
  - the allocation proposal passed
  - both `law` proposals expired
  - `Emergency Aid Law` appeared twice and got `0/0/0` and `0/0/3`
- interpretation:
  - explicit `law` affordance changes proposal-type selection
  - law proposals are now being created
  - the next bottleneck is support/attention for law proposals rather than proposal typing or voting mechanics

## Important Reliability Lessons

### 1. `run/start` can transiently 500 under reset-backed load
Fix already applied:
- the harness retries transient `5xx` start failures before giving up

### 2. Post-hoc live-table scoring is unsafe after `reset_world=true`
Reason:
- each reset truncates the dev-world simulation tables
- if you recompute old runs from current live tables after later resets, event counts can collapse to zero

Operational rule:
- for completed reset-backed eval runs, score from stop-time `technical_report.json`

### 3. `run/metrics` is for live polling, not durable post-reset scoring
Use it while a run is active.
Do not treat it as canonical after later resets.

### 4. Use `vote_diagnostics` before changing governance again
Operational rule:
- inspect `batch.runs[].summary.vote_diagnostics` in `behavior_eval_results.json`

Interpretation:
- deadline interrupts `0` means the problem is before voting
- deadline interrupts `>0` with `vote_actions=0` means the problem is salience or decision preference
- `invalid_vote_attempts > 0` means the problem is vote payload validity or backend validation

### 5. Use `proposal_diagnostics` before changing proposal mechanics
Operational rule:
- inspect `batch.runs[].summary.proposal_diagnostics` in `behavior_eval_results.json`

Interpretation:
- `proposal_actions=0` and `invalid_create_proposal_attempts=0` means agents are not choosing proposal creation
- `invalid_create_proposal_attempts > 0` means proposal intent exists but validation or affordance is failing
- nontrivial `forum_actions_before_first_proposal` with `seconds_to_first_proposal=null` means social activity is not converting into governance

## Latest Short-Day Reserve Result
- Run:
  - `behavior-eval-20260405t1942-short-reserve-b1`
- Artifacts:
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/technical_report.json`
  - `/Users/drmixer/code/Emergence/output/reports/runs/behavior-eval-20260405t1942-short-reserve-b1/run_report_summary.json`
- Summary:
  - `64` LLM calls
  - `9` proposals
  - `177` votes
  - `0` laws passed
  - `0` trade
  - `0` conflict
- DB-scoped event query:
  - `reserve_aid = 0`
  - `reserve_shortfall = 0`
  - `proposal_resolved = 4`
  - `law_passed = 0`
- Interpretation:
  - `DAY_LENGTH_MINUTES=20` is not enough by itself
  - the short path did improve pressure, but in this run proposals still did not convert into formal laws
  - reserve-access evaluation remains blocked on reliable law enactment, not just survival timing

## Latest Law-Conversion Prompt Tweak
- File:
  - `/Users/drmixer/code/Emergence/backend/app/services/context_builder.py`
- Change:
  - clarified that recurring aid, reserve access, and pooled-contribution systems should usually use `proposal_type="law"`
  - clarified that one-time aid distributions should usually use `proposal_type="allocation"`
  - added a second reserve-specific `law` example
- Why:
  - the short-day reserve rerun showed passed proposal resolutions but still `0` formal laws passed
  - this is the smallest non-forcing change that targets the actual bottleneck
- Verification:
  - compile passed
  - compile passed

## Latest Short-Law Rerun
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
- Key diagnostics:
  - all `16` proposal actions were `proposal_type="law"`
  - `16` unique proposal authors
  - `0` invalid `create_proposal` attempts
  - `2` invalid votes, both rejected because the voting period had already ended
  - first law passed about `478s` into the run
  - after the first passed law, there were `89` non-governance follow-on events and `63` more votes
- Interpretation:
  - the short-window law-conversion bottleneck is fixed enough for evaluation purposes
  - the reserve-law consequence layer is active, but still not strategically necessary in this short run
  - the next bottleneck is pressure: get more agents near survival deficit after law passage, or accept a slightly longer post-law window

## If You Continue This Work
- preserve the current harness logic that loads stop-time technical reports
- keep the docs in sync with any threshold or mode changes
- if you change governance timing, rerun:
  - one `control` eval
  - one `interestingness` eval
- if you want to compare exploratory conditions credibly, add at least `3` interestingness replicates for that condition or treat it as observational only
- if you tune governance next, also measure proposal creation rate, not just votes
- after the proposal-salience prompt rerun, proposal creation is no longer the main bottleneck; focus next on vote opportunity timing and proposal-deadline interrupts
- the short-law rerun moved the bottleneck again: votes and law passage now work in the compressed window, so focus next on post-law reserve necessity rather than governance conversion

## Next Good Improvements
- store an explicit stop-time eval snapshot per run to avoid recomputing from mixed sources
- add a `--skip-smoke` flag for faster repeated tuning loops
- add optional per-mode runtime config presets beyond `AGENT_LOOP_DELAY_SECONDS`
- if short-run votes are a goal, test shorter voting windows in development only
- tighten interestingness gates if you want them to reflect stronger emergence:
  - require at least one of votes, trade, conflict, or passed laws
  - consider downweighting pure work-volume as an emergence proxy
- add proposal diagnostics next if vote diagnostics keep showing zero deadline interrupts:
  - if needed after the current harness change, add context-level instrumentation for:
    - how many active proposals appear in context
    - how often agents choose `create_proposal`
    - whether proposal opportunities cluster by agent or checkpoint
