import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  CircleX,
  Eye,
  FileSearch,
  Handshake,
  Hash,
  Map as MapIcon,
  Radio,
  Scale,
  ShieldAlert,
  TimerReset,
  Users,
} from 'lucide-react'
import { api } from '../services/api'
import {
  getLatestCompletedScheduledRun,
  getScheduleEntryForRunId,
} from '../data/runSchedule'
import { trackKpiEventOnce } from '../services/kpiAnalytics'

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

function getEventLane(item) {
  const eventType = cleanString(item?.event_type)
  const category = cleanString(item?.category)

  if (['agent_died', 'became_dormant', 'agent_revived', 'awakened'].includes(eventType)) return 'survival'
  if (['law_passed', 'proposal_resolved', 'create_proposal', 'vote_enforcement'].includes(eventType) || category === 'governance') return 'governance'
  if (['trade', 'request_aid', 'refuse_aid'].includes(eventType) || ['cooperation', 'alliance'].includes(category)) return 'aid_trade'
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

function isVisibleMoment(item) {
  if (!item || getEventId(item) <= 0) return false
  const eventType = cleanString(item?.event_type)
  const category = cleanString(item?.category)
  if (ROUTINE_EVENT_TYPES.has(eventType)) return false
  if (['survival', 'governance', 'aid_trade', 'public_order', 'system'].includes(getEventLane(item))) return true
  if (['crisis', 'conflict', 'governance', 'cooperation', 'alliance'].includes(category)) return true
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
    const candidates = moments.filter((item) => {
      const eventMs = Date.parse(getEventTime(item))
      return Number.isFinite(eventMs) && eventMs >= startMs && eventMs <= endMs
    })
    const representative = candidates
      .sort((a, b) => Number(b?.salience || 0) - Number(a?.salience || 0))[0] || null
    return { ...bucket, representative }
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

function getMomentsInBucket(moments, bucket) {
  return uniqueMoments(moments)
    .filter((moment) => isMomentInBucket(moment, bucket))
    .sort((a, b) => {
      const salienceDelta = Number(b?.salience || 0) - Number(a?.salience || 0)
      if (salienceDelta !== 0) return salienceDelta
      return (Date.parse(getEventTime(a)) || 0) - (Date.parse(getEventTime(b)) || 0)
    })
}

function buildSelectedWindow(bucket, moments) {
  if (!bucket) return null
  const windowMoments = getMomentsInBucket(moments, bucket)
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
    count: windowMoments.length || Number(bucket.event_count || 0),
    dominantLane,
    laneCounts,
    moments: windowMoments,
    topMoments: windowMoments.slice(0, 3),
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
        moments: items.slice(0, 4),
      }
    })
    .filter((lane) => lane.count > 0 || lane.key !== 'other')
}

function getArchiveRunId(archive) {
  const items = Array.isArray(archive?.items) ? archive.items : []
  return cleanString(items[0]?.run_id)
}

export default function WatchReplay() {
  const [searchParams] = useSearchParams()
  const requestedRunId = cleanString(searchParams.get('run'))
  const scheduledRun = getLatestCompletedScheduledRun()
  const initialRunId = requestedRunId || scheduledRun?.runId || ''
  const [runId, setRunId] = useState(initialRunId)
  const archiveDefaultApplied = useRef(false)
  const [archive, setArchive] = useState(null)
  const [runDetail, setRunDetail] = useState(null)
  const [playback, setPlayback] = useState(null)
  const [density, setDensity] = useState(null)
  const [story, setStory] = useState(null)
  const [loading, setLoading] = useState(Boolean(initialRunId))
  const [error, setError] = useState('')
  const [selectedBucketKey, setSelectedBucketKey] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadArchive() {
      const payload = await api.getRunsArchive(12, false).catch(() => null)
      if (cancelled) return
      setArchive(payload && typeof payload === 'object' ? payload : null)
      const archiveRunId = getArchiveRunId(payload)
      if (!requestedRunId && !archiveDefaultApplied.current) {
        archiveDefaultApplied.current = true
        if (archiveRunId && archiveRunId !== runId) {
          setRunId(archiveRunId)
        }
      }
    }

    void loadArchive()
    return () => {
      cancelled = true
    }
  }, [requestedRunId, runId])

  useEffect(() => {
    let cancelled = false
    if (!runId) {
      return () => {
        cancelled = true
      }
    }

    async function loadRun() {
      setLoading(true)
      setError('')
      const [detailResult, playbackResult, densityResult, storyResult] = await Promise.allSettled([
        api.getRunDetail(runId, 96, 24, 45),
        api.getRunPlayback(runId, 120, 420),
        api.getPlotTurnReplay(96, 45, 60, 240, runId),
        api.getReplayStory(96, 45, 10, runId),
      ])
      if (cancelled) return

      const detailPayload = detailResult.status === 'fulfilled' ? detailResult.value : null
      const playbackPayload = playbackResult.status === 'fulfilled' ? playbackResult.value : null
      const densityPayload = densityResult.status === 'fulfilled' ? densityResult.value : null
      const storyPayload = storyResult.status === 'fulfilled' ? storyResult.value : null

      setRunDetail(detailPayload && typeof detailPayload === 'object' ? detailPayload : null)
      setPlayback(playbackPayload && typeof playbackPayload === 'object' ? playbackPayload : null)
      setDensity(densityPayload && typeof densityPayload === 'object' ? densityPayload : null)
      setStory(storyPayload && typeof storyPayload === 'object' ? storyPayload : null)

      if (!detailPayload && !playbackPayload && !densityPayload && !storyPayload) {
        setError('Watch replay data could not be loaded.')
      }
      setLoading(false)
    }

    void loadRun()
    return () => {
      cancelled = true
    }
  }, [runId])

  const archiveItems = Array.isArray(archive?.items) ? archive.items : []
  const runSchedule = getScheduleEntryForRunId(runId) || scheduledRun
  const playbackItems = useMemo(() => Array.isArray(playback?.items) ? playback.items : [], [playback])
  const densityItems = useMemo(() => Array.isArray(density?.items) ? density.items : [], [density])
  const storyItems = useMemo(() => Array.isArray(story?.items) ? story.items : [], [story])
  const visibleMoments = useMemo(
    () => uniqueMoments([...storyItems, ...densityItems, ...playbackItems].filter(isVisibleMoment)),
    [densityItems, playbackItems, storyItems],
  )
  const window = useMemo(() => getRunWindow(runDetail, playback, density), [density, playback, runDetail])
  const densityBuckets = useMemo(
    () => buildDensityBuckets(density, visibleMoments, window),
    [density, visibleMoments, window],
  )
  const selectedBucket = useMemo(
    () => densityBuckets.find((bucket) => getBucketKey(bucket) === selectedBucketKey) || null,
    [densityBuckets, selectedBucketKey],
  )
  const selectedWindow = useMemo(
    () => buildSelectedWindow(selectedBucket, visibleMoments),
    [selectedBucket, visibleMoments],
  )
  const laneRows = useMemo(() => buildLaneRows(visibleMoments), [visibleMoments])
  const maxBucketCount = Math.max(1, ...densityBuckets.map((bucket) => Number(bucket.event_count || 0)))
  const activity = runDetail?.activity || {}
  const cleanRunId = cleanString(runId)
  const unavailableError = cleanRunId ? '' : 'No completed public run is available for the watch board.'

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
      setSelectedBucketKey('')
      setRunId(nextRunId)
    }
  }

  function handleBucketSelect(bucket) {
    const key = getBucketKey(bucket)
    setSelectedBucketKey((current) => current === key ? '' : key)
  }

  function clearSelectedWindow() {
    setSelectedBucketKey('')
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
      {cleanRunId && loading && <div className="empty-state">Loading watch replay...</div>}
      {cleanRunId && !loading && error && <div className="feed-notice">{error}</div>}

      {cleanRunId && !loading && !error && (
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
              <p>{densityBuckets.length} buckets · {visibleMoments.length} linked moments</p>
            </div>
            <div className="watch-density-bars">
              {densityBuckets.map((bucket) => {
                const count = Number(bucket.event_count || 0)
                const representative = bucket.representative
                const eventId = getEventId(representative)
                const lane = representative
                  ? getEventLane(representative)
                  : normalizeLaneKey(bucket.dominant_category)
                const height = count > 0 ? Math.max(16, Math.round((count / maxBucketCount) * 110)) : 4
                return (
                  <button
                    key={`${bucket.index}-${bucket.bucket_start}`}
                    type="button"
                    className={`watch-density-bar lane-${lane} ${selectedWindow?.key === getBucketKey(bucket) ? 'active' : ''}`}
                    onClick={() => handleBucketSelect(bucket)}
                    aria-pressed={selectedWindow?.key === getBucketKey(bucket)}
                    title={`${count} moment${count === 1 ? '' : 's'} near ${formatTimeOnly(bucket.bucket_start)}`}
                    aria-label={`Select ${count} event timeline bucket near ${formatTimeOnly(bucket.bucket_start)}`}
                    disabled={count <= 0 && eventId <= 0 && !bucket.dominant_category}
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
                </div>
                <button type="button" className="btn btn-secondary" onClick={clearSelectedWindow}>
                  <CircleX size={14} />
                  Clear selection
                </button>
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
            </section>
          )}

          <section className="watch-lanes" aria-label="Major category lanes">
            <div className="watch-section-head">
              <div>
                <span>Category lanes</span>
                <h3>{selectedWindow ? 'Moments inside the selected window' : 'Open the spikes, then inspect the source trail'}</h3>
              </div>
            </div>
            {laneRows.map((lane) => {
              const LaneIcon = lane.icon || Radio
              const visibleLaneMoments = selectedWindow
                ? lane.moments.filter((moment) => isMomentInBucket(moment, selectedWindow.bucket))
                : lane.moments
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
