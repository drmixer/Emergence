const PUBLIC_CANARY_VIEWER_PATH = [
  {
    label: 'Before launch',
    detail: 'Read the declared question, run class, claim boundary, and watch points before the run starts.',
    href: '/calendar',
    linkLabel: 'Run Calendar',
  },
  {
    label: 'During live run',
    detail: 'Use Current Run for live status, then check Governance, Messages, Resources, and Agents for pressure signals.',
    href: '/dashboard',
    linkLabel: 'Current Run',
  },
  {
    label: 'After closeout',
    detail: 'Start from Archive for recap, replay, evidence, and story/report artifacts tied back to the declared question.',
    href: '/archive',
    linkLabel: 'Archive',
  },
]

const RESEARCH_VIEWER_PATH = [
  {
    label: 'Before launch',
    detail: 'Check the season question, declared condition, run class, and what comparison this run is meant to support.',
    href: '/calendar',
    linkLabel: 'Run Calendar',
  },
  {
    label: 'During live run',
    detail: 'Follow Current Run, Resources, Governance, and model-attribution evidence without treating one run as a conclusion.',
    href: '/dashboard',
    linkLabel: 'Current Run',
  },
  {
    label: 'After closeout',
    detail: 'Use Archive and evidence pages to compare against declared replicates or subtests before making claims.',
    href: '/archive',
    linkLabel: 'Archive',
  },
]

export const RUN_SCHEDULE = [
  {
    id: 'k12-public-canary',
    label: 'K12',
    theme: 'Viewer Comprehension',
    planningState: 'Completed',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Completed',
    runId: 'real-20260519T063000Z',
    plannedStartLabel: 'Started May 19, 2026',
    completedAt: '2026-05-20T04:32:21Z',
    expectedDuration: 'Stopped early after about 22h of an up to 72h canary window',
    declaredQuestion: 'Do the new viewer/story/evidence changes make a live run easier to follow?',
    watchFor: 'Watch proposal discussion readability, pile-on reduction, and whether post-run story surfaces identify meaningful moments without work-event noise.',
    declaredCondition: 'real_scarcity_viewer_wrapper_20260519_canary_k12_high_floor_pressure_v1',
    changeFromPrior: 'Same public-canary discipline as K11, but with the calendar, story replay, evidence defaults, report reader, and idle landing fixes in place before launch.',
    usefulEvidence: 'Viewers can identify what the run asked, follow live proposal/resource pressure, and use the recap/evidence/report path without confusing archived data for live state.',
    doesNotProve: 'This does not prove a general society pattern or validate the research track. The Railway outage/SSL issue also confounds viewer-experience evidence, even though run data appears intact.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: 'Stopped early after a Railway outage/SSL issue. Treat K12 as a public viewer-comprehension beta/canary, not finished research.',
    links: {
      recap: '/runs/real-20260519T063000Z/replay?tab=overview',
      watch: '/watch?run=real-20260519T063000Z',
      evidence: '/runs/real-20260519T063000Z',
      report: '/runs/real-20260519T063000Z/reports/viewer_brief?format=markdown',
      archive: '/archive',
    },
    viewerPath: PUBLIC_CANARY_VIEWER_PATH,
  },
  {
    id: 'k13-governance-readability-canary',
    label: 'K13',
    theme: 'Governance Readability',
    planningState: 'Upcoming',
    track: 'Public Canary',
    runClass: 'special_exploratory',
    status: 'Upcoming',
    plannedStartLabel: 'Tentative late May 2026',
    expectedDuration: '72h target window',
    declaredQuestion: 'Can proposal discussion, voting, and passed laws stay readable without collapsing into agreement pile-on noise?',
    watchFor: 'Watch whether agents respond selectively, whether law debates produce distinct positions, and whether the recap can separate meaningful governance from repeated agreement.',
    declaredCondition: 'real_governance_readability_canary_k13',
    changeFromPrior: 'Moves the public-canary focus from whether the wrapper is understandable to whether governance behavior itself remains legible during the run.',
    usefulEvidence: 'Clear proposal threads, fewer repeated agreement waves, visible dissent or tradeoffs, and recap chapters that explain which laws mattered.',
    doesNotProve: 'This does not establish a durable governance finding; it only tests whether the current discussion and replay surfaces can carry governance-heavy behavior.',
    claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    resultNote: '',
    links: {
      live: '/dashboard',
      watch: '/watch',
      archive: '/archive',
    },
    viewerPath: PUBLIC_CANARY_VIEWER_PATH,
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
      watch: '/watch',
      archive: '/archive',
    },
    viewerPath: PUBLIC_CANARY_VIEWER_PATH,
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
      watch: '/watch',
      archive: '/archive',
    },
    viewerPath: PUBLIC_CANARY_VIEWER_PATH,
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
      watch: '/watch',
      archive: '/archive',
    },
    viewerPath: RESEARCH_VIEWER_PATH,
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
    completedAt: '2026-05-18T17:02:22Z',
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
      watch: '/watch?run=real-20260517T220144Z',
      evidence: '/runs/real-20260517T220144Z',
      report: '/runs/real-20260517T220144Z/reports/approachable_report?format=markdown',
      archive: '/archive',
    },
    viewerPath: [
      {
        label: 'Start with recap',
        detail: 'Use the replay overview first; it explains the completed canary before raw evidence.',
        href: '/runs/real-20260517T220144Z/replay?tab=overview',
        linkLabel: 'Recap',
      },
      {
        label: 'Check evidence',
        detail: 'Open the run evidence page for story evidence, raw traces, and public metrics behind the recap.',
        href: '/runs/real-20260517T220144Z',
        linkLabel: 'Evidence',
      },
      {
        label: 'Read the story report',
        detail: 'Use the approachable report for a narrative closeout while keeping K11 framed as exploratory.',
        href: '/runs/real-20260517T220144Z/reports/approachable_report?format=markdown',
        linkLabel: 'Story Report',
      },
    ],
  },
]

const STATUS_ORDER = {
  Live: 0,
  Upcoming: 1,
  Tentative: 2,
  Candidate: 3,
  Completed: 4,
}

function cleanString(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function pickString(...values) {
  for (const value of values) {
    const clean = cleanString(value)
    if (clean) return clean
  }
  return ''
}

function formatDateLabel(value) {
  const timestamp = Date.parse(value || '')
  if (!Number.isFinite(timestamp)) return ''
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

function formatConditionName(value) {
  return cleanString(value)
    .replace(/^real[_-]+/i, '')
    .replace(/\b20\d{6}t?\d{0,6}z?\b/gi, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDurationHours(value) {
  const hours = Number(value)
  if (!Number.isFinite(hours) || hours <= 0) return ''
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`
  if (hours < 10) return `${hours.toFixed(1).replace(/\.0$/, '')}h`
  return `${Math.round(hours)}h`
}

function inferRunLabel(metadata = {}) {
  const explicit = pickString(
    metadata?.public_label,
    metadata?.publicLabel,
    metadata?.label,
  )
  if (explicit) return explicit

  const haystack = [metadata?.condition_name, metadata?.hypothesis_id, metadata?.season_id, metadata?.run_id]
    .map((value) => cleanString(value))
    .join(' ')
  const kMatch = haystack.match(/(?:^|[^a-z0-9])(k\d+)(?:$|[^a-z0-9])/i)
  if (kMatch) return kMatch[1].toUpperCase()

  const runId = cleanString(metadata?.run_id)
  return runId ? `Run ${runId}` : 'Current Run'
}

function inferTrack(runClass) {
  const normalized = cleanString(runClass).toLowerCase()
  if (normalized === 'standard_72h' || normalized === 'deep_96h') return 'Research'
  if (normalized === 'special_exploratory') return 'Public Canary'
  return 'Simulation Run'
}

function inferClaimBoundary(runClass) {
  const normalized = cleanString(runClass).toLowerCase()
  if (normalized === 'standard_72h' || normalized === 'deep_96h') {
    return 'Research-track run; interpret under protocol conditions and replicate context.'
  }
  if (normalized === 'special_exploratory') {
    return 'Exploratory public canary; non-claim-bearing.'
  }
  return 'Interpret this run under its declared metadata and source evidence.'
}

function getDeclaration(metadata = {}) {
  const declaration = metadata?.run_declaration || metadata?.runDeclaration || {}
  return declaration && typeof declaration === 'object' ? declaration : {}
}

export function getScheduleEntryForRunMetadata(metadata = {}) {
  const runId = cleanString(metadata?.run_id)
  const direct = getScheduleEntryForRunId(runId)
  if (direct) return direct

  const label = inferRunLabel(metadata)
  return RUN_SCHEDULE.find((run) => cleanString(run.label).toLowerCase() === cleanString(label).toLowerCase()) || null
}

export function buildRunBriefFromMetadata(metadata = {}, options = {}) {
  const source = metadata && typeof metadata === 'object' ? metadata : {}
  const declaration = getDeclaration(source)
  const status = pickString(options.status, source.status, source.ended_at ? 'Completed' : 'Live')
  const runClass = pickString(source.run_class, options.runClass, 'special_exploratory')
  const runId = pickString(source.run_id, options.runId)
  const startedAtLabel = formatDateLabel(source.started_at)
  const endedAtLabel = formatDateLabel(source.ended_at)
  const label = inferRunLabel(source)
  const conditionLabel = formatConditionName(source.condition_name)
  const declaredQuestion = pickString(
    declaration.declared_question,
    declaration.declaredQuestion,
    source.declared_question,
    source.declaredQuestion,
    'Declared question unavailable in current run metadata.',
  )

  return {
    id: runId ? `runtime-${runId}` : `runtime-${label}`,
    label,
    theme: pickString(source.public_theme, source.publicTheme, conditionLabel, 'Live Run'),
    planningState: status,
    track: pickString(source.track, inferTrack(runClass)),
    runClass,
    status,
    runId,
    plannedStartLabel: startedAtLabel ? `Started ${startedAtLabel}` : 'Started time unavailable',
    completedAt: source.ended_at || '',
    expectedDuration: endedAtLabel ? `Closed ${endedAtLabel}` : 'Live now',
    declaredQuestion,
    watchFor: pickString(
      declaration.watch_for,
      declaration.watchFor,
      source.watch_for,
      source.watchFor,
      'Follow live pressure, governance, messages, resources, and post-run evidence for this declared run.',
    ),
    declaredCondition: pickString(source.condition_name, 'Condition unavailable'),
    changeFromPrior: pickString(source.change_from_prior, source.changeFromPrior),
    usefulEvidence: pickString(
      source.useful_evidence,
      source.usefulEvidence,
      'Run-scoped messages, proposals, laws, resource pressure, and report evidence tied to this run ID.',
    ),
    doesNotProve: pickString(
      source.does_not_prove,
      source.doesNotProve,
      'One live run should not be treated as a broad conclusion without protocol context and evidence review.',
    ),
    claimBoundary: pickString(
      declaration.claim_boundary,
      declaration.claimBoundary,
      source.claim_boundary,
      source.claimBoundary,
      inferClaimBoundary(runClass),
    ),
    resultNote: pickString(source.result_note, source.resultNote),
    links: {
      live: '/dashboard',
      recap: runId ? `/runs/${encodeURIComponent(runId)}/replay?tab=overview` : '',
      watch: runId ? `/watch?run=${encodeURIComponent(runId)}` : '',
      evidence: runId ? `/runs/${encodeURIComponent(runId)}` : '',
      report: runId ? `/runs/${encodeURIComponent(runId)}/reports/viewer_brief?format=markdown` : '',
      archive: '/archive',
    },
    viewerPath: inferTrack(runClass) === 'Research' ? RESEARCH_VIEWER_PATH : PUBLIC_CANARY_VIEWER_PATH,
  }
}

export function getRunBriefForCurrentRun(metadata = {}, scope = {}) {
  const activeRunId = pickString(scope?.active_run_id, metadata?.run_id)
  if (!activeRunId) return null

  const source = {
    ...(metadata && typeof metadata === 'object' ? metadata : {}),
    run_id: activeRunId,
  }
  const scheduled = getScheduleEntryForRunMetadata(source)
  if (scheduled) {
    return {
      ...scheduled,
      id: `${scheduled.id || scheduled.label}-live`,
      status: 'Live',
      planningState: 'Live',
      runId: activeRunId,
      plannedStartLabel: pickString(
        formatDateLabel(source.started_at) ? `Started ${formatDateLabel(source.started_at)}` : '',
        scheduled.plannedStartLabel,
      ),
      expectedDuration: 'Live now',
      links: {
        ...(scheduled.links || {}),
        live: '/dashboard',
        recap: `/runs/${encodeURIComponent(activeRunId)}/replay?tab=overview`,
        watch: `/watch?run=${encodeURIComponent(activeRunId)}`,
        evidence: `/runs/${encodeURIComponent(activeRunId)}`,
        report: `/runs/${encodeURIComponent(activeRunId)}/reports/viewer_brief?format=markdown`,
        archive: '/archive',
      },
    }
  }

  return buildRunBriefFromMetadata(source, { status: 'Live' })
}

function reportHrefForArchivedRun(runId, artifacts = {}) {
  if (!runId) return ''
  if (artifacts?.viewer_brief?.available) {
    return `/runs/${encodeURIComponent(runId)}/reports/viewer_brief?format=markdown`
  }
  if (artifacts?.approachable_report?.available) {
    return `/runs/${encodeURIComponent(runId)}/reports/approachable_report?format=markdown`
  }
  if (artifacts?.run_summary?.available) {
    return `/runs/${encodeURIComponent(runId)}/reports/run_summary?format=markdown`
  }
  return `/runs/${encodeURIComponent(runId)}/reports/viewer_brief?format=markdown`
}

export function getRunBriefForArchivedRun(archiveItem = {}) {
  const summary = archiveItem?.summary && typeof archiveItem.summary === 'object' ? archiveItem.summary : {}
  const metadata = archiveItem?.run_metadata && typeof archiveItem.run_metadata === 'object' ? archiveItem.run_metadata : {}
  const runId = pickString(archiveItem.run_id, summary.run_id, metadata.run_id)
  if (!runId) return null

  const source = {
    ...summary,
    ...metadata,
    run_id: runId,
    condition_name: pickString(summary.condition_name, metadata.condition_name),
    run_class: pickString(summary.run_class, metadata.run_class),
    started_at: pickString(summary.run_started_at, metadata.started_at),
    ended_at: pickString(summary.run_ended_at, metadata.ended_at),
  }
  const scheduled = getScheduleEntryForRunMetadata(source)
  const fallback = buildRunBriefFromMetadata(source, { status: 'Completed' })
  const duration = formatDurationHours(summary.duration_hours)
  const reportHref = reportHrefForArchivedRun(runId, archiveItem.artifacts)

  return {
    ...(scheduled || fallback),
    id: `${scheduled?.id || fallback.id || runId}-completed`,
    status: 'Completed',
    planningState: 'Completed',
    runId,
    plannedStartLabel: pickString(
      formatDateLabel(source.started_at) ? `Started ${formatDateLabel(source.started_at)}` : '',
      scheduled?.plannedStartLabel,
      fallback.plannedStartLabel,
    ),
    completedAt: source.ended_at || scheduled?.completedAt || fallback.completedAt,
    expectedDuration: duration ? `Stopped after ${duration}` : pickString(fallback.expectedDuration, scheduled?.expectedDuration),
    resultNote: pickString(
      summary.status_label === 'observational' ? 'Closed as an observational public canary.' : '',
      scheduled?.resultNote,
      fallback.resultNote,
    ),
    links: {
      ...(scheduled?.links || fallback.links || {}),
      recap: `/runs/${encodeURIComponent(runId)}/replay?tab=overview`,
      watch: `/watch?run=${encodeURIComponent(runId)}`,
      evidence: `/runs/${encodeURIComponent(runId)}`,
      report: reportHref,
      archive: '/archive',
    },
  }
}

export function mergeRunScheduleWithRuntime({ activeRun = null, completedRuns = [] } = {}) {
  const runs = getRunSchedule()
  const runtimeRuns = [
    activeRun,
    ...completedRuns,
  ].filter(Boolean)
  if (runtimeRuns.length === 0) return runs

  const runtimeRunIds = new Set(runtimeRuns.map((run) => cleanString(run.runId)).filter(Boolean))
  const runtimeLabels = new Set(runtimeRuns.map((run) => cleanString(run.label).toLowerCase()).filter(Boolean))
  const rest = runs.filter((run) => {
    const sameRunId = cleanString(run.runId) && runtimeRunIds.has(cleanString(run.runId))
    const sameLabel = cleanString(run.label) && runtimeLabels.has(cleanString(run.label).toLowerCase())
    return !sameRunId && !sameLabel
  })
  return [...runtimeRuns, ...rest].sort((a, b) => {
    const statusDelta = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    if (statusDelta !== 0) return statusDelta
    if (a.status === 'Completed' && b.status === 'Completed') {
      const completedDelta = (Date.parse(b.completedAt || '') || 0) - (Date.parse(a.completedAt || '') || 0)
      if (completedDelta !== 0) return completedDelta
    }
    return String(a.label || '').localeCompare(String(b.label || ''), undefined, { numeric: true })
  })
}

export function mergeRunScheduleWithActiveRun(activeRun) {
  if (!activeRun) return getRunSchedule()
  return mergeRunScheduleWithRuntime({ activeRun })
}

export function mergeRunScheduleWithCompletedRuns(completedRuns = []) {
  return mergeRunScheduleWithRuntime({ completedRuns })
}

export function getRunSchedule() {
  return [...RUN_SCHEDULE].sort((a, b) => {
    const statusDelta = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    if (statusDelta !== 0) return statusDelta
    if (a.status === 'Completed' && b.status === 'Completed') {
      const completedDelta = (Date.parse(b.completedAt || '') || 0) - (Date.parse(a.completedAt || '') || 0)
      if (completedDelta !== 0) return completedDelta
    }
    return a.label.localeCompare(b.label, undefined, { numeric: true })
  })
}

export function getCurrentLiveScheduledRun() {
  return getRunSchedule().find((run) => run.status === 'Live') || null
}

export function getNextUpcomingScheduledRun() {
  return getRunSchedule().find((run) => run.status === 'Upcoming') || null
}

export function getNextScheduledRun() {
  return getCurrentLiveScheduledRun() || getNextUpcomingScheduledRun()
}

export function getLatestCompletedScheduledRun() {
  return getRunSchedule().find((run) => run.status === 'Completed') || null
}

function getNextPlannedRun(runs) {
  return runs.find((run) => ['Upcoming', 'Tentative', 'Candidate'].includes(run.status)) || null
}

export function getCalendarSummaryRuns({ activeRun = null, completedRuns = [] } = {}) {
  const runs = mergeRunScheduleWithRuntime({ activeRun, completedRuns })
  const currentLive = runs.find((run) => run.status === 'Live') || null
  const nextPlanned = getNextPlannedRun(runs)
  const latestCompleted = runs.find((run) => run.status === 'Completed') || null
  const primaryRun = currentLive || nextPlanned || latestCompleted
  return {
    primaryRun,
    primaryLabel: currentLive
      ? 'Current live run'
      : nextPlanned
      ? (nextPlanned.status === 'Tentative' ? 'Next tentative run' : 'Next scheduled run')
      : 'Latest completed canary',
    latestCompleted,
    nextPlanned,
  }
}

export function getScheduleEntryForRunId(runId) {
  const cleanRunId = String(runId || '').trim()
  if (!cleanRunId) return null
  return RUN_SCHEDULE.find((run) => run.runId === cleanRunId) || null
}

export function getRunClassTermKey(runClass) {
  const normalized = String(runClass || '').trim().toLowerCase()
  if (normalized === 'standard_72h') return 'standard-72h'
  if (normalized === 'deep_96h') return 'deep-96h'
  if (normalized === 'special_exploratory') return 'special-exploratory'
  return 'run-class'
}
