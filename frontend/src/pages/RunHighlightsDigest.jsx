import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Activity,
  Eye,
  FileSearch,
  Handshake,
  Hash,
  Scale,
  ShieldAlert,
  Skull,
  Sparkles,
  TimerReset,
} from 'lucide-react'
import { api } from '../services/api'
import { getScheduleEntryForRunId } from '../data/runSchedule'
import { getStoryReplayHref, getWatchReplayHref } from '../utils/bestMoments'
import { trackKpiEventOnce } from '../services/kpiAnalytics'

const ROUTINE_EVENT_TYPES = new Set(['work', 'idle', 'vote', 'processing_error'])

function cleanString(value) {
  return String(value || '').trim()
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString()
}

function formatTimestamp(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatLabel(value) {
  return cleanString(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function getEventId(item) {
  return Number(item?.event_id || item?.id || 0)
}

function getEventTitle(item) {
  return cleanString(item?.title || item?.event_type || 'Run event').replace(/_/g, ' ')
}

function getEventDescription(item) {
  return cleanString(item?.why_this_matters || item?.description || item?.summary)
}

function getEventTime(item) {
  return item?.created_at || item?.timestamp || ''
}

function isDigestMoment(item) {
  if (!item || getEventId(item) <= 0) return false
  const eventType = cleanString(item.event_type)
  if (ROUTINE_EVENT_TYPES.has(eventType)) return false
  return true
}

function sortByTime(items) {
  return [...items].sort((a, b) => {
    const delta = (Date.parse(getEventTime(a)) || 0) - (Date.parse(getEventTime(b)) || 0)
    if (delta !== 0) return delta
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

function getMomentLane(item) {
  const eventType = cleanString(item?.event_type)
  const category = cleanString(item?.category)
  if (['agent_died', 'became_dormant', 'agent_revived', 'awakened'].includes(eventType)) return 'survival'
  if (['law_passed', 'proposal_resolved', 'create_proposal', 'vote_enforcement'].includes(eventType) || category === 'governance') return 'governance'
  if (['trade', 'request_aid', 'refuse_aid'].includes(eventType) || ['cooperation', 'alliance'].includes(category)) return 'aid_trade'
  if (category === 'conflict' || ['public_accusation', 'contest_proposal', 'initiate_sanction', 'initiate_seizure', 'initiate_exile', 'enforcement_initiated', 'agent_sanctioned', 'resources_seized', 'agent_exiled'].includes(eventType)) return 'public_order'
  return 'other'
}

function pickTopMoment(moments, lane) {
  return moments
    .filter((item) => getMomentLane(item) === lane)
    .sort((a, b) => {
      const salienceDelta = Number(b?.salience || 0) - Number(a?.salience || 0)
      if (salienceDelta !== 0) return salienceDelta
      return (Date.parse(getEventTime(a)) || 0) - (Date.parse(getEventTime(b)) || 0)
    })[0] || null
}

function buildDigestRows(activity, moments) {
  return [
    {
      key: 'survival',
      label: 'Deaths / Dormancy',
      icon: Skull,
      value: `${formatNumber(activity.deaths)} / ${formatNumber(activity.became_dormant)}`,
      detail: `${formatNumber(activity.agent_revived)} revivals recorded.`,
      moment: pickTopMoment(moments, 'survival'),
    },
    {
      key: 'governance',
      label: 'Laws / Proposals',
      icon: Scale,
      value: `${formatNumber(activity.laws_passed)} / ${formatNumber(activity.proposal_actions)}`,
      detail: `${formatNumber(activity.vote_actions)} vote actions in the run.`,
      moment: pickTopMoment(moments, 'governance'),
    },
    {
      key: 'aid_trade',
      label: 'Aid / Trade',
      icon: Handshake,
      value: `${formatNumber(activity.aid_requests)} / ${formatNumber(activity.trade_actions)}`,
      detail: `${formatNumber(activity.aid_refusals)} aid refusals recorded.`,
      moment: pickTopMoment(moments, 'aid_trade'),
    },
    {
      key: 'public_order',
      label: 'Public Order',
      icon: ShieldAlert,
      value: `${formatNumber(activity.public_order_events)} signals`,
      detail: `${formatNumber(activity.conflict_events)} conflict signals in this run.`,
      moment: pickTopMoment(moments, 'public_order'),
    },
  ]
}

function buildNotableDecisions(moments) {
  const decisionTypes = new Set(['law_passed', 'proposal_resolved', 'create_proposal', 'contest_proposal'])
  return moments
    .filter((item) => decisionTypes.has(cleanString(item?.event_type)) || getMomentLane(item) === 'governance')
    .sort((a, b) => Number(b?.salience || 0) - Number(a?.salience || 0))
    .slice(0, 4)
}

export default function RunHighlightsDigest() {
  const { runId } = useParams()
  const cleanRunId = cleanString(runId)
  const scheduledRun = getScheduleEntryForRunId(cleanRunId)
  const [runDetail, setRunDetail] = useState(null)
  const [story, setStory] = useState(null)
  const [loading, setLoading] = useState(Boolean(cleanRunId))
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadDigest() {
      setLoading(true)
      setError('')
      const [detailResult, storyResult] = await Promise.allSettled([
        api.getRunDetail(cleanRunId, 96, 30, 45),
        api.getReplayStory(96, 45, 10, cleanRunId),
      ])
      if (cancelled) return

      const detailPayload = detailResult.status === 'fulfilled' ? detailResult.value : null
      const storyPayload = storyResult.status === 'fulfilled' ? storyResult.value : null
      setRunDetail(detailPayload && typeof detailPayload === 'object' ? detailPayload : null)
      setStory(storyPayload && typeof storyPayload === 'object' ? storyPayload : null)
      if (!detailPayload && !storyPayload) setError('Highlights digest could not be loaded.')
      setLoading(false)
    }

    if (cleanRunId) void loadDigest()
    return () => {
      cancelled = true
    }
  }, [cleanRunId])

  const storyItems = useMemo(() => Array.isArray(story?.items) ? story.items : [], [story])
  const sourceTraces = useMemo(() => Array.isArray(runDetail?.source_traces) ? runDetail.source_traces : [], [runDetail])
  const digestMoments = useMemo(
    () => uniqueMoments([...storyItems, ...sourceTraces].filter(isDigestMoment)),
    [sourceTraces, storyItems],
  )
  const activity = useMemo(() => runDetail?.activity || {}, [runDetail])
  const digestRows = useMemo(() => buildDigestRows(activity, digestMoments), [activity, digestMoments])
  const notableDecisions = useMemo(() => buildNotableDecisions(digestMoments), [digestMoments])
  const topMoments = useMemo(
    () => [...digestMoments]
      .sort((a, b) => Number(b?.salience || 0) - Number(a?.salience || 0))
      .slice(0, 6),
    [digestMoments],
  )

  useEffect(() => {
    if (!cleanRunId || loading || error) return
    trackKpiEventOnce('run_highlights_digest_view', `run_highlights_digest:${cleanRunId}`, {
      runId: cleanRunId,
      surface: 'run_highlights_digest',
      target: 'digest',
      metadata: {
        story_moments: storyItems.length,
        digest_moments: digestMoments.length,
      },
    })
  }, [cleanRunId, digestMoments.length, error, loading, storyItems.length])

  return (
    <div className="run-highlights-page">
      <div className="page-header">
        <h1>
          <Sparkles size={30} />
          Run Highlights
        </h1>
        <p className="page-description">
          A compact digest of deaths, decisions, aid/trade, unusual signals, and links back into Watch, Replay, and Evidence.
        </p>
      </div>

      <div className="run-detail-topbar">
        <div className="run-id-pill">
          <Hash size={15} />
          <span>{cleanRunId || 'unknown-run'}</span>
        </div>
        <div className="run-topbar-actions">
          <Link className="btn btn-secondary" to={`/watch?run=${encodeURIComponent(cleanRunId)}`}>
            <Eye size={14} />
            Watch
          </Link>
          <Link className="btn btn-secondary" to={getStoryReplayHref(cleanRunId)}>
            <TimerReset size={14} />
            Replay
          </Link>
          <Link className="btn btn-secondary" to={`/runs/${encodeURIComponent(cleanRunId)}`}>
            <FileSearch size={14} />
            Evidence
          </Link>
          <Link className="btn btn-secondary" to="/archive">Archive</Link>
        </div>
      </div>

      {loading && <div className="empty-state">Loading run highlights...</div>}
      {!loading && (error || !cleanRunId) && (
        <div className="feed-notice">{error || 'Run ID is required.'}</div>
      )}

      {!loading && !error && cleanRunId && (
        <>
          <section className="run-highlights-hero" aria-label="Highlights digest summary">
            <div>
              <span>{scheduledRun?.label || 'Completed run'} · {formatLabel(runDetail?.run_metadata?.run_class || 'public run')}</span>
              <h2>{scheduledRun?.declaredQuestion || 'What stood out in this completed run?'}</h2>
              <p>{scheduledRun?.claimBoundary || 'Digest view only; use Evidence before making claims.'}</p>
            </div>
            <div className="run-highlights-total">
              <Activity size={18} />
              <span>Scoped events</span>
              <strong>{formatNumber(activity.total_events)}</strong>
            </div>
          </section>

          <section className="run-highlights-grid" aria-label="Highlights by category">
            {digestRows.map((row) => {
              const RowIcon = row.icon
              const eventId = getEventId(row.moment)
              return (
                <article key={row.key} className={`run-highlight-panel lane-${row.key}`}>
                  <div className="run-highlight-panel-head">
                    <RowIcon size={18} />
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                  <p>{row.detail}</p>
                  {row.moment ? (
                    <div className="run-highlight-moment">
                      <span>{formatTimestamp(getEventTime(row.moment))}</span>
                      <strong>{getEventTitle(row.moment)}</strong>
                      <p>{getEventDescription(row.moment) || 'Source event available for inspection.'}</p>
                      <div>
                        <Link className="btn btn-secondary" to={getWatchReplayHref(cleanRunId, eventId)}>Watch</Link>
                        <Link className="btn btn-secondary" to={`/runs/${encodeURIComponent(cleanRunId)}/replay?mode=timeline&event=${eventId}`}>Replay</Link>
                        <Link className="btn btn-secondary" to={`/runs/${encodeURIComponent(cleanRunId)}?event=${eventId}`}>Evidence</Link>
                      </div>
                    </div>
                  ) : (
                    <div className="run-highlight-empty">No non-routine source moment in this lane.</div>
                  )}
                </article>
              )
            })}
          </section>

          <section className="run-highlights-two-column">
            <div className="card">
              <div className="card-header">
                <h3>Notable decisions</h3>
                <span className="strip-meta">{notableDecisions.length} shown</span>
              </div>
              <div className="card-body run-highlight-list">
                {notableDecisions.map((moment) => {
                  const eventId = getEventId(moment)
                  return (
                    <div key={eventId} className="run-highlight-list-item">
                      <span>{formatLabel(moment.event_type)} · {formatTimestamp(getEventTime(moment))}</span>
                      <strong>{getEventTitle(moment)}</strong>
                      <p>{getEventDescription(moment) || 'Decision source available for inspection.'}</p>
                      <Link to={getWatchReplayHref(cleanRunId, eventId)}>Open in Watch</Link>
                    </div>
                  )
                })}
                {notableDecisions.length === 0 && (
                  <div className="empty-state compact">No notable governance decision moments were available.</div>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <h3>Top watch moments</h3>
                <span className="strip-meta">{topMoments.length} linked</span>
              </div>
              <div className="card-body run-highlight-list">
                {topMoments.map((moment) => {
                  const eventId = getEventId(moment)
                  return (
                    <div key={eventId} className="run-highlight-list-item">
                      <span>{formatLabel(getMomentLane(moment))} · {formatTimestamp(getEventTime(moment))}</span>
                      <strong>{getEventTitle(moment)}</strong>
                      <p>{getEventDescription(moment) || 'Source event available for inspection.'}</p>
                      <Link to={getWatchReplayHref(cleanRunId, eventId)}>Open in Watch</Link>
                    </div>
                  )
                })}
                {topMoments.length === 0 && (
                  <div className="empty-state compact">No linked watch moments are available for this run.</div>
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
