import { createElement, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  Activity,
  BarChart3,
  CircleCheck,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  Hash,
  ListTree,
  ShieldCheck,
  TimerReset,
} from 'lucide-react'
import { api } from '../services/api'
import { trackKpiEvent, trackKpiEventOnce } from '../services/kpiAnalytics'
import {
  buildEvidenceGroups,
  buildEvidenceCategoryFilters,
  EVIDENCE_CATEGORY_META,
  filterEvidenceByCategory,
} from '../utils/evidenceCategories'

const VALID_TABS = new Set(['overview', 'replay', 'evidence', 'reports'])
const ROUTINE_REPLAY_EVENT_TYPES = new Set(['work', 'idle', 'vote', 'processing_error'])
const SIGNAL_REPLAY_EVENT_TYPES = new Set([
  'agent_died',
  'became_dormant',
  'agent_revived',
  'awakened',
  'law_passed',
  'proposal_resolved',
  'create_proposal',
  'world_event',
  'trade',
  'request_aid',
  'refuse_aid',
  'public_accusation',
  'contest_proposal',
  'initiate_sanction',
  'initiate_seizure',
  'initiate_exile',
  'vote_enforcement',
  'enforcement_initiated',
  'agent_sanctioned',
  'resources_seized',
  'agent_exiled',
])
const STRONG_REPLAY_CATEGORIES = new Set(['crisis', 'conflict', 'governance'])
const SOCIAL_REPLAY_CATEGORIES = new Set(['cooperation', 'alliance'])
const REPLAY_CHAPTER_ORDER = ['survival', 'governance', 'aid_trade', 'public_order', 'system', 'other']

const REPLAY_CHAPTER_META = {
  survival: {
    label: 'Survival Pressure',
    shortLabel: 'Survival',
    description: 'Agents left active play through dormancy, death, or revival.',
  },
  governance: {
    label: 'Governance Decisions',
    shortLabel: 'Governance',
    description: 'Proposals, votes, and laws changed what the agents were trying to coordinate around.',
  },
  aid_trade: {
    label: 'Aid & Trade',
    shortLabel: 'Aid / Trade',
    description: 'Resource requests, refusals, and trades show where cooperation held or broke.',
  },
  public_order: {
    label: 'Public Order & Conflict',
    shortLabel: 'Public Order',
    description: 'Accusations, refusals, sanctions, seizures, exile, and contests mark disorder or enforcement pressure.',
  },
  system: {
    label: 'System Shocks',
    shortLabel: 'Shocks',
    description: 'World events or run-wide shocks changed the constraints around the agents.',
  },
  other: {
    label: 'Other Signals',
    shortLabel: 'Other',
    description: 'Notable events that did not fit the major viewer-facing threads.',
  },
}

const NARRATIVE_BEAT_RULES = [
  {
    key: 'opening',
    label: 'Opening Signal',
    match: () => true,
    fallback: 'The first non-routine moment selected for the replay.',
  },
  {
    key: 'governance',
    label: 'Governance Response',
    match: (item) => getChapterKey(item) === 'governance',
    fallback: 'The clearest proposal, vote, or law signal in the curated run story.',
  },
  {
    key: 'pressure',
    label: 'Pressure Point',
    match: (item) => ['survival', 'aid_trade', 'public_order', 'system'].includes(getChapterKey(item)),
    fallback: 'The moment where survival pressure, resource coordination, or disorder became visible.',
  },
  {
    key: 'outcome',
    label: 'Late Outcome',
    match: (_item, index, items) => index === items.length - 1,
    fallback: 'The last curated signal in the replay window.',
  },
]

const REPORT_LABELS = {
  viewer_brief: 'Emergence Brief',
  approachable_report: 'Approachable Story',
  technical_report: 'Technical Report',
  planner_report: 'Next-Run Plan',
  run_summary: 'Run Summary',
}

const REPORT_ORDER = ['viewer_brief', 'approachable_report', 'technical_report', 'planner_report', 'run_summary']

const EVIDENCE_DEFAULT_LIMIT = 80

function formatNumber(value) {
  return Number(value || 0).toLocaleString()
}

function formatUsd(value) {
  return Number(value || 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  })
}

function formatTimestamp(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

function formatRelative(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return formatDistanceToNow(date, { addSuffix: true })
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function getEventId(item) {
  return Number(item?.event_id || item?.id || 0)
}

function getEventTitle(item) {
  return String(item?.title || item?.event_type || 'Run event').replace(/_/g, ' ')
}

function getEventDescription(item) {
  return String(item?.description || item?.summary || '').trim()
}

function getEventTime(item) {
  return item?.created_at || item?.timestamp || ''
}

function clampText(value, maxLength = 220) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text || text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 1).trim()}...`
}

function chooseNarrativeBeat(items, rule, usedEventIds) {
  if (!Array.isArray(items) || items.length === 0) return null
  const orderedItems = rule.key === 'outcome' ? [...items].reverse() : items
  const found = orderedItems.find((item) => {
    const eventId = getEventId(item)
    const index = items.findIndex((candidate) => getEventId(candidate) === eventId)
    return eventId > 0 && !usedEventIds.has(eventId) && rule.match(item, index, items)
  })
  return found || null
}

function buildNarrativeBeats(storyItems) {
  if (!Array.isArray(storyItems) || storyItems.length === 0) return []
  const usedEventIds = new Set()
  const beats = []

  NARRATIVE_BEAT_RULES.forEach((rule) => {
    const item = chooseNarrativeBeat(storyItems, rule, usedEventIds)
    if (!item) return
    const eventId = getEventId(item)
    usedEventIds.add(eventId)
    beats.push({
      key: `${rule.key}-${eventId}`,
      label: rule.label,
      title: getEventTitle(item),
      detail: clampText(item?.why_this_matters || getEventDescription(item) || rule.fallback, 190),
      eventId,
    })
  })

  return beats
}

function isReplayMomentCandidate(item) {
  const eventType = String(item?.event_type || '').trim()
  const category = String(item?.category || '').trim()
  const salience = Number(item?.salience || 0)

  if (getEventId(item) <= 0) return false
  if (ROUTINE_REPLAY_EVENT_TYPES.has(eventType)) return false
  if (SIGNAL_REPLAY_EVENT_TYPES.has(eventType)) return true
  if (STRONG_REPLAY_CATEGORIES.has(category)) return true
  if (SOCIAL_REPLAY_CATEGORIES.has(category)) return salience >= 70
  return salience >= 75
}

function isEvidenceTraceCandidate(item) {
  if (!item || getEventId(item) <= 0) return false
  const eventType = String(item?.event_type || '').trim()
  const category = String(item?.category || '').trim()
  const title = getEventTitle(item).toLowerCase()

  if (ROUTINE_REPLAY_EVENT_TYPES.has(eventType)) return false
  if (title === 'work' || title === 'idle') return false
  if (SIGNAL_REPLAY_EVENT_TYPES.has(eventType)) return true
  if (STRONG_REPLAY_CATEGORIES.has(category) || SOCIAL_REPLAY_CATEGORIES.has(category)) return true
  return Number(item?.salience || 0) >= 70
}

function getStoryItems(story, playbackItems) {
  const storyItems = Array.isArray(story?.items) ? story.items : []
  if (storyItems.length > 0) return storyItems.filter((item) => isReplayMomentCandidate(item))
  return (Array.isArray(playbackItems) ? playbackItems : [])
    .filter((item) => getEventDescription(item) && isReplayMomentCandidate(item))
    .slice(0, 8)
    .map((item, index) => ({
      ...item,
      chapter: index === 0 ? 'Trigger' : index < 3 ? 'Escalation' : index < 6 ? 'Turning Point' : 'Outcome',
      why_this_matters: item?.why_this_matters || getEventDescription(item),
    }))
}

function getChapterKey(item) {
  const eventType = String(item?.event_type || '').trim()
  const category = String(item?.category || '').trim()

  if (['agent_died', 'became_dormant', 'agent_revived', 'awakened'].includes(eventType)) return 'survival'
  if (['law_passed', 'proposal_resolved', 'create_proposal', 'vote_enforcement'].includes(eventType) || category === 'governance') return 'governance'
  if (['trade', 'request_aid', 'refuse_aid'].includes(eventType) || category === 'cooperation' || category === 'alliance') return 'aid_trade'
  if (
    category === 'conflict'
    || [
      'public_accusation',
      'contest_proposal',
      'initiate_sanction',
      'initiate_seizure',
      'initiate_exile',
      'enforcement_initiated',
      'agent_sanctioned',
      'resources_seized',
      'agent_exiled',
    ].includes(eventType)
  ) {
    return 'public_order'
  }
  if (category === 'crisis' || eventType === 'world_event') return 'system'
  return 'other'
}

function buildReplayChapters(storyItems) {
  const buckets = new Map()
  storyItems.forEach((item) => {
    const key = getChapterKey(item)
    const meta = REPLAY_CHAPTER_META[key] || REPLAY_CHAPTER_META.other
    const bucket = buckets.get(key) || {
      key,
      ...meta,
      items: [],
      lead_event_id: 0,
    }
    bucket.items.push(item)
    bucket.lead_event_id = bucket.lead_event_id || getEventId(item)
    buckets.set(key, bucket)
  })

  return REPLAY_CHAPTER_ORDER
    .map((key) => buckets.get(key))
    .filter(Boolean)
    .map((chapter) => {
      const lead = chapter.items[0]
      const count = chapter.items.length
      return {
        ...chapter,
        count,
        summary: count > 1
          ? `${count} notable ${chapter.shortLabel.toLowerCase()} moments, led by ${lead ? getEventTitle(lead).toLowerCase() : 'a source event'}. ${chapter.description}`
          : `${chapter.description} ${lead ? clampText(getEventDescription(lead), 160) : ''}`.trim(),
      }
    })
}

function getChapterForEvent(chapters, eventId) {
  if (!eventId) return null
  return chapters.find((chapter) => chapter.items.some((item) => getEventId(item) === eventId)) || null
}

function getTradeAmountSummary(activity) {
  const amounts = activity?.trade_amounts || {}
  const rows = ['food', 'energy', 'materials']
    .map((resource) => [resource, Number(amounts?.[resource] || 0)])
    .filter(([, value]) => value > 0)
  if (rows.length === 0) return ''
  return rows.map(([resource, value]) => `${Number(value.toFixed(2)).toLocaleString()} ${resource}`).join(' / ')
}

function buildRunBrief(runDetail, storyItems) {
  const activity = runDetail?.activity || {}
  const totalEvents = Number(activity.total_events || 0)
  const deaths = Number(activity.deaths || 0)
  const dormant = Number(activity.became_dormant || 0)
  const revivals = Number(activity.agent_revived || 0)
  const laws = Number(activity.laws_passed || 0)
  const proposals = Number(activity.proposal_actions || 0)
  const aidRequests = Number(activity.aid_requests || 0)
  const aidRefusals = Number(activity.aid_refusals || 0)
  const trades = Number(activity.trade_actions || 0)
  const publicOrder = Number(activity.public_order_events || 0)
  const conflicts = Number(activity.conflict_events || 0)
  const firstMoment = storyItems[0]
  const lastMoment = storyItems[storyItems.length - 1]
  const sentences = []

  if (totalEvents > 0) {
    sentences.push(`This completed run produced ${totalEvents.toLocaleString()} scoped events.`)
  }

  const survivalBits = []
  if (deaths > 0) survivalBits.push(`${deaths.toLocaleString()} death${deaths === 1 ? '' : 's'}`)
  if (dormant > 0) survivalBits.push(`${dormant.toLocaleString()} dormancy event${dormant === 1 ? '' : 's'}`)
  if (revivals > 0) survivalBits.push(`${revivals.toLocaleString()} revival${revivals === 1 ? '' : 's'}`)
  if (survivalBits.length > 0) sentences.push(`Survival pressure showed up as ${survivalBits.join(', ')}.`)

  if (laws > 0 || proposals > 0) {
    sentences.push(`Governance stayed active with ${proposals.toLocaleString()} proposal action${proposals === 1 ? '' : 's'} and ${laws.toLocaleString()} law${laws === 1 ? '' : 's'} passed.`)
  }

  if (aidRequests > 0 || aidRefusals > 0 || trades > 0) {
    const tradeSummary = getTradeAmountSummary(activity)
    sentences.push(`Resource coordination included ${aidRequests.toLocaleString()} aid request${aidRequests === 1 ? '' : 's'}, ${aidRefusals.toLocaleString()} aid refusal${aidRefusals === 1 ? '' : 's'}, and ${trades.toLocaleString()} trade${trades === 1 ? '' : 's'}${tradeSummary ? ` (${tradeSummary})` : ''}.`)
  }

  if (publicOrder > 0 || conflicts > 0) {
    sentences.push(`Public order was not just a label: the run logged ${publicOrder.toLocaleString()} public-order signal${publicOrder === 1 ? '' : 's'} and ${conflicts.toLocaleString()} conflict signal${conflicts === 1 ? '' : 's'}.`)
  }

  if (firstMoment && lastMoment && getEventId(firstMoment) !== getEventId(lastMoment)) {
    sentences.push(`The curated replay starts with ${getEventTitle(firstMoment).toLowerCase()} and ends around ${getEventTitle(lastMoment).toLowerCase()}.`)
  }

  if (sentences.length === 0) {
    return 'Replay data exists, but the run does not yet have enough non-routine story signals for a useful recap.'
  }
  return sentences.slice(0, 5).join(' ')
}

function buildRecapRows(runDetail, storyItems) {
  const activity = runDetail?.activity || {}
  const storyCounts = storyItems.reduce((counts, item) => {
    const key = getChapterKey(item)
    counts[key] = Number(counts[key] || 0) + 1
    return counts
  }, {})
  return [
    {
      label: 'Survival',
      value: `${formatNumber(activity.deaths)} deaths / ${formatNumber(activity.became_dormant)} dormant`,
      detail: `${formatNumber(activity.agent_revived)} revivals recorded.`,
      tone: Number(activity.deaths || 0) > 0 || Number(activity.became_dormant || 0) > 0 ? 'alert' : 'neutral',
    },
    {
      label: 'Governance',
      value: `${formatNumber(activity.laws_passed)} laws passed`,
      detail: `${formatNumber(activity.proposal_actions)} proposal actions and ${formatNumber(activity.vote_actions)} votes.`,
      tone: Number(storyCounts.governance || 0) > 0 ? 'up' : 'neutral',
    },
    {
      label: 'Aid / Trade',
      value: `${formatNumber(activity.aid_requests)} aid requests`,
      detail: `${formatNumber(activity.aid_refusals)} refusals and ${formatNumber(activity.trade_actions)} trades.`,
      tone: Number(activity.aid_refusals || 0) > 0 ? 'alert' : 'neutral',
    },
    {
      label: 'Public Order',
      value: `${formatNumber(activity.public_order_events)} signals`,
      detail: `${formatNumber(activity.conflict_events)} conflict signals in the run window.`,
      tone: Number(activity.conflict_events || 0) > 0 ? 'alert' : 'neutral',
    },
  ]
}

function getReportRows(reports) {
  const rows = Array.isArray(reports?.items) ? reports.items : []
  const byType = new Map()
  rows.forEach((row) => {
    const type = String(row?.artifact_type || '').trim()
    const format = String(row?.artifact_format || '').trim()
    if (!type || !format) return
    const existing = byType.get(type) || { type, formats: [], updated_at: null }
    if (!existing.formats.includes(format)) existing.formats.push(format)
    existing.updated_at = existing.updated_at || row.updated_at || row.created_at || null
    byType.set(type, existing)
  })
  return Array.from(byType.values()).sort((a, b) => {
    const aRank = REPORT_ORDER.indexOf(a.type)
    const bRank = REPORT_ORDER.indexOf(b.type)
    if (aRank !== bRank) {
      if (aRank === -1) return 1
      if (bRank === -1) return -1
      return aRank - bRank
    }
    const aLabel = REPORT_LABELS[a.type] || a.type
    const bLabel = REPORT_LABELS[b.type] || b.type
    return aLabel.localeCompare(bLabel)
  })
}

function getOutcomeRows(runDetail, storyItems, sourceTraces, playbackItems) {
  const activity = runDetail?.activity || {}
  const llm = runDetail?.llm || {}
  const provenance = runDetail?.provenance || {}
  const totalEvents = Number(activity.total_events || 0)
  const deaths = Number(activity.deaths || 0)
  const proposalActions = Number(activity.proposal_actions || 0)
  const voteActions = Number(activity.vote_actions || 0)
  const lawsPassed = Number(activity.laws_passed || 0)
  const deterministicIdle = Number(activity.deterministic_forced_idle_actions || 0)
  const routineFallback = Number(activity.deterministic_routine_fallback_actions || 0)
  const verification = formatLabel(provenance.verification_state || 'unverified')

  return [
    {
      label: 'Survival',
      value: `${deaths.toLocaleString()} deaths`,
      detail: `${totalEvents.toLocaleString()} captured events in the run window.`,
    },
    {
      label: 'Governance',
      value: `${lawsPassed.toLocaleString()} laws`,
      detail: `${proposalActions.toLocaleString()} proposal actions and ${voteActions.toLocaleString()} vote actions recorded.`,
    },
    {
      label: 'Replay',
      value: `${storyItems.length.toLocaleString()} moments`,
      detail: `${playbackItems.length.toLocaleString()} playback events available for reconstruction.`,
    },
    {
      label: 'Evidence',
      value: verification,
      detail: `${sourceTraces.length.toLocaleString()} source traces, ${Number(llm.calls || 0).toLocaleString()} model calls, ${deterministicIdle.toLocaleString()} forced idles, ${routineFallback.toLocaleString()} routine fallbacks.`,
    },
  ]
}

function preferredReportFormat(row) {
  if (row?.formats?.includes('markdown')) return 'markdown'
  if (row?.formats?.includes('json')) return 'json'
  return ''
}

function getInitialTab(requestedTab, requestedMode) {
  if (VALID_TABS.has(requestedTab)) return requestedTab
  if (requestedMode === 'timeline') return 'evidence'
  return 'replay'
}

export default function RunReplay() {
  const { runId } = useParams()
  const [searchParams] = useSearchParams()
  const requestedTab = String(searchParams.get('tab') || '').trim()
  const requestedMode = String(searchParams.get('mode') || '').trim()
  const requestedEventId = Number(searchParams.get('event') || 0)
  const [activeTab, setActiveTab] = useState(() => getInitialTab(requestedTab, requestedMode))
  const [runDetail, setRunDetail] = useState(null)
  const [playback, setPlayback] = useState(null)
  const [story, setStory] = useState({ items: [], chapters: [] })
  const [reports, setReports] = useState(null)
  const [selectedEventId, setSelectedEventId] = useState(() => requestedEventId > 0 ? requestedEventId : 0)
  const [showRawEvidence, setShowRawEvidence] = useState(false)
  const [activeEvidenceCategory, setActiveEvidenceCategory] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      setRunDetail(null)
      setPlayback(null)
      setStory({ items: [], chapters: [] })
      setReports(null)

      const [detailResult, playbackResult, storyResult, reportsResult] = await Promise.allSettled([
        api.getRunDetail(runId, 96, 24, 45),
        api.getRunPlayback(runId, 100, 300),
        api.getReplayStory(96, 45, 10, runId),
        api.getRunReports(runId),
      ])
      if (cancelled) return

      const detail = detailResult.status === 'fulfilled' ? detailResult.value : null
      const playbackPayload = playbackResult.status === 'fulfilled' ? playbackResult.value : null
      const storyPayload = storyResult.status === 'fulfilled' ? storyResult.value : null
      const reportsPayload = reportsResult.status === 'fulfilled' ? reportsResult.value : null

      setRunDetail(detail && typeof detail === 'object' ? detail : null)
      setPlayback(playbackPayload && typeof playbackPayload === 'object' ? playbackPayload : null)
      setStory(storyPayload && typeof storyPayload === 'object' ? storyPayload : { items: [], chapters: [] })
      setReports(reportsPayload && typeof reportsPayload === 'object' ? reportsPayload : null)

      if (!detail && !playbackPayload && !storyPayload && !reportsPayload) {
        setError('Run replay could not be loaded.')
      }
      setLoading(false)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [runId])

  const playbackItems = useMemo(() => Array.isArray(playback?.items) ? playback.items : [], [playback])
  const storyItems = useMemo(() => getStoryItems(story, playbackItems), [story, playbackItems])
  const replayChapters = useMemo(() => buildReplayChapters(storyItems), [storyItems])
  const sourceTraces = useMemo(() => Array.isArray(runDetail?.source_traces) ? runDetail.source_traces : [], [runDetail])
  const reportRows = useMemo(() => getReportRows(reports), [reports])
  const outcomeRows = useMemo(
    () => getOutcomeRows(runDetail, storyItems, sourceTraces, playbackItems),
    [runDetail, storyItems, sourceTraces, playbackItems],
  )

  const activeStoryItem = useMemo(() => {
    if (storyItems.length === 0) return null
    if (selectedEventId > 0) {
      const selected = storyItems.find((item) => getEventId(item) === selectedEventId)
      if (selected) return selected
    }
    return storyItems[0]
  }, [selectedEventId, storyItems])
  const activeChapter = useMemo(() => {
    if (replayChapters.length === 0) return null
    return getChapterForEvent(replayChapters, getEventId(activeStoryItem)) || replayChapters[0]
  }, [activeStoryItem, replayChapters])
  const runBrief = useMemo(() => buildRunBrief(runDetail, storyItems), [runDetail, storyItems])
  const recapRows = useMemo(() => buildRecapRows(runDetail, storyItems), [runDetail, storyItems])
  const narrativeBeats = useMemo(() => buildNarrativeBeats(storyItems), [storyItems])
  const evidenceItems = useMemo(() => {
    const rawItems = sourceTraces.length > 0 ? sourceTraces : playbackItems
    if (showRawEvidence) return rawItems.slice(0, 300)
    const filteredSource = sourceTraces.filter(isEvidenceTraceCandidate)
    if (filteredSource.length > 0) return filteredSource.slice(0, EVIDENCE_DEFAULT_LIMIT)
    if (storyItems.length > 0) return storyItems.slice(0, EVIDENCE_DEFAULT_LIMIT)
    return playbackItems.filter(isEvidenceTraceCandidate).slice(0, EVIDENCE_DEFAULT_LIMIT)
  }, [playbackItems, showRawEvidence, sourceTraces, storyItems])
  const evidenceCategoryFilters = useMemo(() => buildEvidenceCategoryFilters(evidenceItems), [evidenceItems])
  const selectedEvidenceCategory = evidenceCategoryFilters.some((filter) => filter.key === activeEvidenceCategory)
    ? activeEvidenceCategory
    : 'all'
  const filteredEvidenceItems = useMemo(
    () => filterEvidenceByCategory(evidenceItems, selectedEvidenceCategory),
    [evidenceItems, selectedEvidenceCategory],
  )
  const groupedEvidenceItems = useMemo(() => buildEvidenceGroups(filteredEvidenceItems), [filteredEvidenceItems])
  const selectedEvidenceCategoryMeta = EVIDENCE_CATEGORY_META[selectedEvidenceCategory] || EVIDENCE_CATEGORY_META.all
  const rawEvidenceCount = sourceTraces.length || playbackItems.length
  const hiddenRoutineEvidenceCount = Math.max(0, rawEvidenceCount - evidenceItems.length)

  function getReportUrl(row, action) {
    const format = preferredReportFormat(row)
    if (!format || !row?.type) return ''
    return action === 'download'
      ? api.getRunReportDownloadUrl(runId, row.type, format)
      : api.getRunReportViewUrl(runId, row.type, format)
  }

  function getReportViewPath(row) {
    const format = preferredReportFormat(row)
    if (!format || !row?.type) return ''
    return `/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(row.type)}?format=${encodeURIComponent(format)}`
  }

  const provenance = runDetail?.provenance || {}
  const runMetadata = runDetail?.run_metadata || {}
  const activity = runDetail?.activity || {}
  const llm = runDetail?.llm || {}
  const cleanRunId = String(runId || '').trim()

  useEffect(() => {
    if (!cleanRunId || loading || error) return
    trackKpiEventOnce('run_replay_tab_open', `run_replay_tab:${cleanRunId}:${activeTab}`, {
      runId: cleanRunId,
      surface: 'run_replay',
      target: activeTab,
      metadata: {
        report_count: reportRows.length,
        story_moments: storyItems.length,
        evidence_cards: groupedEvidenceItems.length,
      },
    })
  }, [activeTab, cleanRunId, error, groupedEvidenceItems.length, loading, reportRows.length, storyItems.length])

  function setReplayTab(tab) {
    setActiveTab(tab)
  }

  function toggleRawEvidence() {
    const nextValue = !showRawEvidence
    trackKpiEvent('raw_evidence_toggle', {
      runId: cleanRunId,
      surface: 'run_replay',
      target: nextValue ? 'show_raw_evidence' : 'show_story_evidence',
      metadata: {
        raw_evidence_count: rawEvidenceCount,
        hidden_routine_evidence_count: hiddenRoutineEvidenceCount,
      },
    })
    setShowRawEvidence(nextValue)
  }

  function selectEvidenceCategory(categoryKey) {
    if (categoryKey === selectedEvidenceCategory) return
    trackKpiEvent('evidence_filter_used', {
      runId: cleanRunId,
      surface: 'run_replay',
      target: categoryKey,
      metadata: {
        previous_category: selectedEvidenceCategory,
        show_raw_evidence: showRawEvidence,
      },
    })
    setActiveEvidenceCategory(categoryKey)
  }

  return (
    <div className="run-replay-page">
      <div className="page-header">
        <h1>
          <TimerReset size={32} />
          Run Replay
        </h1>
        <p className="page-description">
          Completed-run review with story playback, evidence, and report artifacts in one place.
        </p>
      </div>

      <div className="run-detail-topbar">
        <div className="run-id-pill">
          <Hash size={15} />
          <span>{cleanRunId || 'unknown-run'}</span>
        </div>
        <div className="run-topbar-actions">
          <Link className="btn btn-secondary" to={`/runs/${encodeURIComponent(cleanRunId)}`}>
            Evidence Detail
          </Link>
          <Link className="btn btn-secondary" to="/archive">
            Archive
          </Link>
        </div>
      </div>

      <div className="feed-notice">
        Replay is an observational reconstruction from run events. Use Evidence for source traces before making claims.
      </div>

      {loading && <div className="empty-state">Loading run replay...</div>}
      {!loading && error && <div className="feed-notice">{error}</div>}

      {!loading && !error && (
        <>
          <div className="run-replay-tabs" role="tablist" aria-label="Run replay views">
            {[
              ['overview', BarChart3, 'Overview'],
              ['replay', TimerReset, 'Replay'],
              ['evidence', FileSearch, 'Evidence'],
              ['reports', FileText, 'Reports'],
            ].map(([key, icon, label]) => (
              <button
                key={key}
                type="button"
                className={`filter-btn ${activeTab === key ? 'active' : ''}`}
                onClick={() => setReplayTab(key)}
              >
                {createElement(icon, { size: 15 })}
                {label}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <>
              <div className="card run-replay-brief-card">
                <div className="card-header">
                  <h3>Run In Brief</h3>
                  <span className="strip-meta">Completed-run recap</span>
                </div>
                <div className="card-body">
                  <p className="run-replay-brief-copy">{runBrief}</p>
                  <div className="run-replay-recap-grid">
                    {recapRows.map((row) => (
                      <div key={row.label} className={`run-replay-recap-item ${row.tone}`}>
                        <span>{row.label}</span>
                        <strong>{row.value}</strong>
                        <p>{row.detail}</p>
                      </div>
                    ))}
                  </div>
                  {narrativeBeats.length > 0 && (
                    <div className="run-replay-narrative" aria-label="Replay narrative beats">
                      {narrativeBeats.map((beat) => (
                        <button
                          key={beat.key}
                          type="button"
                          className="run-replay-beat"
                          onClick={() => setSelectedEventId(beat.eventId)}
                        >
                          <span>{beat.label}</span>
                          <strong>{beat.title}</strong>
                          <p>{beat.detail}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="stats-grid run-detail-stats">
                <div className="stat-card">
                  <div className="stat-header">
                    <span className="stat-label">Events</span>
                    <div className="stat-icon blue"><Activity size={18} /></div>
                  </div>
                  <div className="stat-value">{formatNumber(activity.total_events)}</div>
                  <div className="stat-change"><span>{formatLabel(runMetadata.run_class || 'run')}</span></div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <span className="stat-label">LLM Calls</span>
                    <div className="stat-icon green"><CircleCheck size={18} /></div>
                  </div>
                  <div className="stat-value">{formatNumber(llm.calls)}</div>
                  <div className="stat-change"><span>{formatNumber(llm.total_tokens)} tokens</span></div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <span className="stat-label">Deaths</span>
                  </div>
                  <div className="stat-value">{formatNumber(activity.deaths)}</div>
                  <div className="stat-change"><span>{formatNumber(activity.laws_passed)} laws passed</span></div>
                </div>
                <div className="stat-card">
                  <div className="stat-header">
                    <span className="stat-label">Estimated Cost</span>
                  </div>
                  <div className="stat-value run-currency">{formatUsd(llm.estimated_cost_usd)}</div>
                  <div className="stat-change"><span>{formatRelative(runDetail?.captured_at)}</span></div>
                </div>
              </div>

              <div className="card run-provenance-card">
                <div className="card-header">
                  <h3>
                    <ShieldCheck size={18} />
                    Replay Scope
                  </h3>
                </div>
                <div className="card-body">
                  <div className="run-provenance-grid">
                    <div>
                      <span className="label">Condition</span>
                      <strong>{formatLabel(runMetadata.condition_name || 'unknown')}</strong>
                    </div>
                    <div>
                      <span className="label">Time Window</span>
                      <strong>{formatTimestamp(provenance?.time_window?.start_utc)} to {formatTimestamp(provenance?.time_window?.end_utc)}</strong>
                    </div>
                    <div>
                      <span className="label">Verification</span>
                      <strong>{formatLabel(provenance.verification_state || 'unverified')}</strong>
                    </div>
                  </div>
                </div>
              </div>

              <div className="card run-outcome-card">
                <div className="card-header">
                  <h3>
                    <Activity size={18} />
                    Outcome Summary
                  </h3>
                </div>
                <div className="card-body run-outcome-grid">
                  {outcomeRows.map((row) => (
                    <div key={row.label} className="run-outcome-item">
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                      <p>{row.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {activeTab === 'replay' && (
            <>
              <div className="card run-replay-brief-card">
                <div className="card-header">
                  <h3>
                    <TimerReset size={18} />
                    What Happened
                  </h3>
                  <span className="strip-meta">{storyItems.length} curated moments</span>
                </div>
                <div className="card-body">
                  <p className="run-replay-brief-copy">{runBrief}</p>
                  <div className="run-replay-recap-grid">
                    {recapRows.map((row) => (
                      <div key={row.label} className={`run-replay-recap-item ${row.tone}`}>
                        <span>{row.label}</span>
                        <strong>{row.value}</strong>
                        <p>{row.detail}</p>
                      </div>
                    ))}
                  </div>
                  {narrativeBeats.length > 0 && (
                    <div className="run-replay-narrative" aria-label="Replay narrative beats">
                      {narrativeBeats.map((beat) => (
                        <button
                          key={beat.key}
                          type="button"
                          className="run-replay-beat"
                          onClick={() => setSelectedEventId(beat.eventId)}
                        >
                          <span>{beat.label}</span>
                          <strong>{beat.title}</strong>
                          <p>{beat.detail}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="run-replay-grid">
                <div className="card run-replay-rail">
                  <div className="card-header">
                    <h3>
                      <ListTree size={18} />
                      Story Threads
                    </h3>
                    <span className="strip-meta">{replayChapters.length} threads</span>
                  </div>
                  <div className="card-body">
                    {replayChapters.length === 0 ? (
                      <div className="empty-state compact">No curated replay moments are available yet. Routine work and idle events are hidden here; use Evidence for the raw log.</div>
                    ) : (
                      <div className="run-replay-chapter-list">
                        {replayChapters.map((chapter) => {
                          const selected = chapter.key === activeChapter?.key
                          return (
                            <button
                              key={chapter.key}
                              type="button"
                              className={`run-replay-chapter ${selected ? 'active' : ''}`}
                              onClick={() => setSelectedEventId(Number(chapter.lead_event_id || 0))}
                            >
                              <span>{chapter.count} moment{chapter.count === 1 ? '' : 's'}</span>
                              <strong>{chapter.label}</strong>
                              <em>{chapter.summary}</em>
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>

                <div className="card run-replay-main">
                  <div className="card-header">
                    <h3>{activeChapter ? activeChapter.label : 'Replay'}</h3>
                    {activeChapter && <span className="strip-meta">{activeChapter.count} moment{activeChapter.count === 1 ? '' : 's'}</span>}
                  </div>
                  <div className="card-body">
                    {activeChapter ? (
                      <>
                        <p className="run-replay-description">{activeChapter.summary}</p>
                        {activeStoryItem && (
                          <div className="run-replay-featured">
                            <div className="run-replay-featured-header">
                              <span>Selected moment</span>
                              <strong>{formatRelative(getEventTime(activeStoryItem))}</strong>
                            </div>
                            <h4>{getEventTitle(activeStoryItem)}</h4>
                            <p>{getEventDescription(activeStoryItem)}</p>
                            {activeStoryItem?.why_this_matters && (
                              <div className="run-replay-why">
                                <span>Why this mattered</span>
                                <p>{activeStoryItem.why_this_matters}</p>
                              </div>
                            )}
                            {Array.isArray(activeStoryItem?.deltas) && activeStoryItem.deltas.length > 0 && (
                              <div className="run-replay-deltas" aria-label="Replay moment signals">
                                {activeStoryItem.deltas.map((delta) => (
                                  <span key={`${delta.label}-${delta.value}`} className={`run-replay-delta ${delta.tone || 'neutral'}`}>
                                    <strong>{delta.label}</strong>
                                    {delta.value}
                                  </span>
                                ))}
                              </div>
                            )}
                            <div className="run-replay-actions">
                              {getEventId(activeStoryItem) > 0 && (
                                <>
                                  <Link className="btn btn-secondary" to={`/runs/${encodeURIComponent(cleanRunId)}?event=${getEventId(activeStoryItem)}`}>
                                    Evidence
                                  </Link>
                                  <Link className="btn btn-secondary" to={`/timeline?event=${getEventId(activeStoryItem)}`}>
                                    Raw Event Log
                                  </Link>
                                </>
                              )}
                            </div>
                          </div>
                        )}

                        {activeChapter.items.length > 1 && (
                          <div className="run-replay-moment-list" aria-label={`${activeChapter.label} moments`}>
                            {activeChapter.items.map((item, index) => {
                              const eventId = getEventId(item)
                              const selected = eventId > 0 && eventId === getEventId(activeStoryItem)
                              return (
                                <button
                                  key={`${eventId || index}-${getEventTitle(item)}`}
                                  type="button"
                                  className={`run-replay-moment-item ${selected ? 'active' : ''}`}
                                  onClick={() => setSelectedEventId(eventId)}
                                >
                                  <span>{formatLabel(item.event_type || item.category || 'event')}</span>
                                  <strong>{getEventTitle(item)}</strong>
                                  <p>{clampText(getEventDescription(item), 150)}</p>
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="empty-state compact">Replay data has not been generated for this run.</div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'evidence' && (
            <div className="card">
              <div className="card-header">
                <h3>{showRawEvidence ? 'Raw Evidence Links' : 'Story Evidence'}</h3>
                <span className="strip-meta">
                  {groupedEvidenceItems.length} cards · {filteredEvidenceItems.length} traces
                </span>
              </div>
              {rawEvidenceCount > 0 && (
                <div className="run-evidence-toolbar stacked">
                  <div>
                    <p>
                      {showRawEvidence
                        ? 'Showing raw source traces, including routine work and idle events.'
                        : `${hiddenRoutineEvidenceCount.toLocaleString()} routine or low-signal trace${hiddenRoutineEvidenceCount === 1 ? '' : 's'} hidden by default.`}
                    </p>
                    <p className="run-evidence-why">
                      <strong>{selectedEvidenceCategoryMeta.label}:</strong> {selectedEvidenceCategoryMeta.description}
                    </p>
                    {filteredEvidenceItems.length > groupedEvidenceItems.length && (
                      <p className="run-evidence-why">
                        <strong>Grouped:</strong> {filteredEvidenceItems.length.toLocaleString()} traces compressed into {groupedEvidenceItems.length.toLocaleString()} skimmable cards. Expand a card for every source trace and raw link.
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={toggleRawEvidence}
                  >
                    {showRawEvidence ? 'Show Story Evidence' : 'Show Raw Evidence'}
                  </button>
                </div>
              )}
              {evidenceCategoryFilters.length > 1 && (
                <div className="evidence-filter-row" aria-label="Evidence categories">
                  {evidenceCategoryFilters.map((filter) => (
                    <button
                      key={filter.key}
                      type="button"
                      aria-label={`${filter.label} ${filter.count}`}
                      className={`evidence-filter-chip ${selectedEvidenceCategory === filter.key ? 'active' : ''}`}
                      onClick={() => selectEvidenceCategory(filter.key)}
                    >
                      <span>{filter.label}</span>
                      <strong>{filter.count}</strong>
                    </button>
                  ))}
                </div>
              )}
              <div className="card-body run-trace-list">
                {groupedEvidenceItems.map((group, index) => {
                  const lead = group.lead || group.items[0] || {}
                  const eventId = Number(lead?.event_id || lead?.id || 0)
                  const groupMeta = EVIDENCE_CATEGORY_META[group.categoryKey] || EVIDENCE_CATEGORY_META.other
                  const leadDescription = getEventDescription(lead)
                  const extraSummaries = group.summaries
                    .filter((summary) => summary !== leadDescription)
                    .slice(0, 2)
                  return (
                    <div key={`${group.key}-${index}`} className={`run-trace-item ${group.count > 1 ? 'grouped' : ''}`}>
                      <div className="run-trace-main">
                        <div className="run-trace-title-row">
                          <h4>{lead.title || group.title || getEventTitle(lead)}</h4>
                          {group.count > 1 && (
                            <span className="run-trace-count">{group.count} traces</span>
                          )}
                        </div>
                        <p>{leadDescription}</p>
                        {extraSummaries.length > 0 && (
                          <div className="run-trace-summary-list" aria-label={`${group.title} grouped evidence examples`}>
                            {extraSummaries.map((summary) => (
                              <p key={summary}>{clampText(summary, 150)}</p>
                            ))}
                          </div>
                        )}
                        <div className="run-trace-meta">
                          <span>{groupMeta.label}</span>
                          <span>{formatLabel(lead.event_type || lead.category || 'event')}</span>
                          {lead.salience !== undefined && <span>Top salience {lead.salience}</span>}
                          <span>{formatRelative(getEventTime(lead))}</span>
                        </div>
                        {group.count > 1 && (
                          <details className="run-trace-details">
                            <summary>Show all {group.count} source traces</summary>
                            <div className="run-trace-detail-list">
                              {group.items.map((trace, traceIndex) => {
                                const traceEventId = Number(trace?.event_id || trace?.id || 0)
                                return (
                                  <div key={`${traceEventId || traceIndex}-${getEventDescription(trace)}`} className="run-trace-detail-row">
                                    <div>
                                      <strong>{trace.title || getEventTitle(trace)}</strong>
                                      <p>{getEventDescription(trace)}</p>
                                      <span>{formatRelative(getEventTime(trace)) || formatLabel(trace.event_type || 'event')}</span>
                                    </div>
                                    <div className="run-trace-detail-links">
                                      {trace.trace_url && (
                                        <a href={trace.trace_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
                                          Event API <ExternalLink size={14} />
                                        </a>
                                      )}
                                      {traceEventId > 0 && (
                                        <>
                                          <Link to={`/runs/${encodeURIComponent(cleanRunId)}?event=${traceEventId}`} className="btn btn-secondary">
                                            Detail
                                          </Link>
                                          <Link to={`/timeline?event=${traceEventId}`} className="btn btn-secondary">
                                            Raw Log
                                          </Link>
                                        </>
                                      )}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </details>
                        )}
                      </div>
                      <div className="run-trace-links">
                        {lead.trace_url && (
                          <a href={lead.trace_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
                            Event API <ExternalLink size={14} />
                          </a>
                        )}
                        {eventId > 0 && (
                          <>
                            <Link to={`/runs/${encodeURIComponent(cleanRunId)}?event=${eventId}`} className="btn btn-secondary">
                              Detail
                            </Link>
                            <Link to={`/timeline?event=${eventId}`} className="btn btn-secondary">
                              Raw Log
                            </Link>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
                {groupedEvidenceItems.length === 0 && (
                  <div className="empty-state compact">No event evidence is available for this run.</div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'reports' && (
            <div className="card">
              <div className="card-header">
                <h3>Report Artifacts</h3>
                <span className="strip-meta">{reportRows.length} available</span>
              </div>
              <div className="card-body reports-list">
                {reportRows.length === 0 ? (
                  <div className="empty-state compact">No report artifacts are available for this run.</div>
                ) : (
                  reportRows.map((row) => (
                    <div key={row.type} className="reports-item">
                      <div className="reports-item-main">
                        <strong>{REPORT_LABELS[row.type] || formatLabel(row.type)}</strong>
                        <span>{row.formats.join(', ')}</span>
                        <span>{formatTimestamp(row.updated_at)}</span>
                      </div>
                      <div className="reports-item-actions">
                        <Link
                          className="btn btn-secondary"
                          to={getReportViewPath(row)}
                        >
                          <FileText size={14} />
                          Open
                        </Link>
                        <a
                          className="btn btn-secondary"
                          href={getReportUrl(row, 'download')}
                        >
                          <Download size={14} />
                          Download
                        </a>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
