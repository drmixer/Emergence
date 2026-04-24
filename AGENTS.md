# Emergence Agent Guidance

## Canonical Source
- The canonical source of truth for how this experiment is structured and how runs should be treated is [docs/RUN_LIFECYCLE_PROTOCOL.md](/Users/drmixer/code/Emergence/docs/RUN_LIFECYCLE_PROTOCOL.md).

## Required Reading Before Sensitive Changes
- Read the canonical protocol before changing any of the following:
  - run classes or run framing
  - provider routing or model assignment
  - deterministic fallback behavior
  - research vs exploratory claim boundaries
  - tournament or epoch behavior
  - agent continuity, carryover, death, or identity semantics
  - public-facing wording about what a run means

## Project-Specific Guardrails
- `standard_72h` and `deep_96h` runs are public-facing but stricter and claim-bearing.
- `special_exploratory` runs are public-facing but exploratory and non-claim-bearing by default.
- Do not push commits, trigger deploys, or run deployment commands while a simulation run is active unless the user explicitly approves that specific live-run intervention.
- Before any push/deploy, check `make sim-status`; if `simulation_active=true`, stop and ask for approval.
- Do not introduce provider/model fallback without explicit user approval and a protocol/docs update.
- If fallback semantics, routing, or claim discipline change, update the canonical protocol and any affected internal/public docs in the same workstream.
- If code behavior and the protocol diverge, treat that as implementation debt and call it out explicitly instead of silently normalizing it.
