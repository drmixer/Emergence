import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Star,
  Zap,
  Clock,
  AlertTriangle,
  Award,
  Sparkles,
  MessageCircle,
  Flame,
  TrendingUp,
  TrendingDown,
  Minus,
  Share2,
  TimerReset,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api } from '../services/api'
import { trackShareAction } from '../services/shareAnalytics'
import { trackKpiEventOnce } from '../services/kpiAnalytics'
import { getMomentEvidenceHref, getMomentReplayHref } from '../utils/bestMoments'

const Recap = lazy(() => import('../components/Recap'))
const QuoteCardGenerator = lazy(() => import('../components/QuoteCard'))

const getImportanceColor = (importance) => {
  if (importance >= 100) return 'gold'
  if (importance >= 90) return 'purple'
  if (importance >= 80) return 'blue'
  if (importance >= 70) return 'green'
  return 'gray'
}

const eventTypeIcons = {
  world_event: Zap,
  law_passed: Award,
  proposal_resolved: AlertTriangle,
  agent_died: AlertTriangle,
  became_dormant: AlertTriangle,
  default: Star,
}

const getTurnRunId = (turn) => String(turn?.run_id || turn?.metadata?.runtime?.run_id || '').trim()
const VALID_TABS = new Set(['recap', 'highlights', 'summary', 'plotTurns', 'replay', 'quotes'])
const VALID_REPLAY_MODES = new Set(['timeline', 'story60'])
const MAJOR_CATEGORIES = new Set(['crisis', 'conflict', 'governance'])
const STORY_CHAPTERS = ['Trigger', 'Escalation', 'Turning Point', 'Outcome']
const REPLAY_BUCKET_MINUTES = 30

function resolveReplayMode(requestedMode, requestedEventId = 0) {
  if (VALID_REPLAY_MODES.has(requestedMode)) return requestedMode
  return requestedEventId > 0 ? 'timeline' : 'story60'
}

function getMomentTier(turn) {
  const salience = Number(turn?.salience || 0)
  const category = String(turn?.category || '')
  if (salience >= 85) return 'major'
  if (salience >= 72 && MAJOR_CATEGORIES.has(category)) return 'major'
  return 'minor'
}

function getTurnTimestamp(turn) {
  const timestamp = turn?.created_at ? new Date(turn.created_at).getTime() : 0
  return Number.isFinite(timestamp) ? timestamp : 0
}

function formatReplayBucketLabel(timestampMs, totalSpanMs = 0) {
  const date = new Date(timestampMs)
  if (!Number.isFinite(date.getTime())) return ''

  if (totalSpanMs > 24 * 60 * 60 * 1000) {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(date)
  }

  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function buildReplayBuckets(events, timeWindow, bucketMinutes = REPLAY_BUCKET_MINUTES) {
  const bucketMs = Math.max(10, Number(bucketMinutes || REPLAY_BUCKET_MINUTES)) * 60 * 1000
  const eventTimestamps = Array.isArray(events)
    ? events.map((turn) => getTurnTimestamp(turn)).filter((value) => value > 0)
    : []

  const requestedStart = timeWindow?.start_utc ? new Date(timeWindow.start_utc).getTime() : 0
  const requestedEnd = timeWindow?.end_utc ? new Date(timeWindow.end_utc).getTime() : 0

  let startMs = Number.isFinite(requestedStart) && requestedStart > 0 ? requestedStart : (eventTimestamps[0] || 0)
  let endMs = Number.isFinite(requestedEnd) && requestedEnd > 0 ? requestedEnd : (eventTimestamps[eventTimestamps.length - 1] || startMs)

  if (eventTimestamps.length > 0) {
    startMs = Math.min(startMs || eventTimestamps[0], eventTimestamps[0])
    endMs = Math.max(endMs || eventTimestamps[eventTimestamps.length - 1], eventTimestamps[eventTimestamps.length - 1])
  }

  if (!Number.isFinite(startMs) || startMs <= 0) return []
  if (!Number.isFinite(endMs) || endMs < startMs) endMs = startMs

  const totalSpanMs = Math.max(bucketMs, endMs - startMs)
  const bucketCount = Math.max(1, Math.ceil(totalSpanMs / bucketMs))
  const buckets = Array.from({ length: bucketCount }, (_, idx) => {
    const bucketStart = startMs + (idx * bucketMs)
    const bucketEnd = idx === bucketCount - 1 ? endMs : Math.min(endMs, bucketStart + bucketMs)
    return {
      index: idx,
      bucket_start: new Date(bucketStart).toISOString(),
      bucket_end: new Date(bucketEnd).toISOString(),
      label: formatReplayBucketLabel(bucketStart, totalSpanMs),
      event_count: 0,
      max_salience: 0,
      dominant_category: null,
      category_counts: {},
    }
  })

  for (const turn of events || []) {
    const timestamp = getTurnTimestamp(turn)
    if (timestamp <= 0 || timestamp < startMs || timestamp > endMs) continue
    const idx = Math.max(0, Math.min(bucketCount - 1, Math.floor((timestamp - startMs) / bucketMs)))
    const bucket = buckets[idx]
    bucket.event_count += 1
    bucket.max_salience = Math.max(Number(bucket.max_salience || 0), Number(turn?.salience || 0))
    const category = String(turn?.category || 'notable')
    bucket.category_counts[category] = Number(bucket.category_counts[category] || 0) + 1
    bucket.dominant_category = Object.keys(bucket.category_counts).sort((left, right) => {
      const countDelta = Number(bucket.category_counts[right] || 0) - Number(bucket.category_counts[left] || 0)
      if (countDelta !== 0) return countDelta
      return left.localeCompare(right)
    })[0] || 'notable'
  }

  return buckets
}

function pickReplayStoryMoments(turns, targetCount = 8) {
  const cleanTurns = Array.isArray(turns)
    ? turns.filter((turn) => Number(turn?.event_id || 0) > 0)
    : []
  if (cleanTurns.length === 0) return []

  const maxAvailable = Math.min(10, cleanTurns.length)
  const boundedTarget =
    cleanTurns.length >= 6
      ? Math.min(Math.max(targetCount, 6), maxAvailable)
      : maxAvailable

  const ranked = [...cleanTurns].sort((a, b) => {
    const salienceDelta = Number(b?.salience || 0) - Number(a?.salience || 0)
    if (salienceDelta !== 0) return salienceDelta
    return getTurnTimestamp(b) - getTurnTimestamp(a)
  })

  const selected = []
  const categoryCounts = {}
  const maxPerCategory = Math.max(2, Math.ceil(boundedTarget / 3))

  for (const turn of ranked) {
    if (selected.length >= boundedTarget) break

    const category = String(turn?.category || 'notable')
    const currentCategoryCount = Number(categoryCounts[category] || 0)
    if (currentCategoryCount >= maxPerCategory) continue

    const turnTimestamp = getTurnTimestamp(turn)
    const hasNearbySelected = selected.some((item) => {
      const itemTimestamp = getTurnTimestamp(item)
      return Math.abs(itemTimestamp - turnTimestamp) < 25 * 60 * 1000
    })

    if (hasNearbySelected && Number(turn?.salience || 0) < 85) continue

    selected.push(turn)
    categoryCounts[category] = currentCategoryCount + 1
  }

  if (selected.length < boundedTarget) {
    for (const turn of ranked) {
      if (selected.length >= boundedTarget) break
      if (selected.some((item) => Number(item?.event_id || 0) === Number(turn?.event_id || 0))) continue
      selected.push(turn)
    }
  }

  return selected.sort((a, b) => getTurnTimestamp(a) - getTurnTimestamp(b))
}

function getStoryChapterLabel(index, total) {
  if (total <= 1) return STORY_CHAPTERS[0]
  const ratio = index / Math.max(1, total - 1)
  if (ratio < 0.25) return STORY_CHAPTERS[0]
  if (ratio < 0.55) return STORY_CHAPTERS[1]
  if (ratio < 0.8) return STORY_CHAPTERS[2]
  return STORY_CHAPTERS[3]
}

function buildMomentDeltas(turn) {
  if (!turn || typeof turn !== 'object') return []

  const metadata = turn?.metadata && typeof turn.metadata === 'object' ? turn.metadata : {}
  const eventType = String(turn?.event_type || '')
  const category = String(turn?.category || '')
  const result = String(metadata?.result || '').trim().toLowerCase()
  const deltas = []

  if (eventType === 'law_passed') {
    deltas.push({ label: 'Laws', value: '+1', tone: 'up' })
  }

  if (eventType === 'agent_died') {
    deltas.push({ label: 'Deaths', value: '+1', tone: 'down' })
  }

  if (eventType === 'proposal_resolved') {
    let value = 'Resolved'
    let tone = 'neutral'
    if (result === 'passed') {
      value = 'Passed'
      tone = 'up'
    } else if (result === 'failed' || result === 'expired') {
      value = result[0].toUpperCase() + result.slice(1)
      tone = 'down'
    }
    deltas.push({ label: 'Proposal', value, tone })
  }

  if (category === 'alliance' || category === 'cooperation') {
    deltas.push({ label: 'Coalitions', value: 'Alignment Shift', tone: 'up' })
  }

  if (category === 'conflict') {
    deltas.push({ label: 'Conflict', value: 'Escalation', tone: 'alert' })
  }

  if (category === 'crisis') {
    deltas.push({ label: 'Pressure', value: 'System Shock', tone: 'alert' })
  }

  const effect = metadata?.effect && typeof metadata.effect === 'object' ? metadata.effect : {}
  const effectResource = String(effect?.resource || metadata?.resource || '').trim()
  if (effectResource) {
    deltas.push({
      label: effectResource[0].toUpperCase() + effectResource.slice(1),
      value: 'Resource Swing',
      tone: 'neutral',
    })
  } else if (
    effect?.reduce_all_agents !== undefined ||
    effect?.disable_communication !== undefined ||
    effect?.consumption_modifier !== undefined
  ) {
    deltas.push({ label: 'Resources', value: 'Global Shift', tone: 'alert' })
  }

  const impactedAgents = Number(metadata?.affected_agents || metadata?.impacted_agents || 0)
  if (Number.isFinite(impactedAgents) && impactedAgents > 0) {
    deltas.push({ label: 'Impacted', value: `${Math.round(impactedAgents)} agents`, tone: 'neutral' })
  }

  const deduped = []
  const seenLabels = new Set()
  for (const delta of deltas) {
    const label = String(delta?.label || '')
    if (!label || seenLabels.has(label)) continue
    seenLabels.add(label)
    deduped.push(delta)
    if (deduped.length >= 4) break
  }

  return deduped
}

function getWhyThisMatters(turn) {
  const category = String(turn?.category || '')
  const eventType = String(turn?.event_type || '')

  if (eventType === 'law_passed' || category === 'governance') {
    return 'Governance changed the rule set, so incentives and downstream behavior likely shifted after this moment.'
  }
  if (category === 'crisis') {
    return 'A system-level shock altered constraints for many agents at once and can redirect the entire run trajectory.'
  }
  if (category === 'conflict') {
    return 'Conflict spikes coordination costs and can rapidly reorder faction trust, trade flow, and survival outcomes.'
  }
  if (category === 'alliance' || category === 'cooperation') {
    return 'Coordination and alliances change who can execute strategy, absorb shocks, and control governance outcomes.'
  }
  return 'This high-salience event changed momentum and helps explain why subsequent actions unfolded the way they did.'
}

export default function Highlights() {
  const [searchParams] = useSearchParams()
  const requestedTab = String(searchParams.get('tab') || '').trim()
  const requestedEventId = Number(searchParams.get('event') || 0)
  const runFilter = String(searchParams.get('run') || '').trim()
  const requestedReplayMode = String(searchParams.get('mode') || '').trim()

  const [summary, setSummary] = useState(null)
  const [bestMoments, setBestMoments] = useState([])
  const [plotTurns, setPlotTurns] = useState([])
  const [replayTurns, setReplayTurns] = useState([])
  const [replayStory, setReplayStory] = useState({ items: [], chapters: [] })
  const [replayBuckets, setReplayBuckets] = useState([])
  const [replayIndex, setReplayIndex] = useState(-1)
  const [replayPlayback, setReplayPlayback] = useState(null)
  const [replayMode, setReplayMode] = useState(resolveReplayMode(requestedReplayMode, requestedEventId))
  const [storyMomentIndex, setStoryMomentIndex] = useState(0)
  const [selectedReplayEventId, setSelectedReplayEventId] = useState(0)
  const [showSourceDetail, setShowSourceDetail] = useState(false)
  const [activeRunId, setActiveRunId] = useState('')
  const [selectedRunId, setSelectedRunId] = useState('')
  const [invalidArchivedRunId, setInvalidArchivedRunId] = useState('')
  const [overview, setOverview] = useState(null)
  const [emergenceMetrics, setEmergenceMetrics] = useState(null)
  const [shareNotice, setShareNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [tabLoading, setTabLoading] = useState({})
  const [loadedTabs, setLoadedTabs] = useState({})
  const [activeTab, setActiveTab] = useState(VALID_TABS.has(requestedTab) ? requestedTab : 'recap')

  useEffect(() => {
    if (VALID_TABS.has(requestedTab)) {
      setActiveTab(requestedTab)
    }
  }, [requestedTab])

  useEffect(() => {
    setReplayMode(resolveReplayMode(requestedReplayMode, requestedEventId))
    setShowSourceDetail(false)
  }, [runFilter, requestedReplayMode, requestedEventId])

  useEffect(() => {
    setReplayMode(resolveReplayMode(requestedReplayMode, requestedEventId))
  }, [requestedReplayMode, requestedEventId])

  useEffect(() => {
    let cancelled = false

    async function loadBase() {
      setLoading(true)
      setTabLoading({})
      setLoadedTabs({})
      setSummary(null)
      setBestMoments([])
      setPlotTurns([])
      setReplayTurns([])
      setReplayStory({ items: [], chapters: [] })
      setReplayBuckets([])
      setReplayIndex(-1)
      setReplayPlayback(null)
      setInvalidArchivedRunId('')
      setOverview(null)
      setEmergenceMetrics(null)

      try {
        const archiveView = Boolean(runFilter)
        if (archiveView) {
          try {
            await api.fetch(`/api/analytics/runs/${encodeURIComponent(runFilter)}?trace_limit=1&min_salience=0`, {
              quietStatusCodes: [404],
            })
            if (cancelled) return
            setActiveRunId('')
            setSelectedRunId(runFilter)
            setOverview(null)
          } catch (error) {
            if (cancelled) return
            if (Number(error?.status || 0) === 404) {
              setActiveRunId('')
              setSelectedRunId('')
              setInvalidArchivedRunId(runFilter)
              setOverview(null)
            } else {
              setActiveRunId('')
              setSelectedRunId(runFilter)
              setOverview(null)
            }
          }
        } else {
          const overviewPayload = await api.getAnalyticsOverview().catch(() => null)
          if (cancelled) return
          const liveRunId = String(overviewPayload?.scope?.active_run_id || '').trim()
          const lastCompletedRunId = String(overviewPayload?.scope?.last_completed_run_id || '').trim()
          setActiveRunId(liveRunId)
          setSelectedRunId(liveRunId || lastCompletedRunId)
          setOverview(overviewPayload && typeof overviewPayload === 'object' ? overviewPayload : null)
        }
      } catch {
        if (cancelled) return
        setActiveRunId('')
        setSelectedRunId(runFilter || '')
        setOverview(null)
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadBase()
    return () => {
      cancelled = true
    }
  }, [runFilter])

  useEffect(() => {
    if (loading) return
    if (Boolean(runFilter) && invalidArchivedRunId) return
    if (activeTab === 'recap' || activeTab === 'quotes') return
    if (loadedTabs[activeTab]) return

    let cancelled = false
    const scopedRunId = String(selectedRunId || '').trim()
    const archiveView = Boolean(runFilter)

    async function loadTabData() {
      setTabLoading((prev) => ({ ...prev, [activeTab]: true }))
      try {
        if (activeTab === 'highlights') {
          const payload = await api.getBestMoments(6, 72, 55, scopedRunId).catch(() => ({ items: [] }))
          if (cancelled) return
          setBestMoments(Array.isArray(payload?.items) ? payload.items : [])
        } else if (activeTab === 'summary') {
          const payload = await api.getLatestSummary(scopedRunId).catch(() => null)
          if (cancelled) return
          setSummary(payload?.summary ? payload : null)
        } else if (activeTab === 'plotTurns') {
          const [turns, metricsPayload] = await Promise.all([
            api.getPlotTurns(16, 72, 60, scopedRunId).catch(() => ({ items: [] })),
            archiveView || emergenceMetrics
              ? Promise.resolve(emergenceMetrics)
              : api.fetch('/api/analytics/emergence/metrics?hours=24').catch(() => null),
          ])
          if (cancelled) return
          setPlotTurns(Array.isArray(turns?.items) ? turns.items : [])
          if (!archiveView && !emergenceMetrics) {
            setEmergenceMetrics(metricsPayload && typeof metricsPayload === 'object' ? metricsPayload : null)
          }
        } else if (activeTab === 'replay') {
          if (!scopedRunId) {
            setReplayTurns([])
            setReplayStory({ items: [], chapters: [] })
            setReplayBuckets([])
            setReplayIndex(-1)
            setReplayPlayback(null)
          } else {
            const [replay, replayStoryPayload, metricsPayload] = await Promise.all([
              api.getRunPlayback(scopedRunId).catch(() => ({ items: [], time_window: null, contract: null })),
              api.getReplayStory(24, 55, 8, scopedRunId).catch(() => ({ items: [], chapters: [] })),
              archiveView || emergenceMetrics
                ? Promise.resolve(emergenceMetrics)
                : api.fetch('/api/analytics/emergence/metrics?hours=24').catch(() => null),
            ])
            if (cancelled) return
            const playbackItems = Array.isArray(replay?.items) ? replay.items : []
            setReplayTurns(playbackItems)
            setReplayPlayback(replay && typeof replay === 'object' ? replay : null)
            setReplayStory({
              items: Array.isArray(replayStoryPayload?.items) ? replayStoryPayload.items : [],
              chapters: Array.isArray(replayStoryPayload?.chapters) ? replayStoryPayload.chapters : [],
            })
            const buckets = buildReplayBuckets(playbackItems, replay?.time_window, REPLAY_BUCKET_MINUTES)
            setReplayBuckets(buckets)
            setReplayIndex(buckets.length > 0 ? buckets.length - 1 : -1)
            if (!archiveView && !emergenceMetrics) {
              setEmergenceMetrics(metricsPayload && typeof metricsPayload === 'object' ? metricsPayload : null)
            }
          }
        }

        setLoadedTabs((prev) => ({ ...prev, [activeTab]: true }))
      } finally {
        if (!cancelled) {
          setTabLoading((prev) => ({ ...prev, [activeTab]: false }))
        }
      }
    }

    loadTabData()
    return () => {
      cancelled = true
    }
  }, [activeTab, emergenceMetrics, invalidArchivedRunId, loadedTabs, loading, runFilter, selectedRunId])

  const activeReplayBucket =
    replayIndex >= 0 && replayIndex < replayBuckets.length ? replayBuckets[replayIndex] : null

  const replayBucketEvents = useMemo(() => {
    if (!activeReplayBucket) return []
    const bucketStart = new Date(activeReplayBucket.bucket_start).getTime()
    const bucketEnd = new Date(activeReplayBucket.bucket_end).getTime()

    return replayTurns
      .filter((turn) => {
        const createdAt = turn.created_at ? new Date(turn.created_at).getTime() : 0
        return createdAt >= bucketStart && createdAt <= bucketEnd
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [replayTurns, activeReplayBucket])

  const replayRecent = useMemo(() => {
    if (!activeReplayBucket) return []
    const bucketEnd = new Date(activeReplayBucket.bucket_end).getTime()

    return replayTurns
      .filter((turn) => {
        const createdAt = turn.created_at ? new Date(turn.created_at).getTime() : 0
        return createdAt <= bucketEnd
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 8)
  }, [replayTurns, activeReplayBucket])

  const replayStoryMoments = useMemo(() => {
    if (Array.isArray(replayStory.items) && replayStory.items.length > 0) {
      return replayStory.items
    }
    const selected = pickReplayStoryMoments(replayTurns, 8)
    return selected.map((turn, index) => ({
      ...turn,
      chapter: getStoryChapterLabel(index, selected.length),
      why_this_matters: getWhyThisMatters(turn),
      deltas: buildMomentDeltas(turn),
    }))
  }, [replayTurns, replayStory.items])

  const replayStoryChapters = useMemo(() => {
    if (Array.isArray(replayStory.chapters) && replayStory.chapters.length > 0) {
      return replayStory.chapters
    }
    return STORY_CHAPTERS.map((label) => {
      const chapterItems = replayStoryMoments.filter((item) => item?.chapter === label)
      return {
        label,
        count: chapterItems.length,
        description: '',
        lead_event_id: Number(chapterItems[0]?.event_id || 0),
      }
    }).filter((chapter) => chapter.count > 0)
  }, [replayStory.chapters, replayStoryMoments])

  const activeStoryMoment =
    storyMomentIndex >= 0 && storyMomentIndex < replayStoryMoments.length
      ? replayStoryMoments[storyMomentIndex]
      : null

  const activeTimelineMoment = useMemo(() => {
    if (selectedReplayEventId > 0) {
      const selected = replayTurns.find((turn) => Number(turn?.event_id || 0) === selectedReplayEventId)
      if (selected) return selected
    }
    return replayBucketEvents[0] || replayRecent[0] || replayTurns[replayTurns.length - 1] || null
  }, [selectedReplayEventId, replayTurns, replayBucketEvents, replayRecent])

  const activeReplayMoment = replayMode === 'story60' ? activeStoryMoment : activeTimelineMoment
  const replayContract = replayPlayback?.contract && typeof replayPlayback.contract === 'object'
    ? replayPlayback.contract
    : null
  const replayTimeWindow = replayPlayback?.time_window && typeof replayPlayback.time_window === 'object'
    ? replayPlayback.time_window
    : null

  const activeReplayMomentDeltas = useMemo(() => buildMomentDeltas(activeReplayMoment), [activeReplayMoment])
  const activeReplayEvidence = useMemo(() => {
    const turn = activeReplayMoment
    if (!turn) return { runDetailHref: '', evidenceApiHref: '' }
    const runId = getTurnRunId(turn)
    const eventId = Number(turn?.event_id || 0)
    if (!runId) return { runDetailHref: '', evidenceApiHref: '' }
    const safeRunId = encodeURIComponent(runId)
    const runDetailHref = `/runs/${safeRunId}${eventId > 0 ? `?event=${eventId}` : ''}`
    const evidenceApiHref = `/api/analytics/runs/${safeRunId}?trace_limit=20&min_salience=55`
    return { runDetailHref, evidenceApiHref }
  }, [activeReplayMoment])

  const isArchiveView = Boolean(runFilter)
  const invalidArchiveState = isArchiveView && Boolean(invalidArchivedRunId)
  const showLiveStateStrip = !isArchiveView && !!selectedRunId && selectedRunId === activeRunId
  const highlightsLoading = loading || Boolean(tabLoading.highlights)
  const summaryLoading = loading || Boolean(tabLoading.summary)
  const plotTurnsLoading = loading || Boolean(tabLoading.plotTurns)
  const replayLoading = loading || Boolean(tabLoading.replay)
  const runScopeLabel = invalidArchiveState
    ? `Requested archived run ${invalidArchivedRunId} not found`
    : isArchiveView && selectedRunId
    ? `Selected run ${selectedRunId}`
    : (showLiveStateStrip ? 'Active run' : 'Latest available run')
  const recapTabLabel = isArchiveView ? 'Run Recap' : 'Run Summary So Far'
  const plotTurnsLabel = isArchiveView ? 'Key Moments' : 'What Changed'

  const stateStrip = useMemo(() => {
    const day = Number(overview?.day_number || 0)
    const deaths = Number(overview?.agents?.dead || 0)
    const laws = Number(overview?.laws?.total || 0)
    const coalitionIndex = Number(emergenceMetrics?.metrics?.coalition_edge_count || 0)
    const cooperationRate = Number(emergenceMetrics?.metrics?.cooperation_rate || 0)
    const conflictRate = Number(emergenceMetrics?.metrics?.conflict_rate || 0)
    let trend = 'flat'
    let trendLabel = 'Balanced'
    if (cooperationRate - conflictRate >= 0.08) {
      trend = 'up'
      trendLabel = 'Cooperation rising'
    } else if (conflictRate - cooperationRate >= 0.08) {
      trend = 'down'
      trendLabel = 'Conflict rising'
    }
    return { day, deaths, laws, coalitionIndex, trend, trendLabel }
  }, [overview, emergenceMetrics])

  useEffect(() => {
    if (replayStoryMoments.length === 0) {
      setStoryMomentIndex(0)
      return
    }

    if (requestedEventId > 0) {
      const requestedIndex = replayStoryMoments.findIndex(
        (turn) => Number(turn?.event_id || 0) === requestedEventId
      )
      if (requestedIndex >= 0) {
        setStoryMomentIndex(requestedIndex)
        return
      }
    }

    setStoryMomentIndex((prev) => {
      if (prev < 0) return 0
      if (prev >= replayStoryMoments.length) return replayStoryMoments.length - 1
      return prev
    })
  }, [replayStoryMoments, requestedEventId])

  useEffect(() => {
    if (activeTab !== 'replay') return
    if (requestedEventId > 0) {
      setSelectedReplayEventId(requestedEventId)
      return
    }

    setSelectedReplayEventId((prev) => {
      if (prev > 0 && replayTurns.some((turn) => Number(turn?.event_id || 0) === prev)) {
        return prev
      }
      const fallback = Number(
        replayBucketEvents[0]?.event_id ||
        replayRecent[0]?.event_id ||
        replayTurns[replayTurns.length - 1]?.event_id ||
        0
      )
      return fallback
    })
  }, [activeTab, requestedEventId, replayTurns, replayBucketEvents, replayRecent])

  const shareMoment = async (turn, surface = 'highlights_plot_turn') => {
    const eventId = Number(turn?.event_id || 0)
    if (!eventId) return
    const runId = getTurnRunId(turn)
    const origin = window.location.origin
    const shareUrl = runId
      ? `${origin}/share/run/${encodeURIComponent(runId)}/moment/${eventId}`
      : `${origin}/share/moment/${eventId}`
    const shareTitle = turn?.title || 'Emergence moment'
    const shareText = String(turn?.description || '').slice(0, 200)
    trackShareAction('share_clicked', {
      runId,
      eventId,
      surface,
      target: 'moment_link',
    })

    try {
      if (navigator.share) {
        await navigator.share({ title: shareTitle, text: shareText, url: shareUrl })
        trackShareAction('share_native_success', {
          runId,
          eventId,
          surface,
          target: 'moment_link',
        })
        setShareNotice('Moment shared.')
      } else {
        await navigator.clipboard.writeText(shareUrl)
        trackShareAction('share_copied', {
          runId,
          eventId,
          surface,
          target: 'moment_link',
        })
        setShareNotice('Moment link copied.')
      }
      setTimeout(() => setShareNotice(''), 2000)
    } catch (error) {
      if (error?.name !== 'AbortError') {
        setShareNotice('Unable to share right now.')
        setTimeout(() => setShareNotice(''), 2000)
      }
    }
  }

  const TrendIcon = stateStrip.trend === 'up' ? TrendingUp : stateStrip.trend === 'down' ? TrendingDown : Minus

  useEffect(() => {
    const replayReady = replayMode === 'story60'
      ? replayStoryMoments.length > 0
      : replayBuckets.length > 0
    if (replayLoading || activeTab !== 'replay' || !replayReady) return
    trackKpiEventOnce('replay_start', `replay_start:${selectedRunId || 'all'}:${replayMode}`, {
      runId: selectedRunId,
      surface: 'highlights_replay_tab',
      target: replayMode === 'story60'
        ? 'story60'
        : (requestedEventId > 0 ? 'focused_event' : 'default'),
    })
  }, [replayLoading, activeTab, replayMode, replayBuckets.length, replayStoryMoments.length, selectedRunId, requestedEventId])

  useEffect(() => {
    if (replayLoading || activeTab !== 'replay') return
    const timelineCompleted = replayMode !== 'story60' && replayBuckets.length >= 2 && replayIndex === 0
    const storyCompleted =
      replayMode === 'story60' &&
      replayStoryMoments.length >= 2 &&
      storyMomentIndex === replayStoryMoments.length - 1

    if (!timelineCompleted && !storyCompleted) return
    const target = replayMode === 'story60' ? 'story60_last_moment' : 'timeline_start_reached'
    trackKpiEventOnce('replay_complete', `replay_complete:${selectedRunId || 'all'}:${replayMode}`, {
      runId: selectedRunId,
      surface: 'highlights_replay_tab',
      target,
    })
  }, [replayLoading, activeTab, replayMode, replayBuckets.length, replayIndex, replayStoryMoments.length, storyMomentIndex, selectedRunId])

  return (
    <div className="highlights-page">
      <div className="page-header">
        <h1>
          <Star size={32} />
          Highlights
        </h1>
        <p className="page-description">
          {invalidArchiveState
            ? `Requested archived run ${invalidArchivedRunId} could not be found`
            : isArchiveView && selectedRunId
            ? `Run recap, replay, and evidence surfaces for archived run ${selectedRunId}`
            : activeRunId
              ? 'Live story desk for the current run: recap, what changed, replay, and summary'
              : 'Recap, key moments, replay, and summary from the latest available run'}
        </p>
      </div>

      <div className="feed-notice">
        Highlights are observational summaries from simulation data. For claim-level evidence, review run detail traces and the <Link to="/method">method notes</Link>.
      </div>

      {requestedTab === 'predictions' && (
        <div className="feed-notice">
          Predictions now live on their own page. <Link to="/predictions">Open the prediction market</Link>.
        </div>
      )}

      {invalidArchiveState ? (
        <div className="feed-notice">
          Requested archived run <strong>{invalidArchivedRunId}</strong> was not found. <Link to="/archive">Choose a completed run from the archive</Link>.
        </div>
      ) : isArchiveView && selectedRunId && (
        <div className="feed-notice">
          Viewing archived run <strong>{selectedRunId}</strong>. <Link to="/archive">Back to archive</Link>
        </div>
      )}

      <div className="highlight-tabs">
        <button
          className={`tab-btn ${activeTab === 'recap' ? 'active' : ''}`}
          onClick={() => setActiveTab('recap')}
        >
          <Sparkles size={16} />
          {recapTabLabel}
        </button>
        <button
          className={`tab-btn ${activeTab === 'highlights' ? 'active' : ''}`}
          onClick={() => setActiveTab('highlights')}
        >
          <Star size={16} />
          Best Moments
        </button>
        <button
          className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
          onClick={() => setActiveTab('summary')}
        >
          <Clock size={16} />
          Daily Summary
        </button>
        <button
          className={`tab-btn ${activeTab === 'plotTurns' ? 'active' : ''}`}
          onClick={() => setActiveTab('plotTurns')}
        >
          <Flame size={16} />
          {plotTurnsLabel}
        </button>
        <button
          className={`tab-btn ${activeTab === 'replay' ? 'active' : ''}`}
          onClick={() => setActiveTab('replay')}
        >
          <TimerReset size={16} />
          Replay
        </button>
        <button
          className={`tab-btn ${activeTab === 'quotes' ? 'active' : ''}`}
          onClick={() => setActiveTab('quotes')}
        >
          <MessageCircle size={16} />
          Quote Cards
        </button>
      </div>

      {!invalidArchiveState && showLiveStateStrip && (activeTab === 'plotTurns' || activeTab === 'replay') && (
        <>
          <div className="feed-notice">Scope: Active run</div>
          <div className="state-strip">
            <div className="state-item">
              <span>Day</span>
              <strong>{stateStrip.day}</strong>
            </div>
            <div className="state-item">
              <span>Deaths</span>
              <strong>{stateStrip.deaths}</strong>
            </div>
            <div className="state-item">
              <span>Laws</span>
              <strong>{stateStrip.laws}</strong>
            </div>
            <div className="state-item">
              <span>Coalition Index</span>
              <strong>{stateStrip.coalitionIndex}</strong>
            </div>
            <div className={`state-item trend ${stateStrip.trend}`}>
              <span>Trend</span>
              <strong><TrendIcon size={14} /> {stateStrip.trendLabel}</strong>
            </div>
          </div>
        </>
      )}

      {shareNotice && <div className="feed-notice success">{shareNotice}</div>}

      {invalidArchiveState && (
        <div className="empty-state">
          Archived run <strong>{invalidArchivedRunId}</strong> was not found. Return to <Link to="/archive">the runs archive</Link> and choose a completed run.
        </div>
      )}

      {!invalidArchiveState && activeTab === 'recap' && (
        <Suspense fallback={<div className="empty-state">Loading recap…</div>}>
          <Recap runId={selectedRunId} title={recapTabLabel.toUpperCase()} scopeLabel={runScopeLabel} />
        </Suspense>
      )}

      {!invalidArchiveState && activeTab === 'quotes' && (
        <Suspense fallback={<div className="empty-state">Loading quote cards…</div>}>
          <QuoteCardGenerator />
        </Suspense>
      )}

      {!invalidArchiveState && activeTab === 'highlights' && (
        <div className="featured-events">
          <div className="featured-intro">
            <h3>Best Moments</h3>
            <p>The fastest way to understand why this run matters, with replay and evidence links on every card.</p>
            <span>Scope: {runScopeLabel}</span>
          </div>
          {highlightsLoading && (
            <div className="empty-state">Loading best moments…</div>
          )}
          {!highlightsLoading && bestMoments.length === 0 && (
            <div className="empty-state">No best moments yet.</div>
          )}
          {bestMoments.map((turn) => {
            const Icon = eventTypeIcons[turn.event_type] || eventTypeIcons.default
            const color = getImportanceColor(turn.salience)
            const evidenceHref = getMomentEvidenceHref(turn)
            const replayHref = getMomentReplayHref(turn)

            return (
              <div key={turn.event_id} className={`featured-card color-${color}`}>
                <div className="featured-header">
                  <div className={`featured-icon ${color}`}>
                    <Icon size={20} />
                  </div>
                  <div className="featured-meta">
                    <span className="featured-type">{turn.label || 'Best moment'}</span>
                    <span className="featured-time">
                      {formatDistanceToNow(new Date(turn.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  <div className={`importance-badge ${color}`}>
                    {turn.salience}
                  </div>
                </div>
                <h3 className="featured-title">{turn.title}</h3>
                <p className="featured-description">{turn.stake || 'This moment changed momentum and helps explain what happened next.'}</p>
                <div className="featured-actions">
                  {evidenceHref && (
                    <Link to={evidenceHref} className="plot-turn-run-link">
                      Evidence
                    </Link>
                  )}
                  <Link to={replayHref} className="plot-turn-run-link">
                    Replay
                  </Link>
                  <button type="button" className="moment-share-btn" onClick={() => shareMoment(turn, 'highlights_best_moments')}>
                    <Share2 size={14} />
                    Share
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!invalidArchiveState && activeTab === 'summary' && (
        <div className="daily-summary">
          {summaryLoading ? (
            <div className="empty-state">Loading daily summary…</div>
          ) : !summary ? (
            <div className="empty-state">No daily summary yet.</div>
          ) : (
            <div className="summary-card">
              <div className="summary-header">
                <h2>
                  {summary.source === 'run_summary_fallback'
                    ? `Run ${summary.run_id || selectedRunId || 'Latest'} Summary`
                    : (summary.day_number ? `Day ${summary.day_number} Summary` : `Run ${selectedRunId || 'Latest'} Summary`)}
                </h2>
                <span className="summary-date">
                  {summary.created_at ? new Date(summary.created_at).toLocaleDateString() : ''}
                </span>
              </div>

              {summary.source === 'run_summary_fallback' && (
                <div className="feed-notice">
                  Daily summary is unavailable for this run window. Showing the scoped run-summary fallback.
                </div>
              )}

              {summary.stats && (
                <>
                  <div className="feed-notice">Scope: {runScopeLabel}</div>
                  <div className="summary-stats">
                    {summary.stats.active_agents !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.active_agents}</div>
                        <div className="stat-label">Active</div>
                      </div>
                    )}
                    {summary.stats.dormant_agents !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.dormant_agents}</div>
                        <div className="stat-label">Dormant</div>
                      </div>
                    )}
                    {summary.stats.messages !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.messages}</div>
                        <div className="stat-label">Messages</div>
                      </div>
                    )}
                    {summary.stats.votes !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.votes}</div>
                        <div className="stat-label">Votes</div>
                      </div>
                    )}
                    {summary.stats.laws_passed !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.laws_passed}</div>
                        <div className="stat-label">Laws</div>
                      </div>
                    )}
                    {summary.stats.total_events !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.total_events}</div>
                        <div className="stat-label">Events</div>
                      </div>
                    )}
                    {summary.stats.llm_calls !== undefined && (
                      <div className="summary-stat">
                        <div className="stat-value">{summary.stats.llm_calls}</div>
                        <div className="stat-label">LLM Calls</div>
                      </div>
                    )}
                  </div>
                </>
              )}

              <div className="summary-content">
                {String(summary.summary || '').split('\n\n').map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!invalidArchiveState && activeTab === 'plotTurns' && (
        <div className="plot-turns-panel">
          <div className="featured-intro">
            <h3>{plotTurnsLabel}</h3>
            <p>
              {isArchiveView
                ? 'Curated high-salience moments for the selected archived run.'
                : 'The most visible changes shaping the active run right now.'}
            </p>
            <span>Scope: {runScopeLabel}</span>
          </div>
          {plotTurnsLoading && (
            <div className="empty-state">Loading {plotTurnsLabel.toLowerCase()}…</div>
          )}
          {!plotTurnsLoading && plotTurns.length === 0 && (
            <div className="empty-state">No {plotTurnsLabel.toLowerCase()} yet.</div>
          )}
          {plotTurns.map((turn) => {
            const turnRunId = getTurnRunId(turn)
            const tier = getMomentTier(turn)
            const isFocused = requestedEventId > 0 && Number(turn.event_id) === requestedEventId
            return (
              <div
                key={turn.event_id}
                className={`plot-turn-card category-${turn.category || 'notable'} tier-${tier} ${isFocused ? 'focused' : ''}`}
              >
                <div className="plot-turn-row">
                  <h3>
                    {turn.title}
                    <span className={`moment-tier-badge ${tier}`}>{tier === 'major' ? 'Major Moment' : 'Minor Moment'}</span>
                  </h3>
                  <span className="plot-turn-salience">Signal {turn.salience}</span>
                </div>
                <p>{turn.description}</p>
                <div className="plot-turn-meta">
                  <span className="plot-turn-category">{(turn.category || 'notable').replace(/_/g, ' ')}</span>
                  <span>
                    {turn.created_at ? formatDistanceToNow(new Date(turn.created_at), { addSuffix: true }) : ''}
                  </span>
                  {turnRunId && (
                    <Link to={`/runs/${encodeURIComponent(turnRunId)}`} className="plot-turn-run-link">
                      Run {turnRunId}
                    </Link>
                  )}
                  <button type="button" className="moment-share-btn" onClick={() => shareMoment(turn, 'highlights_plot_turn')}>
                    <Share2 size={12} />
                    Share this moment
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!invalidArchiveState && activeTab === 'replay' && (
        <div className="replay-panel">
          {replayLoading && <div className="empty-state">Loading replay…</div>}
          {!replayLoading && replayBuckets.length === 0 && (
            <div className="empty-state">No replay data for this run yet.</div>
          )}

          {replayBuckets.length > 0 && activeReplayBucket && (
            <>
              <div className="replay-intro-card">
                <div>
                  <strong>Replay in 60 Seconds</strong>
                  <p>Story mode is a curated chaptered recap. Timeline mode is canonical event playback for the selected run.</p>
                </div>
                <span>
                  {replayMode === 'story60'
                    ? `${replayStoryMoments.length} curated moments`
                    : `${replayTurns.length} replay events`}
                </span>
              </div>

              <div className="replay-mode-toggle">
                <button
                  type="button"
                  className={`tab-btn ${replayMode === 'story60' ? 'active' : ''}`}
                  onClick={() => setReplayMode('story60')}
                >
                  Replay in 60 Seconds
                </button>
                <button
                  type="button"
                  className={`tab-btn ${replayMode === 'timeline' ? 'active' : ''}`}
                  onClick={() => setReplayMode('timeline')}
                >
                  Replay Timeline
                </button>
              </div>

              {replayMode === 'timeline' ? (
                <>
                  <div className="replay-header">
                    <h3>Replay Timeline</h3>
                    <span>
                      Slice {replayIndex + 1}/{replayBuckets.length} · {activeReplayBucket.label} · {activeReplayBucket.event_count} event
                      {activeReplayBucket.event_count === 1 ? '' : 's'}
                    </span>
                  </div>
                  <div className="replay-source-note">
                    <strong>Canonical playback</strong>
                    <span>
                      {replayContract?.ordering === 'created_at_asc_id_asc'
                        ? 'Ordered by created_at then id.'
                        : 'Run-scoped event playback.'}
                    </span>
                    {replayTimeWindow?.start_utc && replayTimeWindow?.end_utc && (
                      <em>
                        {formatDistanceToNow(new Date(replayTimeWindow.start_utc), { addSuffix: true })} to{' '}
                        {formatDistanceToNow(new Date(replayTimeWindow.end_utc), { addSuffix: true })}
                      </em>
                    )}
                  </div>

                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, replayBuckets.length - 1)}
                    step={1}
                    value={Math.max(0, replayIndex)}
                    onChange={(event) => setReplayIndex(Number(event.target.value))}
                  />

                  <div className="replay-buckets">
                    {replayBuckets.map((bucket, idx) => {
                      const dominant = bucket.dominant_category || 'notable'
                      return (
                        <button
                          key={`${bucket.index}-${bucket.bucket_start}`}
                          type="button"
                          className={`replay-bucket category-${dominant} ${idx === replayIndex ? 'active' : ''}`}
                          style={{ height: `${Math.max(14, Math.min(72, Number(bucket.event_count || 0) * 8))}px` }}
                          onClick={() => setReplayIndex(idx)}
                          title={`${bucket.label} · ${bucket.event_count} events`}
                        />
                      )
                    })}
                  </div>

                  <div className="replay-focus-layout">
                    <div className="replay-main">
                      <div className="replay-grid">
                        <div>
                          <h4>Events In This Slice</h4>
                          {replayBucketEvents.length === 0 ? (
                            <div className="empty-state compact">No replay-visible events in this slice.</div>
                          ) : (
                            <div className="plot-turns-panel">
                              {replayBucketEvents.map((turn) => {
                                const turnRunId = getTurnRunId(turn)
                                const tier = getMomentTier(turn)
                                const isFocused = requestedEventId > 0 && Number(turn.event_id) === requestedEventId
                                const isSelected = Number(turn?.event_id || 0) === Number(activeReplayMoment?.event_id || 0)
                                return (
                                  <div
                                    key={`slice-${turn.event_id}`}
                                    className={`plot-turn-card category-${turn.category || 'notable'} tier-${tier} ${isFocused ? 'focused' : ''} ${isSelected ? 'selected' : ''}`}
                                  >
                                    <div className="plot-turn-row">
                                      <h3>
                                        {turn.title}
                                        <span className={`moment-tier-badge ${tier}`}>{tier === 'major' ? 'Major Moment' : 'Minor Moment'}</span>
                                      </h3>
                                      <span className="plot-turn-salience">Signal {turn.salience}</span>
                                    </div>
                                    <p>{turn.description}</p>
                                    <div className="plot-turn-meta">
                                      <span>{(turn.category || 'notable').replace(/_/g, ' ')}</span>
                                      <span>
                                        {turn.created_at
                                          ? formatDistanceToNow(new Date(turn.created_at), { addSuffix: true })
                                          : ''}
                                      </span>
                                      {turnRunId && (
                                        <Link to={`/runs/${encodeURIComponent(turnRunId)}`} className="plot-turn-run-link">
                                          Run {turnRunId}
                                        </Link>
                                      )}
                                      <button
                                        type="button"
                                        className="moment-focus-btn"
                                        onClick={() => setSelectedReplayEventId(Number(turn?.event_id || 0))}
                                      >
                                        Focus
                                      </button>
                                      <button type="button" className="moment-share-btn" onClick={() => shareMoment(turn, 'highlights_replay_slice')}>
                                        <Share2 size={12} />
                                        Share this moment
                                      </button>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>

                        <div>
                          <h4>Latest Up To This Point</h4>
                          {replayRecent.length === 0 ? (
                            <div className="empty-state compact">No events yet.</div>
                          ) : (
                            <div className="replay-recent-list">
                              {replayRecent.map((turn) => {
                                const isSelected = Number(turn?.event_id || 0) === Number(activeReplayMoment?.event_id || 0)
                                return (
                                  <div
                                    key={`recent-${turn.event_id}`}
                                    className={`replay-recent-item category-${turn.category || 'notable'} ${isSelected ? 'focused' : ''}`}
                                  >
                                    <button
                                      type="button"
                                      className="replay-recent-focus"
                                      onClick={() => setSelectedReplayEventId(Number(turn?.event_id || 0))}
                                    >
                                      <span>{turn.title}</span>
                                      <strong>{turn.salience}</strong>
                                      <em>Focus</em>
                                    </button>
                                    <button type="button" className="moment-share-btn" onClick={() => shareMoment(turn, 'highlights_replay_recent')}>
                                      <Share2 size={12} />
                                      Share
                                    </button>
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <aside className="why-panel">
                      <h4>Why this matters</h4>
                      {!activeReplayMoment ? (
                        <div className="empty-state compact">Select a moment to inspect impact and evidence.</div>
                      ) : (
                        <>
                          <p className="why-title">{activeReplayMoment.title}</p>
                          <p className="why-copy">{getWhyThisMatters(activeReplayMoment)}</p>
                          {activeReplayMomentDeltas.length > 0 && (
                            <div className="delta-chip-row">
                              {activeReplayMomentDeltas.map((delta) => (
                                <span key={`${delta.label}-${delta.value}`} className={`delta-chip tone-${delta.tone || 'neutral'}`}>
                                  <strong>{delta.label}</strong>
                                  <em>{delta.value}</em>
                                </span>
                              ))}
                            </div>
                          )}
                          <div className="why-evidence">
                            {activeReplayEvidence.runDetailHref ? (
                              <Link to={activeReplayEvidence.runDetailHref}>Run Detail Evidence</Link>
                            ) : (
                              <span className="why-missing">Run evidence unavailable.</span>
                            )}
                            {activeReplayEvidence.evidenceApiHref && (
                              <a href={activeReplayEvidence.evidenceApiHref} target="_blank" rel="noreferrer">
                                Raw Evidence API
                              </a>
                            )}
                          </div>
                          <button type="button" className="why-source-toggle" onClick={() => setShowSourceDetail((prev) => !prev)}>
                            {showSourceDetail ? 'Hide source detail' : 'Show source detail'}
                          </button>
                          {showSourceDetail && (
                            <pre className="why-source-detail">
                              {JSON.stringify(activeReplayMoment.metadata || {}, null, 2)}
                            </pre>
                          )}
                        </>
                      )}
                    </aside>
                  </div>
                </>
              ) : (
                <div className="replay-focus-layout">
                  <div className="replay-main">
                    <div className="replay-header">
                      <h3>Replay in 60 Seconds</h3>
                      <span>
                        {replayStoryMoments.length} curated moments · chaptered narrative · about one minute to scan
                      </span>
                    </div>
                    <div className="replay-source-note">
                      <strong>Curated story</strong>
                      <span>Selected from high-salience plot turns, not full event playback.</span>
                    </div>

                    {replayStoryMoments.length === 0 || !activeStoryMoment ? (
                      <div className="empty-state compact">No curated moments available yet.</div>
                    ) : (
                      <>
                        <div className="story-chapter-strip">
                          {replayStoryChapters.map((chapter) => {
                            const isActive = chapter.label === activeStoryMoment.chapter
                            return (
                              <button
                                key={`chapter-${chapter.label}`}
                                type="button"
                                className={`story-chapter-item ${isActive ? 'active' : ''}`}
                                onClick={() => {
                                  const nextIndex = replayStoryMoments.findIndex(
                                    (turn) => Number(turn?.event_id || 0) === Number(chapter.lead_event_id || 0)
                                  )
                                  if (nextIndex >= 0) {
                                    setStoryMomentIndex(nextIndex)
                                    setSelectedReplayEventId(Number(replayStoryMoments[nextIndex]?.event_id || 0))
                                  }
                                }}
                              >
                                <span>{chapter.label}</span>
                                <strong>{chapter.count} moment{chapter.count === 1 ? '' : 's'}</strong>
                                {chapter.description && <em>{chapter.description}</em>}
                              </button>
                            )
                          })}
                        </div>

                        <div className="story60-controls">
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => {
                              const nextIndex = Math.max(0, storyMomentIndex - 1)
                              setStoryMomentIndex(nextIndex)
                              setSelectedReplayEventId(Number(replayStoryMoments[nextIndex]?.event_id || 0))
                            }}
                            disabled={storyMomentIndex <= 0}
                          >
                            Previous
                          </button>
                          <span>
                            Moment {storyMomentIndex + 1}/{replayStoryMoments.length} · {activeStoryMoment.chapter}
                          </span>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => {
                              const nextIndex = Math.min(replayStoryMoments.length - 1, storyMomentIndex + 1)
                              setStoryMomentIndex(nextIndex)
                              setSelectedReplayEventId(Number(replayStoryMoments[nextIndex]?.event_id || 0))
                            }}
                            disabled={storyMomentIndex >= replayStoryMoments.length - 1}
                          >
                            Next
                          </button>
                        </div>

                        <div
                          className={`plot-turn-card story60-card category-${activeStoryMoment.category || 'notable'} tier-${getMomentTier(activeStoryMoment)}`}
                        >
                          <div className="plot-turn-row">
                            <h3>
                              {activeStoryMoment.title}
                              <span className="story-chapter-badge">{activeStoryMoment.chapter}</span>
                            </h3>
                            <span className="plot-turn-salience">Signal {activeStoryMoment.salience}</span>
                          </div>
                          <p>{activeStoryMoment.description}</p>
                          {activeStoryMoment.chapter_description && (
                            <p className="story60-chapter-copy">{activeStoryMoment.chapter_description}</p>
                          )}
                          <div className="plot-turn-meta">
                            <span>{(activeStoryMoment.category || 'notable').replace(/_/g, ' ')}</span>
                            <span>
                              {activeStoryMoment.created_at
                                ? formatDistanceToNow(new Date(activeStoryMoment.created_at), { addSuffix: true })
                                : ''}
                            </span>
                            {getTurnRunId(activeStoryMoment) && (
                              <Link to={`/runs/${encodeURIComponent(getTurnRunId(activeStoryMoment))}`} className="plot-turn-run-link">
                                Run {getTurnRunId(activeStoryMoment)}
                              </Link>
                            )}
                            <button type="button" className="moment-share-btn" onClick={() => shareMoment(activeStoryMoment, 'highlights_replay_story60')}>
                              <Share2 size={12} />
                              Share this moment
                            </button>
                          </div>
                          {activeStoryMoment.deltas?.length > 0 && (
                            <div className="delta-chip-row">
                              {activeStoryMoment.deltas.map((delta) => (
                                <span key={`${delta.label}-${delta.value}`} className={`delta-chip tone-${delta.tone || 'neutral'}`}>
                                  <strong>{delta.label}</strong>
                                  <em>{delta.value}</em>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        <div className="story-moment-list">
                          {replayStoryMoments.map((turn, index) => (
                            <button
                              key={`story-${turn.event_id}`}
                              type="button"
                              className={`story-moment-item category-${turn.category || 'notable'} ${index === storyMomentIndex ? 'active' : ''}`}
                              onClick={() => {
                                setStoryMomentIndex(index)
                                setSelectedReplayEventId(Number(turn?.event_id || 0))
                              }}
                            >
                              <span>{turn.chapter}</span>
                              <strong>{turn.title}</strong>
                              <em>Signal {turn.salience}</em>
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>

                  <aside className="why-panel">
                    <h4>Why this matters</h4>
                    {!activeReplayMoment ? (
                      <div className="empty-state compact">Select a moment to inspect impact and evidence.</div>
                    ) : (
                      <>
                        {activeReplayMoment.chapter && (
                          <span className="why-chapter-kicker">{activeReplayMoment.chapter}</span>
                        )}
                        <p className="why-title">{activeReplayMoment.title}</p>
                        <p className="why-copy">{activeStoryMoment?.why_this_matters || getWhyThisMatters(activeReplayMoment)}</p>
                        {activeReplayMomentDeltas.length > 0 && (
                          <div className="delta-chip-row">
                            {activeReplayMomentDeltas.map((delta) => (
                              <span key={`${delta.label}-${delta.value}`} className={`delta-chip tone-${delta.tone || 'neutral'}`}>
                                <strong>{delta.label}</strong>
                                <em>{delta.value}</em>
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="why-evidence">
                          {activeReplayEvidence.runDetailHref ? (
                            <Link to={activeReplayEvidence.runDetailHref}>Run Detail Evidence</Link>
                          ) : (
                            <span className="why-missing">Run evidence unavailable.</span>
                          )}
                          {activeReplayEvidence.evidenceApiHref && (
                            <a href={activeReplayEvidence.evidenceApiHref} target="_blank" rel="noreferrer">
                              Raw Evidence API
                            </a>
                          )}
                        </div>
                        <button type="button" className="why-source-toggle" onClick={() => setShowSourceDetail((prev) => !prev)}>
                          {showSourceDetail ? 'Hide source detail' : 'Show source detail'}
                        </button>
                        {showSourceDetail && (
                          <pre className="why-source-detail">
                            {JSON.stringify(activeReplayMoment.metadata || {}, null, 2)}
                          </pre>
                        )}
                      </>
                    )}
                  </aside>
                </div>
              )}
            </>
          )}
        </div>
      )}

      <style>{`
        .highlight-tabs {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-xl);
        }

        .tab-btn {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm) var(--spacing-lg);
          background: var(--bg-tertiary);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 0.875rem;
          cursor: pointer;
          transition: all var(--transition-fast);
        }

        .tab-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .tab-btn.active {
          background: var(--gradient-primary);
          color: white;
          border-color: transparent;
        }

        .state-strip {
          position: sticky;
          top: -1px;
          z-index: 12;
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-lg);
          padding: var(--spacing-sm);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          background: rgba(6, 6, 10, 0.92);
          backdrop-filter: blur(12px);
        }

        .state-item {
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
          padding: 0.35rem 0.55rem;
          border-radius: var(--radius-md);
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .state-item span {
          color: var(--text-muted);
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .state-item strong {
          font-size: 0.92rem;
          display: inline-flex;
          align-items: center;
          gap: 0.3rem;
        }

        .state-item.trend.up strong {
          color: #86efac;
        }

        .state-item.trend.down strong {
          color: #fca5a5;
        }

        .featured-events {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .featured-intro {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }

        .featured-intro h3 {
          margin-bottom: 0.35rem;
        }

        .featured-intro p {
          margin: 0;
          color: var(--text-secondary);
        }

        .featured-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
          transition: all var(--transition-fast);
        }

        .featured-card:hover {
          transform: translateY(-2px);
          box-shadow: var(--shadow-lg);
        }

        .featured-card.color-gold { border-left: 4px solid #f59e0b; }
        .featured-card.color-purple { border-left: 4px solid #8b5cf6; }
        .featured-card.color-blue { border-left: 4px solid #3b82f6; }
        .featured-card.color-green { border-left: 4px solid #10b981; }
        .featured-card.color-gray { border-left: 4px solid #6b7280; }

        .featured-header {
          display: flex;
          align-items: center;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-md);
        }

        .featured-icon {
          width: 40px;
          height: 40px;
          border-radius: var(--radius-md);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .featured-icon.gold { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
        .featured-icon.purple { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
        .featured-icon.blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
        .featured-icon.green { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .featured-icon.gray { background: rgba(107, 114, 128, 0.15); color: #6b7280; }

        .featured-meta {
          flex: 1;
        }

        .featured-type {
          display: block;
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--text-muted);
          letter-spacing: 0.05em;
        }

        .featured-time {
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .importance-badge {
          padding: 0.25rem 0.75rem;
          border-radius: var(--radius-full);
          font-size: 0.75rem;
          font-weight: 600;
        }

        .importance-badge.gold { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
        .importance-badge.purple { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
        .importance-badge.blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
        .importance-badge.green { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .importance-badge.gray { background: rgba(107, 114, 128, 0.15); color: #6b7280; }

        .featured-title {
          font-size: 1.25rem;
          margin-bottom: var(--spacing-sm);
        }

        .featured-description {
          color: var(--text-secondary);
          line-height: 1.6;
        }

        .featured-actions {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          margin-top: var(--spacing-md);
          flex-wrap: wrap;
        }

        .summary-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          overflow: hidden;
        }

        .summary-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          background: var(--bg-tertiary);
        }

        .summary-header h2 {
          font-size: 1.25rem;
        }

        .summary-date {
          color: var(--text-muted);
          font-size: 0.875rem;
        }

        .summary-stats {
          display: flex;
          gap: var(--spacing-lg);
          padding: var(--spacing-lg);
          border-bottom: 1px solid var(--border-color);
          flex-wrap: wrap;
        }

        .summary-stat {
          text-align: center;
          min-width: 60px;
        }

        .summary-stat .stat-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--accent-blue);
        }

        .summary-stat .stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .summary-content {
          padding: var(--spacing-lg);
        }

        .summary-content p {
          color: var(--text-secondary);
          line-height: 1.8;
          margin-bottom: var(--spacing-md);
        }

        .summary-content p:last-child {
          margin-bottom: 0;
        }

        .plot-turns-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .plot-turn-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-left-width: 4px;
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }

        .plot-turn-card.tier-major {
          box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.09);
        }

        .plot-turn-card.tier-minor {
          opacity: 0.92;
        }

        .plot-turn-card.focused {
          outline: 1px solid rgba(255, 255, 255, 0.35);
        }

        .plot-turn-card.category-crisis { border-left-color: #f97316; }
        .plot-turn-card.category-conflict { border-left-color: #ef4444; }
        .plot-turn-card.category-alliance { border-left-color: #3b82f6; }
        .plot-turn-card.category-governance { border-left-color: #a78bfa; }
        .plot-turn-card.category-cooperation { border-left-color: #22c55e; }
        .plot-turn-card.category-notable { border-left-color: #94a3b8; }

        .plot-turn-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-md);
          margin-bottom: var(--spacing-xs);
        }

        .plot-turn-row h3 {
          margin: 0;
          font-size: 1.1rem;
          display: flex;
          align-items: center;
          gap: 0.45rem;
          flex-wrap: wrap;
        }

        .plot-turn-salience {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .plot-turn-card p {
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.55;
        }

        .plot-turn-meta {
          margin-top: var(--spacing-sm);
          display: flex;
          flex-wrap: wrap;
          color: var(--text-muted);
          font-size: 0.78rem;
          text-transform: capitalize;
          gap: var(--spacing-sm);
        }

        .plot-turn-run-link {
          border: 1px solid var(--border-color);
          border-radius: var(--radius-full);
          padding: 0.12rem 0.55rem;
          font-size: 0.74rem;
          color: var(--text-secondary);
          text-transform: none;
        }

        .plot-turn-run-link:hover {
          color: var(--text-primary);
          border-color: var(--border-light);
        }

        .moment-tier-badge {
          font-size: 0.66rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          border: 1px solid transparent;
          border-radius: var(--radius-full);
          padding: 0.14rem 0.45rem;
        }

        .moment-tier-badge.major {
          background: rgba(255, 255, 255, 0.12);
          border-color: rgba(255, 255, 255, 0.25);
          color: var(--text-primary);
        }

        .moment-tier-badge.minor {
          background: rgba(255, 255, 255, 0.05);
          border-color: rgba(255, 255, 255, 0.1);
          color: var(--text-secondary);
        }

        .moment-share-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.28rem;
          border: 1px solid var(--border-color);
          border-radius: var(--radius-full);
          padding: 0.14rem 0.5rem;
          background: rgba(255, 255, 255, 0.03);
          color: var(--text-secondary);
          font-size: 0.72rem;
          cursor: pointer;
        }

        .moment-share-btn:hover {
          color: var(--text-primary);
          border-color: var(--border-light);
        }

        .prediction-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .prediction-intro-card {
          padding: var(--spacing-lg);
          border-radius: var(--radius-lg);
          background: rgba(255, 255, 255, 0.025);
          border: 1px solid var(--border-color);
        }

        .prediction-intro-card strong {
          display: block;
          margin-bottom: 0.35rem;
        }

        .prediction-intro-card p {
          margin: 0;
          color: var(--text-secondary);
          line-height: 1.55;
        }

        .prediction-stats {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: var(--spacing-sm);
        }

        .prediction-stats div {
          border: 1px solid var(--border-color);
          background: var(--bg-card);
          border-radius: var(--radius-md);
          padding: var(--spacing-sm) var(--spacing-md);
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-sm);
        }

        .prediction-stats span {
          color: var(--text-muted);
          font-size: 0.8rem;
        }

        .prediction-card {
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          padding: var(--spacing-lg);
        }

        .prediction-row {
          display: flex;
          justify-content: space-between;
          gap: var(--spacing-sm);
          align-items: flex-start;
          margin-bottom: var(--spacing-xs);
        }

        .prediction-title-wrap {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }

        .prediction-row h3 {
          margin: 0;
          font-size: 1rem;
        }

        .prediction-live-chip {
          display: inline-flex;
          align-items: center;
          width: fit-content;
          padding: 0.2rem 0.55rem;
          border-radius: 999px;
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .prediction-close {
          color: var(--text-muted);
          font-size: 0.78rem;
          white-space: nowrap;
        }

        .prediction-card p {
          margin: 0;
          color: var(--text-secondary);
          font-size: 0.9rem;
        }

        .prediction-copy-block {
          display: grid;
          gap: 0.3rem;
          margin-top: var(--spacing-sm);
        }

        .prediction-copy-block span {
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-muted);
        }

        .prediction-copy-block strong {
          font-size: 0.9rem;
          line-height: 1.5;
          color: var(--text-primary);
        }

        .prediction-links {
          display: flex;
          gap: var(--spacing-md);
          flex-wrap: wrap;
          margin-top: var(--spacing-sm);
        }

        .prediction-links a {
          color: var(--text-muted);
          text-decoration: none;
          font-size: 0.82rem;
        }

        .prediction-links a:hover {
          color: var(--text-primary);
        }

        .prediction-probability {
          margin-top: var(--spacing-md);
          display: flex;
          border-radius: var(--radius-md);
          overflow: hidden;
          min-height: 34px;
          background: rgba(255, 255, 255, 0.06);
        }

        .prediction-yes,
        .prediction-no {
          display: flex;
          align-items: center;
          font-size: 0.78rem;
          font-weight: 600;
          white-space: nowrap;
          padding: 0 var(--spacing-sm);
        }

        .prediction-yes {
          justify-content: flex-start;
          color: #86efac;
          background: rgba(34, 197, 94, 0.2);
        }

        .prediction-no {
          justify-content: flex-end;
          color: #fca5a5;
          background: rgba(239, 68, 68, 0.2);
        }

        .prediction-actions {
          margin-top: var(--spacing-md);
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
        }

        .feed-notice.success {
          border-color: rgba(34, 197, 94, 0.35);
          background: rgba(34, 197, 94, 0.12);
          color: #86efac;
        }

        .feed-notice.error {
          border-color: rgba(239, 68, 68, 0.35);
          background: rgba(239, 68, 68, 0.12);
          color: #fca5a5;
        }

        .replay-panel {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .replay-intro-card {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: var(--spacing-md);
          padding: var(--spacing-md);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: var(--radius-lg);
          background:
            radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 45%),
            rgba(255, 255, 255, 0.03);
        }

        .replay-intro-card strong {
          display: block;
          margin-bottom: 0.35rem;
          font-size: 0.96rem;
          color: var(--text-primary);
        }

        .replay-intro-card p {
          margin: 0;
          max-width: 44rem;
          color: var(--text-secondary);
          font-size: 0.86rem;
          line-height: 1.5;
        }

        .replay-intro-card span {
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: var(--radius-full);
          padding: 0.25rem 0.7rem;
          color: #bfdbfe;
          font-size: 0.72rem;
          white-space: nowrap;
        }

        .replay-mode-toggle {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
        }

        .replay-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-md);
          color: var(--text-secondary);
          font-size: 0.85rem;
        }

        .replay-header h3 {
          margin: 0;
          font-size: 1rem;
          color: var(--text-primary);
        }

        .replay-source-note {
          display: flex;
          flex-wrap: wrap;
          gap: 0.75rem;
          align-items: center;
          margin: 0 0 1rem;
          color: var(--text-secondary);
          font-size: 0.82rem;
        }

        .replay-source-note strong {
          color: var(--text-primary);
          font-weight: 700;
        }

        .replay-source-note em {
          font-style: normal;
          color: #cbd5e1;
        }

        .replay-buckets {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(10px, 1fr));
          align-items: end;
          gap: 2px;
          min-height: 76px;
        }

        .replay-bucket {
          width: 100%;
          min-height: 8px;
          border: 0;
          border-radius: 4px;
          opacity: 0.55;
          cursor: pointer;
          transition: opacity var(--transition-fast), transform var(--transition-fast);
        }

        .replay-bucket.active {
          opacity: 1;
          transform: translateY(-2px);
        }

        .replay-bucket.category-crisis { background: #f97316; }
        .replay-bucket.category-conflict { background: #ef4444; }
        .replay-bucket.category-alliance { background: #3b82f6; }
        .replay-bucket.category-governance { background: #a78bfa; }
        .replay-bucket.category-cooperation { background: #22c55e; }
        .replay-bucket.category-notable { background: #94a3b8; }

        .replay-focus-layout {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
          gap: var(--spacing-lg);
          align-items: start;
        }

        .replay-main {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-md);
        }

        .replay-grid {
          display: grid;
          grid-template-columns: 2fr 1fr;
          gap: var(--spacing-lg);
        }

        .replay-grid h4 {
          margin: 0 0 var(--spacing-sm) 0;
        }

        .replay-recent-list {
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
        }

        .replay-recent-item {
          width: 100%;
          display: flex;
          justify-content: space-between;
          gap: var(--spacing-sm);
          align-items: center;
          border: 1px solid var(--border-color);
          border-left-width: 4px;
          border-radius: var(--radius-md);
          padding: var(--spacing-sm);
          background: var(--bg-card);
          color: var(--text-primary);
          text-align: left;
        }

        .replay-recent-focus {
          flex: 1;
          min-width: 0;
          border: 0;
          background: transparent;
          color: inherit;
          text-align: left;
          display: grid;
          gap: 0.2rem;
          padding: 0;
          cursor: pointer;
        }

        .replay-recent-item span {
          font-size: 0.85rem;
          color: var(--text-secondary);
        }

        .replay-recent-item strong {
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .replay-recent-item em {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          font-size: 0.7rem;
          color: var(--text-muted);
          font-style: normal;
        }

        .replay-recent-item.focused {
          outline: 1px solid rgba(255, 255, 255, 0.3);
        }

        .replay-recent-item.category-crisis { border-left-color: #f97316; }
        .replay-recent-item.category-conflict { border-left-color: #ef4444; }
        .replay-recent-item.category-alliance { border-left-color: #3b82f6; }
        .replay-recent-item.category-governance { border-left-color: #a78bfa; }
        .replay-recent-item.category-cooperation { border-left-color: #22c55e; }
        .replay-recent-item.category-notable { border-left-color: #94a3b8; }

        .plot-turn-card.selected {
          outline: 1px solid rgba(59, 130, 246, 0.45);
        }

        .moment-focus-btn {
          border: 1px solid var(--border-color);
          border-radius: var(--radius-full);
          padding: 0.14rem 0.5rem;
          background: rgba(59, 130, 246, 0.12);
          color: #93c5fd;
          font-size: 0.72rem;
          cursor: pointer;
        }

        .moment-focus-btn:hover {
          border-color: #3b82f6;
          color: #bfdbfe;
        }

        .story60-controls {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--spacing-sm);
          padding: var(--spacing-sm);
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          background: rgba(255, 255, 255, 0.03);
          color: var(--text-secondary);
          font-size: 0.82rem;
        }

        .story-chapter-strip {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
          gap: var(--spacing-sm);
        }

        .story-chapter-item {
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: var(--radius-md);
          background: rgba(255, 255, 255, 0.03);
          color: var(--text-primary);
          text-align: left;
          padding: var(--spacing-sm);
          display: grid;
          gap: 0.22rem;
          cursor: pointer;
        }

        .story-chapter-item span {
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--text-muted);
        }

        .story-chapter-item strong {
          font-size: 0.86rem;
        }

        .story-chapter-item em {
          font-size: 0.75rem;
          line-height: 1.4;
          color: var(--text-secondary);
          font-style: normal;
        }

        .story-chapter-item.active {
          border-color: rgba(96, 165, 250, 0.4);
          background: rgba(59, 130, 246, 0.12);
        }

        .story60-card {
          margin: 0;
        }

        .story60-chapter-copy {
          margin: 0;
          color: var(--text-secondary);
          font-size: 0.82rem;
          line-height: 1.45;
        }

        .story-chapter-badge {
          font-size: 0.66rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          border: 1px solid rgba(255, 255, 255, 0.25);
          border-radius: var(--radius-full);
          padding: 0.16rem 0.5rem;
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.08);
        }

        .story-moment-list {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: var(--spacing-sm);
        }

        .story-moment-item {
          border: 1px solid var(--border-color);
          border-left-width: 4px;
          border-radius: var(--radius-md);
          background: var(--bg-card);
          color: var(--text-primary);
          text-align: left;
          padding: var(--spacing-sm);
          display: grid;
          gap: 0.25rem;
          cursor: pointer;
        }

        .story-moment-item span {
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--text-muted);
        }

        .story-moment-item strong {
          font-size: 0.86rem;
          line-height: 1.3;
        }

        .story-moment-item em {
          font-size: 0.72rem;
          color: var(--text-muted);
          font-style: normal;
        }

        .story-moment-item.active {
          outline: 1px solid rgba(255, 255, 255, 0.28);
          background: rgba(255, 255, 255, 0.06);
        }

        .story-moment-item.category-crisis { border-left-color: #f97316; }
        .story-moment-item.category-conflict { border-left-color: #ef4444; }
        .story-moment-item.category-alliance { border-left-color: #3b82f6; }
        .story-moment-item.category-governance { border-left-color: #a78bfa; }
        .story-moment-item.category-cooperation { border-left-color: #22c55e; }
        .story-moment-item.category-notable { border-left-color: #94a3b8; }

        .why-panel {
          position: sticky;
          top: 76px;
          border: 1px solid var(--border-color);
          border-radius: var(--radius-lg);
          background: var(--bg-card);
          padding: var(--spacing-md);
          display: flex;
          flex-direction: column;
          gap: var(--spacing-sm);
          min-height: 220px;
        }

        .why-panel h4 {
          margin: 0;
        }

        .why-title {
          margin: 0;
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .why-chapter-kicker {
          display: inline-flex;
          align-self: flex-start;
          border-radius: var(--radius-full);
          border: 1px solid rgba(255, 255, 255, 0.12);
          padding: 0.18rem 0.55rem;
          color: #bfdbfe;
          font-size: 0.68rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .why-copy {
          margin: 0;
          color: var(--text-secondary);
          font-size: 0.88rem;
          line-height: 1.5;
        }

        .why-evidence {
          display: flex;
          flex-wrap: wrap;
          gap: var(--spacing-sm);
          margin-top: 0.15rem;
        }

        .why-evidence a,
        .why-evidence .why-missing {
          font-size: 0.78rem;
          border: 1px solid var(--border-color);
          border-radius: var(--radius-full);
          padding: 0.16rem 0.58rem;
          color: var(--text-secondary);
        }

        .why-evidence a:hover {
          color: var(--text-primary);
          border-color: var(--border-light);
        }

        .why-source-toggle {
          border: 1px solid var(--border-color);
          border-radius: var(--radius-md);
          padding: 0.35rem 0.55rem;
          background: rgba(255, 255, 255, 0.03);
          color: var(--text-secondary);
          font-size: 0.78rem;
          cursor: pointer;
          text-align: left;
        }

        .why-source-toggle:hover {
          color: var(--text-primary);
        }

        .why-source-detail {
          margin: 0;
          padding: var(--spacing-sm);
          border-radius: var(--radius-md);
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #c7d2fe;
          font-size: 0.72rem;
          line-height: 1.45;
          max-height: 180px;
          overflow: auto;
        }

        .delta-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.4rem;
          margin-top: var(--spacing-sm);
        }

        .delta-chip {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          border-radius: var(--radius-full);
          padding: 0.18rem 0.56rem;
          border: 1px solid rgba(255, 255, 255, 0.14);
          font-size: 0.72rem;
          background: rgba(255, 255, 255, 0.04);
        }

        .delta-chip strong {
          font-weight: 600;
          color: var(--text-primary);
        }

        .delta-chip em {
          color: var(--text-muted);
          font-style: normal;
        }

        .delta-chip.tone-up {
          border-color: rgba(34, 197, 94, 0.35);
          background: rgba(34, 197, 94, 0.14);
        }

        .delta-chip.tone-down {
          border-color: rgba(239, 68, 68, 0.35);
          background: rgba(239, 68, 68, 0.14);
        }

        .delta-chip.tone-alert {
          border-color: rgba(249, 115, 22, 0.4);
          background: rgba(249, 115, 22, 0.14);
        }

        .empty-state.compact {
          min-height: 0;
          padding: var(--spacing-md);
          border: 1px dashed rgba(255, 255, 255, 0.12);
          border-radius: var(--radius-md);
          color: var(--text-muted);
        }

        @media (max-width: 900px) {
          .replay-grid {
            grid-template-columns: 1fr;
          }

          .replay-focus-layout {
            grid-template-columns: 1fr;
          }

          .replay-intro-card {
            flex-direction: column;
          }

          .why-panel {
            position: static;
          }

          .state-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 640px) {
          .prediction-stats {
            grid-template-columns: 1fr;
          }

          .prediction-actions {
            flex-direction: column;
          }

          .prediction-actions .btn {
            width: 100%;
          }
        }
      `}</style>
    </div>
  )
}
