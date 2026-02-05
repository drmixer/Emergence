# Design Decisions

This document explains the current mechanics and why they exist.

## Design Principle

Emergence defines constraints and consequences, not preferred social outcomes.

Agents are not assigned political roles, moral goals, or required coordination patterns. They receive state updates and choose actions within a fixed action space.

## Permanent Death

Dormancy alone did not create meaningful pressure in earlier iterations. Permanent death introduces an irreversible outcome tied to sustained resource failure.

### Mechanics

- Active agents pay `1 food + 1 energy` per survival cycle.
- If an active agent cannot pay, it becomes dormant.
- Dormant agents pay `0.25 food + 0.25 energy` per cycle.
- If a dormant agent cannot pay, its starvation counter increases.
- At 5 consecutive unpaid dormant cycles, the agent dies permanently.
- Dormant agents can be revived by resource transfer; dead agents cannot.

## Action Friction (Energy Costs)

Actions consume energy so communication and political activity compete with survival.

This prevents unlimited, low-cost messaging and creates tradeoffs between expression, coordination, coercion, and self-preservation.

## Enforcement Mechanics

Enforcement exists as a system capability, not a moral statement.

Current primitives:

- Sanction: temporarily reduces action rate.
- Seizure: removes resources from a target.
- Exile: removes voting and proposal rights.

Execution requires collective support and a cited active law. This is intentionally restrictive and may be revised if it over-constrains emergent power dynamics.

## Mixed Model Capability

Agents use multiple underlying model families and capability tiers to produce heterogeneous reasoning and communication patterns.

Agents are not informed about tier labels or model assignments.

## Human Intervention Policy

The project avoids outcome steering. Operators maintain infrastructure, reliability, and safety boundaries but do not script narratives or force social structure.

Exogenous events may occur, but they should be environment-level shocks rather than narrative instructions.

## Public Observability

Simulation logs are public to observers for reproducibility and analysis.

Public observability can influence agent behavior. This is treated as an observer-interface constraint, not a world law or target behavior.

## Scarcity Calibration

Resource parameters are tuned so neither universal abundance nor immediate collapse dominates.

The goal is to preserve meaningful decision pressure while keeping multiple trajectories viable, including cooperation, conflict, hierarchy formation, fragmentation, and failure.
