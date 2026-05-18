export const RUN_SCHEDULE = [
  {
    id: 'k12-public-canary',
    label: 'K12',
    theme: 'Viewer Comprehension',
    planningState: 'Locked',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Upcoming',
    plannedStartLabel: 'Target May 21, 2026',
    expectedDuration: '72h target window',
    declaredQuestion: 'Do the new viewer/story/evidence changes make a live run easier to follow?',
    watchFor: 'Watch proposal discussion readability, pile-on reduction, and whether post-run story surfaces identify meaningful moments without work-event noise.',
    declaredCondition: 'Viewer/story/evidence wrapper canary after K11 follow-up fixes',
    changeFromPrior: 'Same public-canary discipline as K11, but with the calendar, story replay, evidence defaults, report reader, and idle landing fixes in place before launch.',
    usefulEvidence: 'Viewers can identify what the run asked, follow live proposal/resource pressure, and use the recap/evidence/report path without confusing archived data for live state.',
    doesNotProve: 'This does not prove a general society pattern or validate the research track; it tests whether the public wrapper is understandable during a live canary.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: '',
    links: {
      live: '/dashboard',
      archive: '/archive',
    },
  },
  {
    id: 'k13-governance-readability-canary',
    label: 'K13',
    theme: 'Governance Readability',
    planningState: 'Tentative',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Tentative',
    plannedStartLabel: 'Tentative late May 2026',
    expectedDuration: '72h target window',
    declaredQuestion: 'Can proposal discussion, voting, and passed laws stay readable without collapsing into agreement pile-on noise?',
    watchFor: 'Watch whether agents respond selectively, whether law debates produce distinct positions, and whether the recap can separate meaningful governance from repeated agreement.',
    declaredCondition: 'Governance readability canary after K12 viewer-comprehension observations',
    changeFromPrior: 'Moves the public-canary focus from whether the wrapper is understandable to whether governance behavior itself remains legible during the run.',
    usefulEvidence: 'Clear proposal threads, fewer repeated agreement waves, visible dissent or tradeoffs, and recap chapters that explain which laws mattered.',
    doesNotProve: 'This does not establish a durable governance finding; it only tests whether the current discussion and replay surfaces can carry governance-heavy behavior.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: '',
    links: {
      live: '/dashboard',
      archive: '/archive',
    },
  },
  {
    id: 'k14-aid-trade-pressure-canary',
    label: 'K14',
    theme: 'Aid and Trade Pressure',
    planningState: 'Tentative',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Tentative',
    plannedStartLabel: 'Tentative early June 2026',
    expectedDuration: '72h target window',
    declaredQuestion: 'Under visible scarcity, do agents produce legible aid, refusal, bargaining, and resource-flow behavior?',
    watchFor: 'Watch whether requests, refusals, rescues, and trades form a readable pressure story instead of isolated transaction logs.',
    declaredCondition: 'Aid/trade pressure canary informed by K12-K13 viewer and governance observations',
    changeFromPrior: 'Shifts from governance readability to material survival pressure: who asks, who helps, who refuses, and whether exchange patterns are understandable.',
    usefulEvidence: 'Aid requests tied to resource pressure, trade chains that can be followed, meaningful refusals, and visible consequences for dormancy or recovery.',
    doesNotProve: 'This does not prove stable cooperation norms; it tests whether aid/trade pressure is observable enough to support later controlled research runs.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: '',
    links: {
      live: '/dashboard',
      archive: '/archive',
    },
  },
  {
    id: 'k15-public-order-canary',
    label: 'K15',
    theme: 'Public Order',
    planningState: 'Tentative',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Tentative',
    plannedStartLabel: 'Tentative mid June 2026',
    expectedDuration: '72h target window',
    declaredQuestion: 'Are existing sanctions, invalid actions, accusations, and enforcement signals enough to make public order meaningful?',
    watchFor: 'Watch whether public-order events explain real coordination pressure or whether the current action space is too weak to make conflict legible.',
    declaredCondition: 'Public-order observation canary using existing mechanics; no new hostile actions unless separately declared',
    changeFromPrior: 'Keeps mechanics honest and observes the existing public-order surface before adding theft, sabotage, or other hostile actions.',
    usefulEvidence: 'Sanctions or accusations tied to specific behavior, enforcement that changes agent choices, and recap evidence that distinguishes order from ordinary governance.',
    doesNotProve: 'This does not test new conflict mechanics and should not be treated as evidence for hostile-action design unless a later run declares that condition.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: '',
    links: {
      live: '/dashboard',
      archive: '/archive',
    },
  },
  {
    id: 'season-1-run-1-research-baseline',
    label: 'Season 1 Run 1',
    theme: 'Research Baseline',
    planningState: 'Candidate',
    track: 'Research',
    runClass: 'standard_72h',
    status: 'Candidate',
    plannedStartLabel: 'Candidate after public-canary slate',
    expectedDuration: '72h standard run',
    declaredQuestion: 'Under fixed survival pressure, when do AI agents form durable cooperation, governance, and aid norms?',
    watchFor: 'Watch one-variable-change discipline, stable run metadata, and evidence that can support season-level comparison rather than one-off spectacle.',
    declaredCondition: 'Season 1 baseline candidate; final condition should be locked after K12-K15 canary findings',
    changeFromPrior: 'Transitions from public usability canaries to stricter, claim-bearing research-track discipline only after the viewer pipeline is reliable.',
    usefulEvidence: 'Comparable survival, governance, aid/trade, public-order, and model-attribution evidence that can be replicated across the season.',
    doesNotProve: 'One baseline run alone does not prove the season hypothesis; it starts the comparison set and needs replicates or declared subtests.',
    claimBoundary: 'Research-track candidate; claim-bearing only after protocol conditions and replicate context are satisfied.',
    resultNote: '',
    links: {
      live: '/dashboard',
      archive: '/archive',
    },
  },
  {
    id: 'k11-public-pipeline-canary',
    label: 'K11',
    theme: 'Public Pipeline',
    planningState: 'Completed',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Completed',
    runId: 'real-20260517T220144Z',
    plannedStartLabel: 'Started May 17, 2026',
    expectedDuration: 'Short public pipeline canary',
    declaredQuestion: 'Can the public run pipeline produce visible survival, governance, and post-run evidence?',
    watchFor: 'This was a pipeline canary; the key outcome is whether viewers can understand what happened after the run.',
    declaredCondition: 'real_scarcity_executable_governance_20260517_canary_k11_high_floor_pressure_v1',
    changeFromPrior: 'First public K-series canary with archive and post-run artifacts exposed to viewers.',
    usefulEvidence: 'The run completed and produced survival pressure, dormancy/death, governance, aid/trade, and public-order signals that could be inspected afterward.',
    doesNotProve: 'K11 was not finished research, not a baseline finding, and not evidence that all future runs will behave the same way.',
    claimBoundary: 'Exploratory public canary; not finished research.',
    resultNote: 'Completed, but viewer experience required substantial follow-up fixes.',
    links: {
      recap: '/runs/real-20260517T220144Z/replay?tab=overview',
      evidence: '/runs/real-20260517T220144Z',
      report: '/runs/real-20260517T220144Z/reports/approachable_report?format=markdown',
      archive: '/archive',
    },
  },
]

const STATUS_ORDER = {
  Live: 0,
  Upcoming: 1,
  Tentative: 2,
  Candidate: 3,
  Completed: 4,
}

export function getRunSchedule() {
  return [...RUN_SCHEDULE].sort((a, b) => {
    const statusDelta = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    if (statusDelta !== 0) return statusDelta
    return a.label.localeCompare(b.label, undefined, { numeric: true })
  })
}

export function getNextScheduledRun() {
  return getRunSchedule().find((run) => run.status === 'Live' || run.status === 'Upcoming') || null
}

export function getLatestCompletedScheduledRun() {
  return getRunSchedule().find((run) => run.status === 'Completed') || null
}

export function getScheduleEntryForRunId(runId) {
  const cleanRunId = String(runId || '').trim()
  if (!cleanRunId) return null
  return RUN_SCHEDULE.find((run) => run.runId === cleanRunId) || null
}
