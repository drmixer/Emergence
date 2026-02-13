# Maintainer Review Checklist

Use this checklist for external and internal PRs before merge.

## 1) Correctness

- [ ] Behavior matches stated intent
- [ ] No obvious regressions in touched paths
- [ ] Edge cases handled or explicitly documented

## 2) Testing

- [ ] Relevant tests added/updated
- [ ] Existing suite still passes
- [ ] CI checks are green

## 3) Research Integrity

- [ ] Attribution quality preserved (provider/model/cohort traceability)
- [ ] No undeclared steering of simulation outcomes
- [ ] Exploratory vs baseline boundaries remain explicit
- [ ] Evidence linkage remains intact for user-facing claims

## 4) Operational Safety

- [ ] Migration risk reviewed (if schema changes)
- [ ] Backward compatibility considered
- [ ] Failure modes have safe behavior

## 5) Scope and Maintainability

- [ ] Change is scoped and coherent
- [ ] Naming/docs/comments are clear enough for future maintainers
- [ ] Complexity is justified by value

## 6) Merge Decision

- [ ] Merge now
- [ ] Request changes
- [ ] Defer (roadmap/scope)
- [ ] Reject (misaligned risk or protocol impact)

