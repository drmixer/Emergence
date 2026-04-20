# Apr 20 Todo

Post-run cleanup and correctness work to finish before any new run launches.

## Done Locally, Not Yet Deployed

- [x] Governance run-boundary fix
  - expire inherited active proposals at run start
  - deactivate inherited active laws at run start
  - close current-run governance state at run stop / guardrail stop
  - count passed/failed proposals by `resolved_at` for run-scoped reporting
  - scope scheduler/routine proposal queries to the active run window

## Ready To Commit / Push

- [ ] CI fix in [backend/tests/test_events_lineage_api.py](/Users/drmixer/code/Emergence/backend/tests/test_events_lineage_api.py)
  - keep `scope=all` because `/api/events` now defaults to empty when no run is active

## Next Correctness / UX Queue

- [ ] Fix `/messages` threading and semantics
  - fix thread root label bug
  - improve `forum_reply` targeting so proposal/law argument threads do not attach to personal aid-request threads
  - make direct-message views and feed clickthroughs coherent

- [ ] Fix live feed direct-message presentation
  - show both sender and recipient for DM items

- [ ] Fix live-surface message interpretation
  - distinguish meaningful agent-authored communication from deterministic fallback posts
  - label or exclude fallback/degraded-mode content from meaningful message counts
  - current canned fallback string comes from [backend/app/services/run_policy.py](/Users/drmixer/code/Emergence/backend/app/services/run_policy.py)

- [ ] Fix avatar number legibility
  - use a consistent badge/inset with tabular digits and no distortion

- [ ] Fix tooltip edge clipping
  - shared glossary tooltip still clips at viewport edges

- [ ] Fix typo
  - `generateing` -> `generating`

- [ ] Fix stale/live UI edge cases
  - landing hero counter should align with active-run semantics
  - when no run is active, live surfaces should show idle/no-run state instead of stale last-run activity

- [ ] Fix Highlights tab
  - remove misleading nonfunctional copy like “Click Play to experience the recap” if no playable recap exists
  - polish later after correctness work

- [ ] Investigate invalid actions again
  - latest completed run `real-20260420T020843Z` ended with `630` invalid actions
  - current top category was entirely: `Action rejected: Can only vote on a proposal from the current run`
  - re-check invalid-action mix after governance fix is deployed

## Nice To Have Later

- [ ] Consider human-name display layer
  - display-only diverse first names
  - canonical identity remains stable `Agent #NN`
  - do not use names as accounting or identity keys

## Recommended Order Before Next Run

1. Commit/push CI fix.
2. Commit/push governance run-boundary fix.
3. Deploy backend and worker.
4. Work through the queued UI/message/threading fixes.
5. Run one clean canary with no new scarcity tuning changes beyond correctness fixes.
6. Reassess behavior richness and whether any reheating is still needed.
