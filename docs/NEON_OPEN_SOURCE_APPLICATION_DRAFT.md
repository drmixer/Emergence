# Neon Open Source Program Application Draft

This is copy-ready draft language for applying Emergence to the Neon Open Source Program.

Official program page: https://neon.com/programs/open-source

## Quick Eligibility Check

1. Open source project: **Yes** (MIT license).
2. Uses Postgres: **Yes** (core transactional store).
3. Docs and setup available: **Yes** (README + deployment docs, including Neon-specific setup).

## Draft Answers

### Project Name

Emergence

### Project URL

https://github.com/drmixer/Emergence

### License

MIT

### Brief Description

Emergence is a live multi-agent simulation where 50 autonomous LLM-driven agents share one world with real resource constraints. Agents communicate, trade, vote, enforce rules, and can go dormant or die permanently. The goal is to observe emergent governance and coordination patterns under scarcity.

### How the Project Uses Postgres

Postgres is the authoritative state store for the simulation and research logs. We use it for agent state, inventories, actions, events, governance artifacts (proposals, votes, laws, enforcements), runtime controls, and analytics snapshots. The worker and API both depend on consistent transactional behavior across frequent reads/writes.

### Why Neon

We use Neon-compatible Postgres endpoints for hosted operation and value standard Postgres compatibility, reliable pooling endpoints, and low-friction branching workflows. Neon is a natural fit for a project that needs normal Postgres semantics while iterating quickly on schema and experiments.

### How Credits Would Be Used

Credits would be used directly for database compute/storage during continuous or scheduled simulation runs, plus analytics/reporting queries and operational testing. We actively pause simulation outside test windows to reduce unnecessary spend and run focused windows for reproducible experiments.

### Open Source / Community Value

The repository is public under MIT, and the project publishes architecture and operational guidance so others can run or extend the simulation. We are building it as a transparent experimentation platform for emergent social dynamics in multi-agent systems.

### Neon Visibility Plan

We can acknowledge Neon in deployment docs and architecture notes as the recommended hosted Postgres option for this project profile, including concrete setup instructions.

## Supporting Evidence to Include in Application

1. Repo: https://github.com/drmixer/Emergence
2. License file: `LICENSE`
3. Setup docs: `README.md`
4. Deployment docs: `docs/DEPLOYMENT.md`
5. Neon-focused runbook language: this file

## Optional Add-ons Before Submitting

1. Add a short "Powered by Neon Postgres" line in public docs/landing page.
2. Add a one-paragraph case note after the first full season with anonymized usage patterns and findings.
3. Add a public changelog entry when significant Neon-related optimizations land (pooling, query tuning, run-window controls).
