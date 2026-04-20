# Apr 20 Todo

Post-run cleanup and correctness work to finish before any new run launches.

## Done And Deployed

- [x] CI fix in [backend/tests/test_events_lineage_api.py](/Users/drmixer/code/Emergence/backend/tests/test_events_lineage_api.py)
  - keep `scope=all` because `/api/events` now defaults to empty when no run is active

- [x] Governance run-boundary fix
  - expire inherited active proposals at run start
  - deactivate inherited active laws at run start
  - close current-run governance state at run stop / guardrail stop
  - count passed/failed proposals by `resolved_at` for run-scoped reporting
  - scope scheduler/routine proposal queries to the active run window

- [x] Start/stop correctness hardening
  - fresh starts now require a fresh `run_id`
  - CLI/admin start paths reject accidental dirty-world carryover from dead/dormant/starving state
  - run guardrails auto-stop extinct runs at `0 active / 0 dormant`
  - landing hero live stats now zero out when no run is active

## Done Locally, Not Yet Committed / Deployed

- [x] Fix `/messages` threading and semantics
  - fix thread root label bug
  - improve `forum_reply` targeting so proposal/law argument threads do not attach to personal aid-request threads
  - make direct-message views and feed clickthroughs coherent

- [x] Fix live feed direct-message presentation
  - show both sender and recipient for DM items

- [x] Fix live-surface message interpretation
  - distinguish meaningful agent-authored communication from deterministic fallback posts
  - label or exclude fallback/degraded-mode content from meaningful message counts
  - current canned fallback string comes from [backend/app/services/run_policy.py](/Users/drmixer/code/Emergence/backend/app/services/run_policy.py)

- [x] Fix avatar number legibility
  - use a consistent badge/inset with tabular digits and no distortion

- [x] Fix tooltip edge clipping
  - shared glossary tooltip now renders in a viewport-clamped portal instead of clipping in local containers

- [x] Fix typo
  - `generating` spelling is clean; prior todo text corrected

- [x] Fix stale/live UI edge cases
  - landing hero now keys off active-run semantics instead of stale historical counters
  - no-run live feed now renders an idle state instead of pretending the experiment is merely waiting to start

- [x] Fix Highlights tab
  - recap prompt copy now describes the actual control behavior
  - highlights header copy no longer claims there is a current run when none is active

## Next Correctness / UX Queue

- [ ] Investigate invalid actions again
  - exclude the operationally invalid start-path runs from tuning interpretation:
    - accidental reopened tail of `real-20260420T020843Z`
    - dirty-start canary `real-20260420T124849Z`
  - latest completed valid baseline to re-check should come after the corrected replacement canary
  - re-check invalid-action mix after governance fix is deployed

## Nice To Have Later

- [ ] Consider human-name display layer
  - display-only diverse first names
  - canonical identity remains stable `Agent #NN`
  - do not use names as accounting or identity keys

## Recommended Order Before Next Run

1. Commit/push the current UI/message/threading batch.
2. Deploy frontend and backend together if the backend message-classification changes stay bundled with the UI counts/labels.
3. Run one clean canary with no new scarcity tuning changes beyond correctness fixes.
4. Re-check invalid-action mix on that canary.
5. Reassess behavior richness and whether any reheating is still needed.
