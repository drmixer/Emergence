# Emergence Growth Roadmap

## Objective
Grow qualified audience and repeat usage without compromising evidence integrity.

## Scope for This Revision
Keep:
- Trust/performance foundation and evidence provenance.
- Story surface and replay experience.
- Share flow and social card generation.
- Weekly "State of Emergence" as fully templated and automated output.

Cut for now:
- Follow/subscribe systems.
- Prediction challenges/leaderboards.
- Public highlights API and embeddable widgets.
- Heavy exploratory visualizations (network graph, heatmap).

## Guardrails
- Every public claim must link to verifiable run evidence.
- Growth features cannot script outcomes or alter simulation incentives.
- UX improvements must preserve simulation fidelity and observability.

## Core Metrics
- Funnel: landing -> run page CTR, run page -> replay start rate.
- Activation: time-to-first-wow, replay completion rate.
- Distribution: share action rate, shared-link CTR.
- Retention: D1/D7 return rate for run/replay visitors.
- Trust: percent of visible claims with evidence links (target: 100%).

## Milestone Plan (Fast Execution)

### Milestone 1: Trust + Performance Foundation
- Improve runtime performance (route splitting, lazy loading, defer heavy components).
- Ship public run detail page (`/runs/[runId]`) with source trace links.
- Add scoped provenance contract on claim surfaces:
  - run ID
  - timestamp window
  - verification state

Exit criteria:
- Core pages are smooth on laptop/mobile.
- Claims shown to users consistently map to run evidence.

### Milestone 2: Story + Share Surface
- Launch replay MVP with rule-based major moment detection.
- Redesign event cards with clear major/minor hierarchy.
- Add sticky state strip (Day, Deaths, Laws, Coalition Index, trend).
- Add "Share this moment" from replay and event cards.
- Generate run and moment social cards (OG images).

Exit criteria:
- New visitors can identify what happened within 30 seconds.
- Share action exists in at least 3 high-intent locations.

### Milestone 3: Automated Weekly Digest
- Create fixed digest template with locked sections.
- Auto-generate digest from verified run data on schedule.
- Auto-attach source links for every claim block.
- Output publish-ready markdown without manual editing.

Exit criteria:
- Digest generation is one command/scheduled job.
- Each digest section includes run-backed evidence links.

## Risk Notes and Mitigations
- Replay trust risk: weak highlight detection can reduce credibility.
  - Mitigation: start rule-based and review top runs before broad promotion.
- Provenance sprawl risk: "100%" can balloon if undefined.
  - Mitigation: enforce minimal evidence contract first, then expand.
- Automation drift risk: digest template may break as schema changes.
  - Mitigation: add schema checks and fallback placeholders.

## Immediate Next Actions
- Finalize analytics events for landing, run detail, replay, and share.
- Define the minimal evidence contract (run_id, time_window, source_link).
- Build replay MVP with 3 major-moment rules.
- Implement digest template + generator script + scheduled run path.
