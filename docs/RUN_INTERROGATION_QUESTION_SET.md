# Run Interrogation Question Set

## Purpose
Use this question set to interrogate runs as timelines, not only as end states.

The goal is to answer:
- what changed
- when it changed
- what mechanism seems to be driving the change
- whether the run is still interpretable at that checkpoint

This is for tuning, diagnosis, and canary comparison. It complements closeout reports; it does not replace them.

## Not A Replacement For
This question set is not a replacement for standard run closeout reports, technical reports, or final run summaries.

Use it alongside those artifacts when mechanism and timing matter.

## Core Principle
Do not rely on final run totals alone when tuning the social engine.

End-state summaries answer outcome. They do not reliably answer mechanism.

A run interrogation should produce a consistent checkpoint-by-checkpoint read so we can distinguish:
- social behavior emerging too late
- scarcity overwhelming coordination
- governance starting but resolving too slowly
- provider/runtime confounds distorting behavior
- dormancy traps replacing outright death while still collapsing the active society

## When To Use It
Use this question set for:
- every internal canary
- every run used to justify a tuning change
- any cross-run comparison where mechanism matters, not just outcome

Recommended minimum:
- one interrogation at the midpoint
- one interrogation at the planned decision horizon
- one final closeout interrogation if the run continues past the decision horizon

## Checkpoint Schedule
Use two checkpoint types together.

### 1. Fixed Checkpoints
Ask the full question set at:
- `25%` of planned run duration
- `50%`
- `75%`
- `100%`

If the run ends early, treat the stop point as the final fixed checkpoint.

### 2. Event-Triggered Checkpoints
Add an extra interrogation when one of these happens:
- first meaningful social burst
- first proposal created
- first proposal resolved
- first law passed
- first major dormancy wave
- active population falls below the run's interpretability floor
- provider-failure burst or degraded-fallback burst
- first meaningful recovery cluster

These event-trigger checkpoints are for mechanism reads. They do not replace the fixed schedule.

## Standard Question Set
Ask the same categories at every checkpoint.

### 1. Population State
- What are the current `active / dormant / dead` counts?
- What is the rate of change since the previous checkpoint?
- Is the run above or below its interpretability floor?
- Is attrition showing up as death, dormancy, or both?

### 2. Resource State
- What are the current common-pool food, energy, and materials totals?
- Which agents are currently the most resource-rich?
- Which agents are currently the most fragile?
- How concentrated are resources right now?
- How many active agents appear within one survival cycle of dormancy?

### 3. Social Activity
- What social actions occurred since the previous checkpoint?
- Who initiated them?
- How many distinct agents are sending messages or social actions?
- How broad is participation versus concentration in a few agents?
- Is the run producing forum discussion, direct messaging, aid requests, refusals, accusations, or trade?

### 4. Social Mechanism
- Which social actions appear consequential rather than decorative?
- Did any requests receive replies, refusals, trade, or follow-through?
- Are agents converging on the same donor, same thread, or same governance focal point?
- Is coordination spreading, stalling, or collapsing into one-sided requests?

### 5. Governance State
- Which proposals were created since the previous checkpoint?
- Who authored them?
- How many votes were cast since the previous checkpoint?
- Did any proposals resolve?
- Did any laws pass or fail?
- Is governance ahead of, behind, or mismatched to the crisis horizon?

### 6. Dormancy And Recovery
- Which agents newly went dormant since the previous checkpoint?
- Have any agents recovered?
- If recovery occurred, what caused it: trade, reserve, or endogenous production?
- Is dormancy acting like temporary instability or effectively like social death?

### 7. Provider And Runtime Health
- How many LLM failures occurred since the previous checkpoint?
- What failure types dominated?
- How many degraded fallback actions or posts occurred?
- Is the run still behaviorally interpretable, or is infra noise now a primary confound?

### 8. Mechanism Read
- What is the dominant mechanism at this checkpoint?
- Is social coordination gaining ground faster than attrition, or slower?
- If the run ended now, what would the diagnosis be?

## Standard Output Format
Each interrogation should produce the same four sections.

### State
Summarize current population, resources, social activity, governance, and provider health.

### Change Since Last Checkpoint
Summarize what materially changed since the last interrogation.

### Mechanism Read
State the best current explanation in one short paragraph.

### Decision
End with one explicit line such as:
- `Decision: social layer present but losing to dormancy pressure`
- `Decision: governance active, but resolution still lags crisis window`
- `Decision: provider-confounded; behavioral read unsafe`
- `Decision: still above floor; continue run`
- `Decision: below floor; stop early and classify scarcity as blocking`

## Required Comparison Discipline
When comparing runs:
- ask the same question set
- use the same checkpoint structure
- name the active interpretability floor explicitly
- separate social failure from provider failure
- separate dormancy collapse from death collapse

Do not change the question set ad hoc just because a run has an eye-catching anomaly.

If a new anomaly matters, add it as an extra note after the standard output, not instead of it.

## Minimum Data To Pull At Each Checkpoint
At each interrogation, gather at least:
- active / dormant / dead counts
- delta from previous checkpoint
- message and social-action counts by type
- proposal and vote activity
- current active laws
- top resource-rich agents
- most fragile agents
- newly dormant agents
- recovered agents
- provider failures and degraded fallback counts

## Canary-Specific Notes
For internal canaries, the most important checkpoint question is:

`Is social coordination gaining ground faster than attrition, or slower?`

If the answer is clearly "slower" by the decision horizon, the canary has not yet reached a useful tuning band, even if some governance or messaging exists.

## Practical Guidance
Keep the writeup short enough to reuse in-thread during live monitoring.

Good interrogation notes are:
- specific
- comparable across runs
- clear about confounds
- explicit about the current best mechanism read

Bad interrogation notes:
- describe only final totals
- drift into narrative without mechanism
- mix infra failure with behavioral diagnosis
- change the framing each time based on whatever looks interesting
