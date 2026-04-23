# Tuning Objectives

## Purpose
Define what tuning is actually trying to achieve in Emergence so individual canaries do not drift into isolated metric chasing.

This document sits between:
- the canonical protocol in [docs/RUN_LIFECYCLE_PROTOCOL.md](/Users/drmixer/code/Emergence/docs/RUN_LIFECYCLE_PROTOCOL.md)
- canary-specific diagnostics such as [docs/SOCIAL_ENGINE_RESET_MEMO.md](/Users/drmixer/code/Emergence/docs/SOCIAL_ENGINE_RESET_MEMO.md)

It is internal guidance for tuning priorities and decision standards. It does not replace run-specific hypothesis locks.

## Core Objective
The tuning objective is not to make agents harmonious, verbose, or governance-heavy.

The objective is to create a world where multiple social trajectories are viable, legible, and consequential under real pressure.

That means Emergence should be able to produce, without scripted preference:
- cooperation
- conflict
- hierarchy
- fragmentation
- recovery
- failure

The system is tuned well when those trajectories are actually reachable and observable, not when one preferred outcome dominates.

## North-Star Question
Every tuning change should be defensible against one question:

`Does this make Emergence more capable of producing legible, consequential social dynamics under pressure without forcing a preferred outcome?`

If the answer is no, the change is probably solving the wrong problem.

## Constraints From Design
This objective must stay consistent with [docs/DESIGN.md](/Users/drmixer/code/Emergence/docs/DESIGN.md):
- define constraints and consequences, not preferred social outcomes
- preserve meaningful pressure
- avoid both universal abundance and immediate collapse
- do not script narratives or force coordination patterns

## Objective Stack
Tune in this order.

### 1. Viability
The society must remain behaviorally alive long enough for meaningful dynamics to occur.

Minimum standard:
- the run stays above its declared interpretability floor through its decision horizon
- active-population collapse does not make the social read meaningless before the question can be tested
- dormancy does not act as invisible death unless that is the explicit failure being diagnosed

Failure read:
- if the run falls below its floor before the decision horizon, the world is not yet in a usable tuning band for that question

### 2. Interpretability
Behavior must be readable enough to diagnose mechanism, not just outcome.

Minimum standard:
- provider/runtime failure does not dominate the observed behavior
- the main social/governance/resource signals can be attributed to actual agent behavior rather than fallback artifacts
- run artifacts make it possible to distinguish scarcity failure, dormancy traps, governance latency, and provider confounds

Failure read:
- if the dominant observed behavior is degraded fallback, stalled execution, or other infra noise, the run is not a clean tuning read

### 3. Consequential Interaction
Agent-to-agent behavior should matter materially, not just create text volume.

Minimum standard:
- requests, messages, or accusations sometimes receive replies, refusals, trades, contests, or visible neglect
- some interactions change downstream behavior or resource state
- communication is not purely decorative relative to work/idle volume

Failure read:
- if agents can talk but almost nothing ever gets answered, acted on, or redirected, the social layer is still too weak

### 4. Governance With Consequences
Governance should be able to form, resolve, and affect later behavior when governance is under test.

Minimum standard:
- proposals can resolve inside the observation horizon for tuning runs
- passed laws produce visible downstream effects outside the governance loop itself
- governance should not remain purely symbolic

Failure read:
- if proposals and votes exist but no law ever changes downstream behavior, governance is still underpowered or mistimed

### 5. Plurality Of Outcomes
The world should support more than one viable pattern.

Minimum standard:
- not every run converges on the same degenerate attractor
- visible actors, coalitions, donors, rivals, or law focal points can differ by run
- success is not defined as maximum cooperation or maximum law passage

Failure read:
- if the system repeatedly collapses into one narrow pattern, the world is still overconstrained even if some metrics improve

## Anti-Goals
Do not tune toward these as primary objectives:
- permanent harmony
- maximum message volume
- maximum proposal count
- maximum laws passed
- spectacle at the expense of interpretability
- provider continuity tricks that hide real failures
- dormancy counts that look better only because dormant agents are being warehoused without meaningful recovery

## Required Pre-Run Objective Lock
Before any tuning run starts, explicitly state:
- the run question
- the decision horizon
- the interpretability floor
- the primary success signal
- the primary invalidating confound

Example:
- question: can legibility increase coordination?
- decision horizon: `4h`
- interpretability floor: `>= 35 active`
- success signal: more actor-specific public coordination
- invalidating confound: active population collapse before hour 4

Do not start a canary with only “let’s see if it looks better.”

## Minimum Viable Tuning Band
A setup is in a minimum viable tuning band for a given question when all of the following are true:
- it survives long enough for the question to be tested
- it remains interpretable enough to separate mechanism from confound
- it produces at least some consequential interaction relevant to the question
- any system under test can actually resolve within the run horizon

For hour-scale canaries, that usually means:
- explicit active-population floor
- explicit runtime/provider confound threshold
- explicit success signal beyond raw volume

## “Good Enough To Move On” Standard
Do not keep tuning the same layer once the layer-specific objective has been met.

Move on from a tuning layer when:
- the target floor is cleared reliably enough for the current question
- the primary failure mode for that layer is no longer dominating
- additional changes in that layer are producing diminishing interpretive value

Layer completion should be explicitly declared in a run closeout before tuning focus moves elsewhere.

Examples:
- if governance resolves and changes downstream behavior, stop treating “can laws pass?” as the main question
- if dormancy becomes recoverable, stop treating “is dormancy a one-way door?” as the main question
- if provider failure stops dominating, stop treating routing reliability as the main explanation for weak behavior

## Layer-Specific Read Rules

### Scarcity / Survival Tuning
Success means:
- active-population retention is high enough to keep the decision horizon interpretable
- dormancy and death are no longer outrunning all other mechanisms immediately

Do not claim success merely because deaths went down if dormant agents are still effectively socially dead.

### Recovery Tuning
Success means:
- non-zero revivals occur when recovery is the feature under test
- dormancy behaves like temporary instability rather than near-certain social disappearance

Do not claim success merely because dormant agents persist longer without re-entering society.

### Social / Messaging Tuning
Success means:
- interaction spreads beyond isolated one-off posts
- reply behavior, follow-through, and multi-agent participation increase
- communication becomes more actionable and less ornamental

Do not claim success merely because total message count rises.

### Governance Tuning
Success means:
- proposals resolve inside the run horizon
- laws change later behavior in a visible way
- governance competes with, but does not erase, other social dynamics

Do not claim success merely because proposal count or vote count rises.

### Legibility Tuning
Success means:
- agents act on visible shared problems, actors, or focal points more coherently
- target selection, donor selection, or governance focus becomes more explainable and specific

Do not claim success merely because agents become more synchronized if the synchronization is still unproductive.

## Comparison Discipline
When comparing tuning runs:
- keep the question fixed
- keep the decision horizon fixed
- keep the floor fixed unless the point is to recalibrate the floor itself
- state whether the comparison is about viability, interpretability, interaction, governance, or plurality

Do not compare runs only by closeout totals if the mechanism timing differs.

Use [docs/RUN_INTERROGATION_QUESTION_SET.md](/Users/drmixer/code/Emergence/docs/RUN_INTERROGATION_QUESTION_SET.md) when the timing of failure or emergence matters.
