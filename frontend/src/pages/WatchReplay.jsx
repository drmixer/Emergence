import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CircleX,
  Eye,
  FileSearch,
  Handshake,
  Hash,
  Map as MapIcon,
  Newspaper,
  Radio,
  Scale,
  ShieldAlert,
  TimerReset,
  Users,
} from 'lucide-react'
import { api } from '../services/api'
import { getScheduleEntryForRunId } from '../data/runSchedule'
import { trackKpiEvent, trackKpiEventOnce } from '../services/kpiAnalytics'

const ROUTINE_EVENT_TYPES = new Set(['work', 'idle', 'vote', 'processing_error'])
const TIMELINE_BUCKET_COUNT = 18

const LANE_ORDER = ['survival', 'governance', 'aid_trade', 'public_order', 'system']

const LANE_META = {
  survival: {
    label: 'Survival',
    icon: Users,
    description: 'Death, dormancy, revival, and other population-state pressure.',
  },
  governance: {
    label: 'Governance',
    icon: Scale,
    description: 'Proposals, votes, resolved decisions, and passed laws.',
  },
  aid_trade: {
    label: 'Aid / Trade',
    icon: Handshake,
    description: 'Aid requests, refusals, trades, and resource coordination.',
  },
  public_order: {
    label: 'Public Order',
    icon: ShieldAlert,
    description: 'Accusations, enforcement, sanctions, seizures, exile, and conflict.',
  },
  system: {
    label: 'System Shocks',
    icon: AlertTriangle,
    description: 'Run-wide shocks or crisis events that changed the board.',
  },
  other: {
    label: 'Other Signals',
    icon: Activity,
    description: 'Other non-routine moments with enough signal to inspect.',
  },
}

function cleanString(value) {
  return String(value || '').trim()
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString()
}

function formatTimestamp(value) {
  if (!value) return 'Unknown time'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown time'
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatTimeOnly(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function formatDurationLabel(start, end) {
  const startMs = Date.parse(start || '')
  const endMs = Date.parse(end || '')
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return 'Completed run'
  const hours = (endMs - startMs) / (1000 * 60 * 60)
  if (hours >= 24) return `${hours.toFixed(1)}h window`
  return `${hours.toFixed(1)}h window`
}

function formatEventTitle(item) {
  return cleanString(item?.title || item?.event_type || 'Run event').replace(/_/g, ' ')
}

function getEventDescription(item) {
  return cleanString(item?.why_this_matters || item?.description || item?.summary)
}

function getEventId(item) {
  return Number(item?.event_id || item?.id || 0)
}

function getEventTime(item) {
  return item?.created_at || item?.timestamp || ''
}

function getReplayHref(runId, eventId = 0) {
  const safeRunId = encodeURIComponent(runId)
  const params = new URLSearchParams()
  params.set('mode', eventId > 0 ? 'timeline' : 'story60')
  if (eventId > 0) params.set('event', String(eventId))
  return `/runs/${safeRunId}/replay?${params.toString()}`
}

function getEvidenceHref(runId, eventId = 0) {
  const safeRunId = encodeURIComponent(runId)
  return `/runs/${safeRunId}${eventId > 0 ? `?event=${encodeURIComponent(String(eventId))}` : ''}`
}

function getBriefHref(runId) {
  return `/runs/${encodeURIComponent(runId)}/reports/viewer_brief?format=markdown`
}

function getEventLane(item) {
  const explicitLane = cleanString(item?.lane)
  if (LANE_META[explicitLane]) return explicitLane
  const eventType = cleanString(item?.event_type)
  const category = cleanString(item?.category)

  if (['agent_died', 'became_dormant', 'agent_revived', 'awakened'].includes(eventType)) return 'survival'
  if (['law_passed', 'proposal_resolved', 'create_proposal', 'vote_enforcement'].includes(eventType) || category === 'governance') return 'governance'
  if (['trade', 'request_aid', 'aid_request_received', 'refuse_aid', 'aid_refusal_received', 'reserve_aid'].includes(eventType)) return 'aid_trade'
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

function normalizeLaneKey(value) {
  const clean = cleanString(value)
  if (LANE_META[clean]) return clean
  return getEventLane({ category: clean })
}

function getLaneFilter(value) {
  const clean = cleanString(value)
  if (!clean || clean === 'all') return ''
  const lane = normalizeLaneKey(clean)
  return LANE_ORDER.includes(lane) ? lane : ''
}

function getWatchFocus(value) {
  const clean = cleanString(value).toLowerCase()
  return clean === 'largest' ? clean : ''
}

function isVisibleMoment(item) {
  if (!item || getEventId(item) <= 0) return false
  const eventType = cleanString(item?.event_type)
  const category = cleanString(item?.category)
  if (ROUTINE_EVENT_TYPES.has(eventType)) return false
  if (['survival', 'governance', 'aid_trade', 'public_order', 'system'].includes(getEventLane(item))) return true
  if (['crisis', 'conflict', 'governance'].includes(category)) return true
  return Number(item?.salience || 0) >= 70
}

function sortByTime(items) {
  return [...items].sort((a, b) => {
    const timeDelta = (Date.parse(getEventTime(a)) || 0) - (Date.parse(getEventTime(b)) || 0)
    if (timeDelta !== 0) return timeDelta
    return getEventId(a) - getEventId(b)
  })
}

function uniqueMoments(items) {
  const seen = new Set()
  return sortByTime(items).filter((item) => {
    const eventId = getEventId(item)
    if (eventId <= 0 || seen.has(eventId)) return false
    seen.add(eventId)
    return true
  })
}

function getRunWindow(runDetail, playback, density) {
  const detailWindow = runDetail?.provenance?.time_window || {}
  const playbackWindow = playback?.time_window || {}
  const densityBuckets = Array.isArray(density?.buckets) ? density.buckets : []
  const firstBucket = densityBuckets[0]
  const lastBucket = densityBuckets[densityBuckets.length - 1]
  return {
    start: detailWindow.start_utc || playbackWindow.start_utc || firstBucket?.bucket_start || '',
    end: detailWindow.end_utc || playbackWindow.end_utc || lastBucket?.bucket_end || '',
  }
}

function buildFallbackBuckets(moments, window) {
  const startMs = Date.parse(window.start || '')
  const endMs = Date.parse(window.end || '')
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return []
  const bucketMs = (endMs - startMs) / TIMELINE_BUCKET_COUNT
  const buckets = Array.from({ length: TIMELINE_BUCKET_COUNT }, (_, index) => {
    const bucketStart = new Date(startMs + bucketMs * index).toISOString()
    const bucketEnd = new Date(index === TIMELINE_BUCKET_COUNT - 1 ? endMs : startMs + bucketMs * (index + 1)).toISOString()
    return {
      index,
      bucket_start: bucketStart,
      bucket_end: bucketEnd,
      label: formatTimeOnly(bucketStart),
      event_count: 0,
      dominant_category: null,
      category_counts: {},
    }
  })

  moments.forEach((item) => {
    const createdMs = Date.parse(getEventTime(item))
    if (!Number.isFinite(createdMs)) return
    const index = Math.max(0, Math.min(TIMELINE_BUCKET_COUNT - 1, Math.floor((createdMs - startMs) / bucketMs)))
    const bucket = buckets[index]
    const lane = getEventLane(item)
    bucket.event_count += 1
    bucket.category_counts[lane] = Number(bucket.category_counts[lane] || 0) + 1
    bucket.dominant_category = Object.entries(bucket.category_counts)
      .sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0] || null
  })

  return buckets
}

function attachRepresentativeMoments(buckets, moments) {
  return buckets.map((bucket) => {
    const startMs = Date.parse(bucket.bucket_start || '')
    const endMs = Date.parse(bucket.bucket_end || '')
    const candidates = uniqueMoments(moments.filter((item) => {
      const eventMs = Date.parse(getEventTime(item))
      return Number.isFinite(eventMs) && eventMs >= startMs && eventMs <= endMs
    }))
    const representative = candidates
      .sort((a, b) => Number(b?.salience || 0) - Number(a?.salience || 0))[0] || null
    const categoryCounts = candidates.reduce((counts, item) => {
      const lane = getEventLane(item)
      counts[lane] = Number(counts[lane] || 0) + 1
      return counts
    }, {})
    const dominantCategory = Object.entries(categoryCounts)
      .sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0]
      || bucket.dominant_category
      || null
    return {
      ...bucket,
      representative,
      linked_moment_count: candidates.length,
      linked_category_counts: categoryCounts,
      dominant_category: dominantCategory,
    }
  })
}

function buildDensityBuckets(density, moments, window) {
  const apiBuckets = Array.isArray(density?.buckets) ? density.buckets : []
  const sourceBuckets = apiBuckets.length > 0 ? apiBuckets : buildFallbackBuckets(moments, window)
  return attachRepresentativeMoments(sourceBuckets, moments)
}

function getBucketKey(bucket) {
  return `${Number(bucket?.index || 0)}:${cleanString(bucket?.bucket_start)}`
}

function getBucketMomentCount(bucket) {
  if (Number.isFinite(Number(bucket?.display_moment_count))) {
    return Number(bucket.display_moment_count)
  }
  return Number(bucket?.linked_moment_count || 0)
}

function getBucketRepresentativeEventId(bucket) {
  return getEventId(bucket?.display_representative || bucket?.representative)
}

function findLargestSpikeBucket(buckets) {
  return [...buckets]
    .sort((a, b) => {
      const countDelta = getBucketMomentCount(b) - getBucketMomentCount(a)
      if (countDelta !== 0) return countDelta
      const salienceDelta = Number(b?.max_salience || b?.display_representative?.salience || b?.representative?.salience || 0)
        - Number(a?.max_salience || a?.display_representative?.salience || a?.representative?.salience || 0)
      if (salienceDelta !== 0) return salienceDelta
      return Number(a?.index || 0) - Number(b?.index || 0)
    })[0] || null
}

function isMomentInBucket(moment, bucket) {
  if (!moment || !bucket) return false
  const eventMs = Date.parse(getEventTime(moment))
  const startMs = Date.parse(bucket.bucket_start || '')
  const endMs = Date.parse(bucket.bucket_end || '')
  return Number.isFinite(eventMs)
    && Number.isFinite(startMs)
    && Number.isFinite(endMs)
    && eventMs >= startMs
    && eventMs <= endMs
}

function getMomentsInBucket(moments, bucket, laneFilter = '') {
  return uniqueMoments(moments)
    .filter((moment) => isMomentInBucket(moment, bucket))
    .filter((moment) => !laneFilter || getEventLane(moment) === laneFilter)
    .sort((a, b) => {
      const salienceDelta = Number(b?.salience || 0) - Number(a?.salience || 0)
      if (salienceDelta !== 0) return salienceDelta
      return (Date.parse(getEventTime(a)) || 0) - (Date.parse(getEventTime(b)) || 0)
    })
}

function buildDisplayBuckets(buckets, moments, laneFilter = '') {
  return buckets.map((bucket) => {
    const displayMoments = getMomentsInBucket(moments, bucket, laneFilter)
    const displayRepresentative = displayMoments[0] || null
    const displayLane = laneFilter
      || (displayRepresentative ? getEventLane(displayRepresentative) : normalizeLaneKey(bucket.dominant_category))
    return {
      ...bucket,
      display_moment_count: displayMoments.length,
      display_representative: displayRepresentative,
      display_lane: displayLane,
    }
  })
}

function buildSelectedWindow(bucket, moments, focusLane = '') {
  if (!bucket) return null
  const windowMoments = getMomentsInBucket(moments, bucket)
  const focusedMoments = focusLane
    ? windowMoments.filter((moment) => getEventLane(moment) === focusLane)
    : windowMoments
  const laneCounts = windowMoments.reduce((counts, moment) => {
    const lane = getEventLane(moment)
    counts[lane] = Number(counts[lane] || 0) + 1
    return counts
  }, {})
  const dominantLane = Object.entries(laneCounts)
    .sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0]
    || normalizeLaneKey(bucket.dominant_category)

  return {
    key: getBucketKey(bucket),
    bucket,
    start: bucket.bucket_start,
    end: bucket.bucket_end,
    count: focusedMoments.length,
    dominantLane: focusLane || dominantLane,
    laneCounts,
    moments: windowMoments,
    topMoments: focusedMoments.slice(0, 3),
  }
}

function buildLaneRows(moments) {
  const grouped = new Map()
  uniqueMoments(moments).forEach((item) => {
    const lane = getEventLane(item)
    const bucket = grouped.get(lane) || []
    bucket.push(item)
    grouped.set(lane, bucket)
  })

  return [...LANE_ORDER, 'other']
    .map((lane) => {
      const items = grouped.get(lane) || []
      const meta = LANE_META[lane] || LANE_META.other
      return {
        key: lane,
        ...meta,
        count: items.length,
        moments: items,
      }
    })
    .filter((lane) => lane.count > 0 || lane.key !== 'other')
}

function getArchiveRunId(archive) {
  const items = Array.isArray(archive?.items) ? archive.items : []
  return cleanString(items[0]?.run_id)
}

export default function WatchReplay() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedRunId = cleanString(searchParams.get('run'))
  const requestedEventId = Number(searchParams.get('event') || 0)
  const requestedBucketIndex = Number(searchParams.get('bucket') || -1)
  const selectedLaneFilter = getLaneFilter(searchParams.get('lane'))
  const requestedFocus = getWatchFocus(searchParams.get('focus'))
  const [archive, setArchive] = useState(null)
  const [watchData, setWatchData] = useState(null)
  const [archiveLoading, setArchiveLoading] = useState(true)
  const [loading, setLoading] = useState(Boolean(requestedRunId))
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadArchive() {
      setArchiveLoading(true)
      const payload = await api.getRunsArchive(12, false).catch(() => null)
      if (cancelled) return
      setArchive(payload && typeof payload === 'object' ? payload : null)
      setArchiveLoading(false)
    }

    void loadArchive()
    return () => {
      cancelled = true
    }
  }, [])

  const archiveItems = Array.isArray(archive?.items) ? archive.items : []
  const archiveLatestRunId = getArchiveRunId(archive)
  const cleanRunId = requestedRunId || archiveLatestRunId

  useEffect(() => {
    let cancelled = false
    if (!cleanRunId) {
      return () => {
        cancelled = true
      }
    }

    async function loadRun() {
      setLoading(true)
      setError('')
      const payload = await api.getRunWatch(cleanRunId, 60, 240).catch(() => null)
      if (cancelled) return

      setWatchData(payload && typeof payload === 'object' ? payload : null)
      if (!payload || typeof payload !== 'object') {
        setError('Watch replay data could not be loaded.')
      }
      setLoading(false)
    }

    void loadRun()
    return () => {
      cancelled = true
    }
  }, [cleanRunId])

  const runSchedule = getScheduleEntryForRunId(cleanRunId)
  const watchItems = useMemo(() => Array.isArray(watchData?.items) ? watchData.items : [], [watchData])
  const visibleMoments = useMemo(
    () => uniqueMoments(watchItems.filter(isVisibleMoment)),
    [watchItems],
  )
  const window = useMemo(() => getRunWindow(watchData, null, watchData), [watchData])
  const densityBuckets = useMemo(
    () => buildDensityBuckets(watchData, visibleMoments, window),
    [visibleMoments, watchData, window],
  )
  const displayBuckets = useMemo(
    () => buildDisplayBuckets(densityBuckets, visibleMoments, selectedLaneFilter),
    [densityBuckets, selectedLaneFilter, visibleMoments],
  )
  const selectedBucket = useMemo(() => {
    let linkedBucket = null
    if (requestedEventId > 0) {
      const linkedMoment = visibleMoments.find((moment) => getEventId(moment) === requestedEventId)
      if (selectedLaneFilter && linkedMoment && getEventLane(linkedMoment) !== selectedLaneFilter) return null
      linkedBucket = linkedMoment
        ? displayBuckets.find((bucket) => isMomentInBucket(linkedMoment, bucket))
        : null
    } else if (Number.isFinite(requestedBucketIndex) && requestedBucketIndex >= 0) {
      linkedBucket = displayBuckets.find((bucket) => Number(bucket.index) === requestedBucketIndex) || null
    } else if (requestedFocus === 'largest') {
      linkedBucket = findLargestSpikeBucket(displayBuckets.filter((bucket) => getBucketMomentCount(bucket) > 0))
    }
    return linkedBucket && getBucketMomentCount(linkedBucket) > 0 ? linkedBucket : null
  }, [displayBuckets, requestedBucketIndex, requestedEventId, requestedFocus, selectedLaneFilter, visibleMoments])
  const selectedWindow = useMemo(
    () => buildSelectedWindow(selectedBucket, visibleMoments, selectedLaneFilter),
    [selectedBucket, selectedLaneFilter, visibleMoments],
  )
  const spikeBuckets = useMemo(
    () => displayBuckets.filter((bucket) => getBucketMomentCount(bucket) > 0),
    [displayBuckets],
  )
  const selectedSpikeIndex = useMemo(() => {
    if (!selectedWindow) return -1
    return spikeBuckets.findIndex((bucket) => getBucketKey(bucket) === selectedWindow.key)
  }, [selectedWindow, spikeBuckets])
  const largestSpikeBucket = useMemo(() => findLargestSpikeBucket(spikeBuckets), [spikeBuckets])
  const largestSpikeCount = getBucketMomentCount(largestSpikeBucket)
  const laneRows = useMemo(() => buildLaneRows(visibleMoments), [visibleMoments])
  const maxBucketCount = Math.max(1, ...displayBuckets.map((bucket) => getBucketMomentCount(bucket)))
  const activity = watchData?.activity || {}
  const unavailableError = cleanRunId || archiveLoading ? '' : 'No completed public run is available for the watch board.'

  useEffect(() => {
    if (!cleanRunId || loading || error) return
    trackKpiEventOnce('watch_replay_view', `watch_replay:${cleanRunId}`, {
      runId: cleanRunId,
      surface: 'watch_replay',
      target: 'watch_board',
      metadata: {
        visible_moments: visibleMoments.length,
        density_buckets: densityBuckets.length,
        lane_count: laneRows.length,
      },
    })
  }, [cleanRunId, densityBuckets.length, error, laneRows.length, loading, visibleMoments.length])

  function handleRunSelect(event) {
    const nextRunId = cleanString(event.target.value)
    if (nextRunId) {
      setSearchParams({ run: nextRunId })
    }
  }

  function getBaseSearchParams() {
    const params = { run: cleanRunId }
    if (selectedLaneFilter) params.lane = selectedLaneFilter
    return params
  }

  function trackWatchInteraction(eventName, target, metadata = {}, eventId = 0) {
    if (!cleanRunId) return
    trackKpiEvent(eventName, {
      runId: cleanRunId,
      eventId,
      surface: 'watch_replay',
      target,
      metadata: {
        lane_filter: selectedLaneFilter || 'all',
        selected_bucket_index: selectedBucket ? Number(selectedBucket.index) : null,
        selected_spike_index: selectedSpikeIndex >= 0 ? selectedSpikeIndex + 1 : null,
        spike_count: spikeBuckets.length,
        ...metadata,
      },
    })
  }

  function selectBucket(bucket) {
    if (!bucket) return
    const eventId = getBucketRepresentativeEventId(bucket)
    setSearchParams(eventId > 0
      ? { ...getBaseSearchParams(), event: String(eventId) }
      : { ...getBaseSearchParams(), bucket: String(bucket.index) })
  }

  function handleBucketSelect(bucket) {
    const key = getBucketKey(bucket)
    if (selectedWindow?.key === key) {
      setSearchParams(getBaseSearchParams())
      return
    }
    selectBucket(bucket)
  }

  function selectLaneFilter(laneKey) {
    const nextLane = getLaneFilter(laneKey)
    trackWatchInteraction('watch_lane_focus', nextLane || 'all_lanes', {
      previous_lane_filter: selectedLaneFilter || 'all',
      focused_lane: nextLane || 'all',
      focused_moments: nextLane
        ? visibleMoments.filter((moment) => getEventLane(moment) === nextLane).length
        : visibleMoments.length,
    })
    setSearchParams(nextLane ? { run: cleanRunId, lane: nextLane } : { run: cleanRunId })
  }

  function jumpToLargestSpike() {
    if (largestSpikeBucket) {
      trackWatchInteraction('watch_spike_jump', 'largest_spike', {
        bucket_index: Number(largestSpikeBucket.index),
        bucket_start: cleanString(largestSpikeBucket.bucket_start),
        bucket_moment_count: getBucketMomentCount(largestSpikeBucket),
      }, getBucketRepresentativeEventId(largestSpikeBucket))
    }
    selectBucket(largestSpikeBucket)
  }

  function selectAdjacentSpike(direction) {
    if (selectedSpikeIndex < 0) return
    const nextIndex = selectedSpikeIndex + direction
    if (nextIndex < 0 || nextIndex >= spikeBuckets.length) return
    const nextBucket = spikeBuckets[nextIndex]
    trackWatchInteraction('watch_spike_step', direction < 0 ? 'previous_spike' : 'next_spike', {
      from_spike_index: selectedSpikeIndex + 1,
      to_spike_index: nextIndex + 1,
      bucket_index: Number(nextBucket.index),
      bucket_start: cleanString(nextBucket.bucket_start),
      bucket_moment_count: getBucketMomentCount(nextBucket),
    }, getBucketRepresentativeEventId(nextBucket))
    selectBucket(spikeBuckets[nextIndex])
  }

  function clearSelectedWindow() {
    if (cleanRunId) {
      setSearchParams(getBaseSearchParams())
    }
  }

  function trackSelectedMomentClick(target, moment) {
    const eventId = getEventId(moment)
    trackWatchInteraction('watch_selected_moment_click', target, {
      moment_lane: getEventLane(moment),
      moment_title: formatEventTitle(moment),
      bucket_index: selectedBucket ? Number(selectedBucket.index) : null,
      bucket_start: selectedBucket ? cleanString(selectedBucket.bucket_start) : '',
    }, eventId)
  }

  return (
    <div className="watch-page">
      <div className="page-header">
        <h1>
          <Eye size={30} />
          Watch Replay
        </h1>
        <p className="page-description">
          A run-over-time board for finding pressure, decisions, and source links in completed public runs.
        </p>
      </div>

      <div className="run-detail-topbar watch-topbar">
        <div className="run-id-pill">
          <Hash size={15} />
          <span>{cleanRunId || 'latest-completed-run'}</span>
        </div>
        <div className="watch-run-select">
          <label htmlFor="watch-run-select">Completed run</label>
          <select id="watch-run-select" value={cleanRunId} onChange={handleRunSelect}>
            {cleanRunId && <option value={cleanRunId}>{runSchedule?.label ? `${runSchedule.label} · ${cleanRunId}` : cleanRunId}</option>}
            {archiveItems
              .filter((item) => cleanString(item?.run_id) && cleanString(item?.run_id) !== cleanRunId)
              .map((item) => (
                <option key={item.run_id} value={item.run_id}>
                  {item.run_id}
                </option>
              ))}
          </select>
        </div>
        <div className="run-topbar-actions">
          <Link className="btn btn-secondary" to="/archive">Archive</Link>
          {cleanRunId && (
            <>
              <Link className="btn btn-secondary" to={getBriefHref(cleanRunId)}>
                <Newspaper size={14} />
                Brief
              </Link>
              <Link className="btn btn-secondary" to={getReplayHref(cleanRunId)}>
                <TimerReset size={14} />
                Replay
              </Link>
              <Link className="btn btn-secondary" to={getEvidenceHref(cleanRunId)}>
                <FileSearch size={14} />
                Evidence
              </Link>
            </>
          )}
        </div>
      </div>

      <div className="feed-notice">
        Watch is a map of where to look, not a conclusion about what the run means. Use Replay, Evidence, and the Brief for interpretation and source review.
      </div>

      {unavailableError && <div className="feed-notice">{unavailableError}</div>}
      {!cleanRunId && archiveLoading && <div className="empty-state">Loading completed runs...</div>}
      {cleanRunId && loading && <div className="empty-state">Loading watch replay...</div>}
      {cleanRunId && !loading && error && <div className="feed-notice">{error}</div>}

      {cleanRunId && !loading && !error && watchData && (
        <>
          <section className="watch-hero" aria-label="Watch replay run summary">
            <div className="watch-hero-copy">
              <span>{runSchedule?.label || 'Completed run'} · {runSchedule?.track || 'Public run'}</span>
              <h2>{runSchedule?.declaredQuestion || 'Completed run map'}</h2>
              <p>{runSchedule?.claimBoundary || 'Review this board as a navigation surface before drawing conclusions.'}</p>
            </div>
            <div className="watch-window">
              <MapIcon size={18} />
              <div>
                <span>{formatDurationLabel(window.start, window.end)}</span>
                <strong>{formatTimestamp(window.start)} to {formatTimestamp(window.end)}</strong>
              </div>
            </div>
          </section>

          <section className="watch-state-strip" aria-label="Population and state strip">
            {[
              ['Events', formatNumber(activity.total_events), 'Scoped run events'],
              ['Deaths', formatNumber(activity.deaths), `${formatNumber(activity.became_dormant)} dormancy events`],
              ['Laws', formatNumber(activity.laws_passed), `${formatNumber(activity.proposal_actions)} proposal actions`],
              ['Aid / Trade', formatNumber(activity.aid_requests), `${formatNumber(activity.trade_actions)} trades`],
              ['Public Order', formatNumber(activity.public_order_events), `${formatNumber(activity.conflict_events)} conflict signals`],
            ].map(([label, value, detail]) => (
              <div key={label} className="watch-state-item">
                <span>{label}</span>
                <strong>{value}</strong>
                <em>{detail}</em>
              </div>
            ))}
          </section>

          <section className="watch-density" aria-label="Event timeline density">
            <div className="watch-section-head">
              <div>
                <span>Timeline density</span>
                <h3>Where the run got interesting</h3>
              </div>
              <div className="watch-section-actions">
                <p>
                  {densityBuckets.length} buckets · {selectedLaneFilter
                    ? `${spikeBuckets.reduce((sum, bucket) => sum + getBucketMomentCount(bucket), 0)} ${LANE_META[selectedLaneFilter]?.label || 'focused'} moments`
                    : `${visibleMoments.length} linked moments`}
                </p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={jumpToLargestSpike}
                  disabled={!largestSpikeBucket || selectedWindow?.key === getBucketKey(largestSpikeBucket)}
                  aria-label={largestSpikeBucket
                    ? `Jump to largest spike with ${largestSpikeCount} linked moments near ${formatTimeOnly(largestSpikeBucket.bucket_start)}`
                    : 'Jump to largest spike'}
                  title={largestSpikeBucket
                    ? `${largestSpikeCount} linked moment${largestSpikeCount === 1 ? '' : 's'} near ${formatTimeOnly(largestSpikeBucket.bucket_start)}`
                    : 'No linked spikes available'}
                >
                  <BarChart3 size={14} />
                  Jump to largest spike
                </button>
              </div>
            </div>
            <div className="watch-lane-filters" role="group" aria-label="Timeline lane focus">
              <button
                type="button"
                className={`watch-lane-filter ${!selectedLaneFilter ? 'active' : ''}`}
                onClick={() => selectLaneFilter('')}
                aria-pressed={!selectedLaneFilter}
              >
                All lanes
              </button>
              {laneRows
                .filter((lane) => LANE_ORDER.includes(lane.key))
                .map((lane) => {
                  const LaneIcon = lane.icon || Radio
                  return (
                    <button
                      key={lane.key}
                      type="button"
                      className={`watch-lane-filter lane-${lane.key} ${selectedLaneFilter === lane.key ? 'active' : ''}`}
                      onClick={() => selectLaneFilter(lane.key)}
                      aria-pressed={selectedLaneFilter === lane.key}
                      aria-label={`${lane.label} lane, ${formatNumber(lane.count)} linked moments`}
                    >
                      <LaneIcon size={14} />
                      {lane.label}
                      <span>{formatNumber(lane.count)}</span>
                    </button>
                  )
                })}
            </div>
            <div
              className="watch-density-bars"
              style={{ gridTemplateColumns: `repeat(${Math.max(1, displayBuckets.length)}, minmax(10px, 1fr))` }}
            >
              {displayBuckets.map((bucket) => {
                const count = getBucketMomentCount(bucket)
                const representative = bucket.display_representative || bucket.representative
                const lane = bucket.display_lane || (representative
                  ? getEventLane(representative)
                  : normalizeLaneKey(bucket.dominant_category))
                const height = count > 0 ? Math.max(16, Math.round((count / maxBucketCount) * 110)) : 4
                return (
                  <button
                    key={`${bucket.index}-${bucket.bucket_start}`}
                    type="button"
                    className={`watch-density-bar lane-${lane} ${selectedWindow?.key === getBucketKey(bucket) ? 'active' : ''}`}
                    onClick={() => handleBucketSelect(bucket)}
                    aria-pressed={selectedWindow?.key === getBucketKey(bucket)}
                    title={`${count} ${selectedLaneFilter ? `${LANE_META[selectedLaneFilter]?.label || 'focused'} ` : ''}moment${count === 1 ? '' : 's'} near ${formatTimeOnly(bucket.bucket_start)}`}
                    aria-label={`Select ${count} ${selectedLaneFilter ? `${LANE_META[selectedLaneFilter]?.label || 'focused'} ` : ''}event timeline bucket near ${formatTimeOnly(bucket.bucket_start)}`}
                    disabled={count <= 0}
                  >
                    <span style={{ height: `${height}px` }} />
                    <em>{count > 0 ? count : ''}</em>
                  </button>
                )
              })}
            </div>
            <div className="watch-density-axis">
              <span>{formatTimeOnly(window.start)}</span>
              <span>{formatTimeOnly(window.end)}</span>
            </div>
          </section>

          {selectedWindow && (
            <section className="watch-selected-window" aria-label="Selected window">
              <div className="watch-selected-window-head">
                <div>
                  <span>Selected window</span>
                  <strong>{formatTimestamp(selectedWindow.start)} to {formatTimestamp(selectedWindow.end)}</strong>
                  <em>
                    Spike {selectedSpikeIndex >= 0 ? selectedSpikeIndex + 1 : '?'} of {spikeBuckets.length}
                    {selectedLaneFilter ? ` · ${LANE_META[selectedLaneFilter]?.label || 'Focused lane'}` : ''}
                  </em>
                </div>
                <div className="watch-window-controls" role="group" aria-label="Selected spike navigation">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => selectAdjacentSpike(-1)}
                    disabled={selectedSpikeIndex <= 0}
                  >
                    <ArrowLeft size={14} />
                    Previous spike
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => selectAdjacentSpike(1)}
                    disabled={selectedSpikeIndex < 0 || selectedSpikeIndex >= spikeBuckets.length - 1}
                  >
                    <ArrowRight size={14} />
                    Next spike
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={clearSelectedWindow}>
                    <CircleX size={14} />
                    Clear selection
                  </button>
                </div>
              </div>
              <div className="watch-selected-window-meta">
                <div>
                  <span>Dominant lane</span>
                  <strong>{LANE_META[selectedWindow.dominantLane]?.label || 'Other Signals'}</strong>
                </div>
                <div>
                  <span>Linked moments</span>
                  <strong>{formatNumber(selectedWindow.count)}</strong>
                </div>
                <div>
                  <span>Replay target</span>
                  <strong>{selectedWindow.topMoments[0] ? formatEventTitle(selectedWindow.topMoments[0]) : 'Window overview'}</strong>
                </div>
              </div>
              <div className="watch-selected-moments">
                {selectedWindow.topMoments.length === 0 && (
                  <p>No linked non-routine moments in this selected window.</p>
                )}
                {selectedWindow.topMoments.map((moment) => {
                  const eventId = getEventId(moment)
                  return (
                    <div key={eventId} className="watch-selected-moment">
                      <span>{LANE_META[getEventLane(moment)]?.label || 'Other Signals'} · {formatTimestamp(getEventTime(moment))}</span>
                      <strong>{formatEventTitle(moment)}</strong>
                      <div>
                        <Link
                          className="btn btn-secondary"
                          to={getReplayHref(cleanRunId, eventId)}
                          onClick={() => trackSelectedMomentClick('replay', moment)}
                        >
                          <TimerReset size={14} />
                          Replay
                        </Link>
                        <Link
                          className="btn btn-secondary"
                          to={getEvidenceHref(cleanRunId, eventId)}
                          onClick={() => trackSelectedMomentClick('evidence', moment)}
                        >
                          <FileSearch size={14} />
                          Evidence
                        </Link>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          <section className="watch-lanes" aria-label="Major category lanes">
            <div className="watch-section-head">
              <div>
                <span>Category lanes</span>
                <h3>{selectedWindow ? 'Moments inside the selected window' : 'Open the spikes, then inspect the source trail'}</h3>
              </div>
              {selectedLaneFilter && (
                <p>Timeline focused on {LANE_META[selectedLaneFilter]?.label || 'selected lane'}; lane rows remain visible for context.</p>
              )}
            </div>
            {laneRows.map((lane) => {
              const LaneIcon = lane.icon || Radio
              const visibleLaneMoments = selectedWindow
                ? lane.moments.filter((moment) => isMomentInBucket(moment, selectedWindow.bucket))
                : lane.moments.slice(0, 4)
              const selectedLaneCount = selectedWindow
                ? Number(selectedWindow.laneCounts[lane.key] || 0)
                : lane.count
              return (
                <article key={lane.key} className={`watch-lane lane-${lane.key} ${selectedWindow && selectedLaneCount === 0 ? 'dimmed' : ''}`}>
                  <div className="watch-lane-head">
                    <LaneIcon size={18} />
                    <div>
                      <strong>{lane.label}</strong>
                      <span>
                        {selectedWindow
                          ? `${selectedLaneCount} in selected window / ${lane.count} total`
                          : `${lane.count} linked moment${lane.count === 1 ? '' : 's'}`}
                      </span>
                    </div>
                    <p>{lane.description}</p>
                  </div>
                  <div className="watch-lane-moments">
                    {visibleLaneMoments.length === 0 && (
                      <div className="watch-lane-empty">
                        {selectedWindow ? 'No linked moments in the selected window.' : 'No linked non-routine moments in this lane.'}
                      </div>
                    )}
                    {visibleLaneMoments.map((moment) => {
                      const eventId = getEventId(moment)
                      return (
                        <div key={eventId} className="watch-moment">
                          <div>
                            <span>{formatTimestamp(getEventTime(moment))}</span>
                            <strong>{formatEventTitle(moment)}</strong>
                            <p>{getEventDescription(moment) || 'Source event available for inspection.'}</p>
                          </div>
                          <div className="watch-moment-actions">
                            <Link className="btn btn-secondary" to={getReplayHref(cleanRunId, eventId)}>
                              <TimerReset size={14} />
                              Replay
                            </Link>
                            <Link className="btn btn-secondary" to={getEvidenceHref(cleanRunId, eventId)}>
                              <FileSearch size={14} />
                              Evidence
                            </Link>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </article>
              )
            })}
          </section>
        </>
      )}
    </div>
  )
}
