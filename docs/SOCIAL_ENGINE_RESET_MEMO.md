# Social Engine Reset Memo

## Status
- Date: April 21, 2026
- Scope: exploratory/tuning-run diagnosis only
- Run used as the strongest live failure example: `real-20260420T230647Z`
- Clean Canary A rerun completed: `real-20260421T095330Z`

## Live Symptom Snapshot
- As checked during the run on April 21, 2026, the active population had collapsed to `15 active`, `7 dormant`, `28 dead`.
- Run-window message mix was effectively private-only: `11 direct_message`, `0 forum_post`, `0 forum_reply`.
- Governance attempts existed, but governance outcomes did not:
  - `17 create_proposal`
  - `113 vote`
  - `0 proposal_resolved`
  - `0 law_passed`
- The event mix was dominated by routine survival actions:
  - `3703 work`
  - `469 idle`
  - then a steep drop to everything else

## Clean Canary A Result
- Run: `real-20260421T095330Z`
- Condition: `real_scarcity_tuning_20260421_tight_v6_canary_a_clean_memory_reset`
- Duration: just under `10 hours`
- Final population:
  - `4 active`
  - `5 dormant`
  - `41 dead`
- Communication:
  - `4 forum_post`
  - `0 forum_reply`
  - `5 direct_message`
- Governance:
  - `8 create_proposal`
  - `34 vote`
  - `0 proposal_resolved`
  - `0 law_passed`
- Social/conflict:
  - `3 request_aid`
  - `1 refuse_aid`
  - `1 trade`
  - `0 public_accusation`
  - `0 contest_proposal`
- Action mix:
  - `1761 work`
  - `941 idle`
  - then a steep drop to everything else
- Runtime action mix:
  - `200` checkpoint actions
  - `46` deterministic routine fallback actions

## Clean Canary A Decision
- Canary A failed cleanly.
- The stale long-term memory confound was removed before this rerun by clearing `AgentMemory`, `AgentRelationshipMemory`, and checkpoint intent state during preset reset.
- Even with that fix and the social-follow-up patch in place, the run still produced:
  - too much death
  - too little messaging
  - no proposal resolution
  - no law passage
- Conclusion:
  - the current scarcity-heavy setup still does not produce the desired social/public/governance behavior
  - do not continue tuning this exact setup with another `tight_v*` iteration

## Confirmed Failure Modes

### 1. Social and governance intent is flattened back into routine work
- The agent loop only calls the LLM at checkpoints; otherwise it executes `routine_executor.build_action(...)` directly: [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:193), [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:206).
- Checkpoints are spaced at `45` to `90` minutes, with only limited social acceleration to `20` minutes when softer signals accumulate: [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:67), [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:74), [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:642), [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:655), [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:683).
- Between checkpoints, `governance` and `social_coordination` intents are deterministically converted back into `work`, not follow-up social actions: [backend/app/services/routine_executor.py](/Users/drmixer/code/Emergence/backend/app/services/routine_executor.py:120).
- Result: even when an agent chooses a social action at a checkpoint, the next hour is largely spent farming.

### 2. Social memory exists, but low-social runs self-zero it
- Relationship memory is explicitly emptied at fresh-run context build time whenever a live run window exists: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:40), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:482).
- The strongest social guidance only becomes available when recent pressure, rivals, alignments, or tensions already exist: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:346), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:955).
- Result: when the run starts flat, agents receive the weakest social framing precisely when they most need bootstrapping context.

### 3. World-state is legible as aggregate scarcity, not as social structure
- Agents see global counts and common-pool totals, but not a compact public picture of who is strongest, weakest, most vocal, or driving proposals: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:898), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:903).
- Proposal context is visible, but actor legibility is thin and mostly local to the current proposal list: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:742).
- Result: agents see “the world is under pressure,” but not “who to trust, resist, blame, recruit, or rally around.”

### 4. Public communication is present in the action space but weak in the prompt surface
- Forum and direct-message context is sampled, but surfaced with short previews and narrow windows: `FORUM_THREAD_CONTEXT_LIMIT = 4`, `DIRECT_CONVERSATION_LIMIT = 3`, `_preview_untrusted_text(..., limit=120)`: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:29), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:33), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:49), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:693), [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:724).
- Action costs are low for communication, so this is not primarily an action-cost problem: [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:941).
- Result: agents can communicate, but the prompt gives them limited public substance to respond to, and the routine layer suppresses follow-through anyway.

### 5. Governance resolution is not absent because the resolver never runs
- Proposal resolution runs every `5` minutes in the scheduler: [backend/app/services/scheduler.py](/Users/drmixer/code/Emergence/backend/app/services/scheduler.py:1244).
- Proposal close times are configurable but created from `PROPOSAL_VOTING_HOURS` at action execution time: [backend/app/services/actions.py](/Users/drmixer/code/Emergence/backend/app/services/actions.py:927).
- So the stronger explanation is not “the system forgot to resolve proposals,” but “the social loop is too slow and too weak for proposals to reach consequential resolution in time.”

## What Not To Touch Next
- Do not do another scarcity-only tightening pass. The current evidence does not support scarcity as the primary missing ingredient.
- Do not add provider/model fallback or other protocol-level routing changes. That is outside the diagnosed failure mode and is guarded by [docs/RUN_LIFECYCLE_PROTOCOL.md](/Users/drmixer/code/Emergence/docs/RUN_LIFECYCLE_PROTOCOL.md).
- Do not add cross-run relationship carryover yet. It could mask the in-run bootstrapping failure rather than solve it.
- Do not do `tight_v7`.
- Do not redesign the entire economy before testing social legibility and explicit shared-problem framing in isolation.

## Open Confound To Clear
- Local notes already flag dirty-start canaries and recommend one clean canary before further scarcity tuning: [Apr20TODO.md](/Users/drmixer/code/Emergence/Apr20TODO.md:60), [Apr20TODO.md](/Users/drmixer/code/Emergence/Apr20TODO.md:80).
- The fresh-start memory contamination issue was confirmed and fixed on the preset reset path before the clean Canary A rerun.
- Treat dirty starts as cleared for the specific `real-20260421T095330Z` rerun, but keep them in mind when interpreting earlier canaries.

## Canary A: Responsive Social Loop

### Goal
- Test whether richer social/governance behavior appears when the routine layer stops drowning checkpoint choices.

### Minimum Observation Window
- Judge this canary at `4 hours` and only if at least `30 agents` are still active at that point.
- If the run falls below `30 active` before the `4 hour` mark, treat the result as confounded by population collapse rather than as a clean social-engine read.

### Baseline
- Keep the current scarcity preset and world mechanics unchanged.
- Keep proposal voting windows unchanged.
- Keep relationship reset semantics unchanged.

### Diff
1. In [backend/app/services/routine_executor.py](/Users/drmixer/code/Emergence/backend/app/services/routine_executor.py:120):
   - Change `strategy in {"governance", "social_coordination"}` from `work` fallback to `idle`, or a lightweight low-cost “social attention” action if one exists.
   - Explicitly avoid turning civic intent into farming.
2. In [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py:74):
   - Tighten low-priority social acceleration from `20` minutes to a smaller value for agents with recent DMs, replies, proposal contests, or direct social pressure.
   - Do not change the global checkpoint range yet; only shorten socially active follow-up.

### Measure
- Forum posts and forum replies per hour
- Share of runtime actions that are checkpoint vs deterministic routine fallback
- Proposal resolution count
- Law passage count
- Fraction of non-`work` / non-`idle` actions

### Success
- Clear increase in public replies/posts without changing scarcity.
- At least `2` proposals resolve while the population is still above `30 active` agents.
- Routine actions no longer dominate immediately after social/governance checkpoints.

### Outcome
- Failed.
- The clean rerun never approached the governance threshold and never generated meaningful public discussion.
- This is evidence that social-loop follow-up alone is not enough in the current world design.

## Canary B: Legible Interdependence

### Goal
- Test whether agents coordinate more when the shared problem and the social map are made explicit in-context.
- Keep enough agents alive long enough for that question to be observable; a collapsed run is not a clean legibility read.

### Minimum Observation Window
- Judge this canary at `4 hours` and only if at least `35 agents` are still active at that point.
- If the run falls below `35 active` before the `4 hour` mark, treat the result as confounded by population collapse rather than as a clean legibility test.

### Baseline
- Keep routine cadence unchanged from Canary A baseline.
- Keep reserve semantics, death threshold, and all non-scarcity world mechanics unchanged.
- Add one modest scarcity relaxation layer specifically to preserve enough headroom for the first `4 hours`.

### Diff
1. In [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:903):
   - Add one named shared-deficit line to `GLOBAL STATE`, not just raw pool numbers.
   - Format it as an explicit collective problem with magnitude, for example:
     - “Collective survival gap: current active+dormant upkeep exceeds visible food/energy support by X this cycle.”
   - The point is not new mechanics; it is explicit framing of a shared coordination problem.
2. In [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:898):
   - Add a small public leaderboard section:
     - top 3 resource holders
     - bottom 3 at-risk agents
     - most recent proposal author or most recent contested proposal
   - Keep it short and concrete.
3. In [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py:49):
   - Increase forum/direct message preview length above `120` characters so messages are more actionable when sampled.
4. In [backend/app/services/scarcity_presets.py](/Users/drmixer/code/Emergence/backend/app/services/scarcity_presets.py):
   - Add a dedicated Canary B preset with a modest food-side relaxation relative to Canary A.
   - Keep everything else at Canary A baseline.
   - The goal is not abundance; it is enough headroom to hold `>= 35 active` agents through the observation window so legibility has time to matter.
5. For future hour-scale tuning runs:
   - Keep the public/default proposal window unchanged.
   - Add a tuning-only shorter proposal voting window plus faster resolution cadence so proposal/law outcomes can resolve inside the canary horizon.
   - Otherwise `0 laws passed` remains partly a clock artifact rather than a clean social-engine read.

### Measure
- Active-agent count at `4 hours`
- Direct-message to forum-post ratio
- Forum reply depth
- Number of distinct agents participating in public discussion
- Proposal creation after explicit shared-deficit framing
- Whether conflict/action targets become more concentrated around visible actors

### Success
- `>= 35` active agents at the `4 hour` mark.
- Agents reference named public actors or the shared deficit in proposals, accusations, replies, or trade/aid behavior.
- Public messaging rises without requiring harsher scarcity.
- Coordination attempts become more legible and more actor-specific.

### Failure Interpretation
- If the run drops below `35 active` before the `4 hour` mark, scarcity is still the blocking variable and Canary B is not yet a clean legibility test.
- If the run stays above the floor and still fails to generate public/social/governance behavior, legibility is less likely to be the primary missing ingredient.

## Decision Rule After The Two Canaries
- If Canary A succeeds and Canary B fails:
  - the main bottleneck was response-loop suppression.
- If Canary B succeeds and Canary A fails:
  - the main bottleneck was world-state legibility.
- If both succeed:
  - proceed to a broader social-engine redesign with confidence.
- If both fail:
  - the next target is the checkpoint prompt/reasoning layer itself, not scarcity tuning.

## Current Recommendation
- Treat Canary A as a clean failure.
- Treat the Canary B rerun as a confounded failure on the survival-floor criterion.
- Before rerunning legibility, calibrate a survival window that can hold `>= 40 active`
  agents through hour 4 and ideally `>= 30 active` through hour 8.
- Keep the Canary B legibility/context changes intact during that calibration.
- Tune only scarcity/headroom until the observation window is stable enough to make the
  social read interpretable.

## Canary C: Survival Window Calibration

### Goal
- Find the minimum scarcity band that preserves an interpretable active population for hour-scale runs.
- Do not add new social or governance changes in this phase; this is an economics/headroom calibration only.

### Minimum Success
- `>= 40 active` agents at `4 hours`
- `>= 30 active` agents at `8 hours`

### Constraints
- Keep the Canary B legibility patch in place.
- Keep reserve semantics, death threshold, and other non-scarcity mechanics unchanged.
- Keep the tuning-only shorter proposal window for canaries so governance outcomes can resolve inside the run.

### Decision Rule
- If Canary C still misses the active-population floor, scarcity remains the blocking variable.
- If Canary C clears the floor, rerun Canary B legibility inside that band before drawing conclusions about the social engine.

## Canary D: Recovery Width Calibration

### Goal
- Test whether dormancy can become a recoverable state instead of a one-way door.
- Keep the Canary C active-survival economics unchanged.
- Change only the recovery pathway width.

### Diff From Canary C
- Re-enable `SURVIVAL_RESERVE_AUTO_CONTRIBUTION_ENABLED`.
- Re-enable `SURVIVAL_RESERVE_AUTO_REVIVE_ENABLED`.
- Keep `SURVIVAL_RESERVE_ACTIVE_AID_ENABLED = False`.
- Keep `SURVIVAL_RESERVE_DORMANT_MAINTENANCE_ENABLED = False`.

### Why
- Canary C showed `44` dormancy transitions and `0` revivals.
- Under that setup, recovery depended almost entirely on timely `trade`, while dormant agents could not act for themselves.
- Canary D tests the smallest reserve change that widens the re-entry path without broadly subsidizing all active shortfalls or merely preserving a large dormant pool.

### Success Read
- Dormancy should stop behaving like soft death.
- The run should produce non-zero revivals.
- The active population should decline more slowly than in Canary C, even if scarcity still needs further tuning afterward.

## Canary E: Response Loop Calibration

### Goal
- Test whether agents begin answering each other more consistently now that the world is survivable.
- Keep the Canary D survival and recovery baseline fixed.
- Change only response visibility and response timing.

### Baseline
- Keep the Canary D survival economics unchanged.
- Keep reserve auto-contribution and reserve auto-revive enabled.
- Keep reserve active-aid and dormant-maintenance disabled.
- Keep canary proposal timing unchanged.

### Diff
1. In [backend/app/services/agent_loop.py](/Users/drmixer/code/Emergence/backend/app/services/agent_loop.py):
   - Pull low-priority social follow-up checkpoints forward more aggressively when agents receive a recent DM, aid request, or forum reply.
   - This is a timing change, not a behavior override.
2. In [backend/app/services/context_builder.py](/Users/drmixer/code/Emergence/backend/app/services/context_builder.py):
   - Add a compact incoming-request inbox that shows:
     - who asked
     - exact amount and resource
     - whether helping would visibly keep the requester active this cycle
     - any visible relationship or governance tie
   - Make pending inbound requests legible enough to answer directly with `trade`, `refuse_aid`, or conditional `direct_message`.

### Success Read
- Survival floor still holds:
  - `>= 40 active` at `4h`
  - `>= 30 active` at `8h`
- Non-zero bilateral follow-through appears:
  - `trade` and/or `refuse_aid`
  - more multi-turn DM or forum exchange
- Response breadth improves:
  - not just whether responses occur
  - but how many distinct agents are responding
- If responses rise but only a few agents handle them, treat donor congestion as the next diagnosis rather than claiming the response loop is solved.

### Decision Rule
- If Canary D still produces near-zero revivals, dormancy recovery remains structurally too narrow.
- If Canary D restores meaningful revivals but active retention is still weak, keep the recovery pathway and retune active survival economics next.

### Outcome
- Passed on the response-loop question after stripping out provider and action-affordance confounds.
- Run: `real-20260423T120719Z`
- Condition: `real_scarcity_tuning_20260423_canary_e_response_loop_v1`
- Duration: `8h`
- Closeout survival:
  - `37 active / 13 dormant / 0 dead`
  - `64` dormancy events
  - `51` revivals
- Raw bilateral follow-through was `5/10` aid requests, but the clean read was stronger:
  - `4` unanswered requests targeted Orbit-12, whose next checkpoints failed on `gemini-2.0-flash` rate limits and whose run record was `6` successes / `61` failures.
  - `1` unanswered request targeted Vector-02, which had `0.00` energy and could not afford even a low-cost communicative action before going dormant.
  - Excluding those confounds, answerable requests had `5/5` bilateral follow-through via `trade` or `refuse_aid`.
- Decision:
  - the response loop works when agents can actually think and afford a response
  - the next blocker is provider reliability/observability, not another response-loop behavior change

## Canary F: Provider-Clean Response/Governance Read

### Pre-F Routing Intervention
- Keep tier composition unchanged.
- Keep the `gm_gemini_2_0_flash` cohort label for attribution continuity.
- Route that cohort to `gemini-2.5-flash` before Canary F because Canary E showed `gemini-2.0-flash` was functionally unavailable under run pressure.
- Disable Gemini 2.5 Flash thinking on the action-JSON route (`thinking_budget=0`) because smoke testing showed the full checkpoint prompt could otherwise spend output budget on hidden reasoning and return truncated JSON.
- After an aborted `1m41s` Canary F smoke (`real-20260424T013348Z`), also route `gm_gemini_2_0_flash_lite`, `or_gpt_oss_20b_free`, and `or_qwen3_4b_free` to direct `gemini-2.5-flash`; the Lite cohort rate-limited under burst pressure and the OpenRouter free cohorts returned `503 no healthy upstream`.
- Keep direct Mistral unchanged because it remained stable under Canary E and the aborted F smoke.
- Treat this as an explicit inter-run provider reliability intervention, not fallback.

### Pre-F Fixes
- Suppress near-duplicate active proposals so governance novelty is not inflated by repeated reserve laws.
- Add or verify reporting that separates aid-request outcomes into:
  - answered
  - provider-confounded
  - mechanically unaffordable
  - clean unanswered
- Verify `Replies` includes forum replies plus follow-up DMs.
- Verify dormant agents are not eligible aid-request targets.

### Outcome
- Passed on the provider-stabilized response-loop question.
- Run: `real-20260424T020150Z`
- Condition: `real_scarcity_tuning_20260424_canary_f_provider_stabilized_response_governance_v1`
- Duration: `8h`
- Closeout survival:
  - `41 active / 9 dormant / 0 dead`
  - `24` dormancy events
  - `15` revivals
- Provider read:
  - `647 / 647` LLM calls succeeded
  - `0` provider failures
  - `0` rate limits
  - `0` provider fallback
- Response-loop read:
  - `15` aid requests
  - `11` trades
  - `4` aid refusals
  - `7` distinct trade/refusal responders
  - direct aid requests received concrete bilateral follow-through rather than only reserve rescue
- Governance read:
  - `5` proposals created
  - `5` proposals resolved
  - `5` laws passed
  - duplicate-proposal suppression prevented mechanical stacking but exposed recovery/label noise when agents attempted near-duplicate governance actions
- Operational caveat:
  - a post-frontend-fix push redeployed backend/worker/frontend during the live run; the run stayed active and provider health remained clean, but this counts as an operational caveat
- Decision:
  - provider stabilization worked
  - the response loop works under clean provider conditions
  - the next blocker is governance recovery polish and feed interpretability, not another provider or scarcity change

## Canary G: Governance Recovery And Feed-Clarity Check

### Goal
- Test whether post-F governance recovery polish reduces degraded fallback/governance idle noise while preserving Canary F's provider-clean response-loop gains.
- Keep Canary F's provider-stabilized routing and Canary D/E/F survival/recovery economics fixed.
- Change only the governance-recovery and feed-label polish already implemented after Canary F.

### Baseline
- Keep provider-stabilized cohort routing:
  - `gm_gemini_2_0_flash` -> direct `gemini-2.5-flash`
  - `gm_gemini_2_0_flash_lite` -> direct `gemini-2.5-flash`
  - `or_gpt_oss_20b_free` -> direct `gemini-2.5-flash`
  - `or_qwen3_4b_free` -> direct `gemini-2.5-flash`
  - direct Mistral unchanged
  - paid OpenRouter anchors unchanged
- Keep the same tier labels and cohort labels for attribution continuity.
- Keep the same survival economics and reserve settings as Canary F.
- Keep the tuning proposal window and resolver cadence unchanged.

### Diff
1. Duplicate proposal validation now exposes structured `duplicate_active_proposal` metadata with the existing proposal id.
2. Checkpoint attempts to create a near-duplicate proposal recover into:
   - `vote` on the existing proposal when valid
   - `forum_reply` on a matching proposal discussion when already voted
   - otherwise a consolidation `forum_post`
3. Idle event descriptions now distinguish:
   - social/governance follow-up holds
   - governance follow-up holds
   - social follow-up holds
   - checkpoint recovery holds
   - generic energy conservation

### Success Read
- Provider health remains clean enough for interpretation:
  - no provider-failure burst
  - no provider/model fallback
  - no repeated degraded provider messages
- Survival floor still holds:
  - `>= 40 active` at `4h`
  - `>= 30 active` at `8h`
- Response loop does not regress:
  - aid requests still receive `trade`, `refuse_aid`, DM, or forum follow-through
  - responder breadth remains visible and not fully collapsed into one donor
- Governance recovery improves:
  - near-duplicate proposal attempts no longer become degraded fallback posts
  - governance intent converts into vote/discussion/consolidation more often than generic routine fallback
- Feed clarity improves:
  - repeated deterministic holds no longer dominate the feed as `Agent chose to rest`
  - runtime idle volume remains technically visible without making the public feed look falsely inert

### Invalidating Confounds
- Any provider-failure burst resembling the aborted Canary F smoke.
- Any push/deploy during the active run unless explicitly approved as a live-run intervention.
- Population collapse below the survival floor before the question can be tested.

### Decision Rule
- If G preserves F's response-loop gains and reduces degraded governance fallback/feed noise, move on from response-loop/governance-recovery tuning.
- If response-loop behavior regresses under clean providers, inspect the new governance recovery path for accidental suppression.
- If provider health fails, classify the run as provider-confounded rather than behavioral.

## Canary H: Longer-Horizon Death Reachability And Response-Loop Check

### Goal
- Test whether death is naturally reachable under the current scarcity/dormancy settings when the run has enough time for dormant upkeep failures to compound.
- Re-check Canary G's donor concentration and clean unanswered aid requests under a longer horizon before adding any donor-routing or routine-layer behavior changes.
- Verify that feed-only suppression of repeated deterministic hold-position idles improves public readability without changing raw run telemetry.

### Baseline
- Keep Canary G's provider-stabilized routing, tier labels, scarcity economics, governance recovery path, and deterministic fallback semantics unchanged.
- Run class remains `special_exploratory`.
- Planned horizon: `16h`.
- Expected ledger cost from Canary G burn rate: about `$1.02`, with OpenRouter projected around `$0.25` if G-like.

### Interpretability Floor
- Mid-run checkpoint: `8h`.
- Continue the full 16h read only if active population is still `>= 30`.
- If active population is below `30` at `8h`, pause for review and treat the second-half evidence as collapse-dominated rather than cleanly interpretable.

### Success Read
- Provider health remains clean:
  - no provider-failure burst
  - no provider/model fallback
  - OpenRouter spend remains within available credit headroom
- Survival/death mechanics become interpretable:
  - dormant duration distribution is visible
  - any death can be traced through resource state, reserve support, aid requests, and follow-through
- Response-loop behavior remains readable:
  - aid requests split into answered, mechanically unaffordable unanswered, provider-confounded unanswered, and clean unanswered
  - requester/target/status patterns are reviewed for the clean unanswered set
- Donor concentration is measured, not tuned:
  - top donor share
  - unique donor count
  - repeated donor burden
- Feed readability holds:
  - default public feed is viewer-visible/salient
  - raw DB/report event totals remain available for audit comparison

### Reporting Note
- Closeout reports and direct DB queries count raw events, including deterministic routine hold-position idles.
- The default public live feed and `/api/events` suppress repeated deterministic hold-idles for readability.
- Use `/api/events?include_routine_hold_idles=true` when comparing the feed endpoint against raw closeout totals.

### Decision Rule
- If H produces death, trace whether it came from intended scarcity pressure, response-loop failure, reserve exhaustion, or an operational/provider confound.
- If H still produces no deaths with meaningful dormant duration, treat current settings as death-resistant and consider a scarcity/upkeep tuning pass.
- If donor concentration or clean unanswered requests repeat at meaningful scale, plan a narrow donor/aid-routing intervention for the next canary.
- If they do not repeat, leave donor mechanics unchanged.
