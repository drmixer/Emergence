import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  ShieldCheck,
  Clock3,
  ExternalLink,
  Share2,
  Hash,
  CircleCheck,
  CircleAlert,
  CircleDashed,
} from 'lucide-react'
import { api } from '../services/api'
import { trackShareAction } from '../services/shareAnalytics'

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

const verificationStyles = {
  verified: {
    label: 'Verified',
    icon: CircleCheck,
    className: 'verified',
  },
  partial: {
    label: 'Partially verified',
    icon: CircleAlert,
    className: 'partial',
  },
  unverified: {
    label: 'Unverified',
    icon: CircleDashed,
    className: 'unverified',
  },
}

export default function RunDetail() {
  const { runId } = useParams()
  const [searchParams] = useSearchParams()
  const requestedEventId = Number(searchParams.get('event') || 0)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [shareNotice, setShareNotice] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const payload = await api.getRunDetail(runId, 48, 16, 55)
        if (!cancelled) {
          setData(payload)
        }
      } catch (loadError) {
        if (!cancelled) {
          setData(null)
          setError(loadError?.message || 'Failed to load run details')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [runId])

  const provenance = data?.provenance || {}
  const verificationState = String(provenance.verification_state || 'unverified')
  const verificationMeta = verificationStyles[verificationState] || verificationStyles.unverified
  const VerificationIcon = verificationMeta.icon

  const startTime = provenance?.time_window?.start_utc
  const endTime = provenance?.time_window?.end_utc
  const timeWindowSummary =
    startTime && endTime ? `${formatTimestamp(startTime)} -> ${formatTimestamp(endTime)}` : 'Unknown time window'

  const shareRun = async () => {
    const origin = window.location.origin
    const cleanRunId = String(runId || '').trim()
    const safeRunId = encodeURIComponent(cleanRunId)
    if (!safeRunId) return

    const shareUrl = `${origin}/share/run/${safeRunId}`
    const title = `Run ${runId} | EMERGENCE`
    const text = 'Evidence-backed run snapshot from Emergence.'
    trackShareAction('share_clicked', {
      runId: cleanRunId,
      surface: 'run_detail_topbar',
      target: 'run_link',
    })

    try {
      if (navigator.share) {
        await navigator.share({ title, text, url: shareUrl })
        trackShareAction('share_native_success', {
          runId: cleanRunId,
          surface: 'run_detail_topbar',
          target: 'run_link',
        })
      } else {
        await navigator.clipboard.writeText(shareUrl)
        trackShareAction('share_copied', {
          runId: cleanRunId,
          surface: 'run_detail_topbar',
          target: 'run_link',
        })
      }
      setShareNotice('Run link ready to share.')
      setTimeout(() => setShareNotice(''), 2000)
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setShareNotice('Unable to share this run right now.')
        setTimeout(() => setShareNotice(''), 2000)
      }
    }
  }

  const copyRunOgUrl = async () => {
    const cleanRunId = String(runId || '').trim()
    const safeRunId = encodeURIComponent(cleanRunId)
    if (!safeRunId) return
    const apiBase = String(api?.baseUrl || '').replace(/\/$/, '')
    const ogUrl = `${apiBase}/api/analytics/runs/${safeRunId}/social-card.svg`
    trackShareAction('share_clicked', {
      runId: cleanRunId,
      surface: 'run_detail_topbar',
      target: 'run_og_url',
    })

    try {
      await navigator.clipboard.writeText(ogUrl)
      trackShareAction('share_copied', {
        runId: cleanRunId,
        surface: 'run_detail_topbar',
        target: 'run_og_url',
      })
      setShareNotice('Run OG image URL copied.')
      setTimeout(() => setShareNotice(''), 2000)
    } catch {
      setShareNotice('Unable to copy run OG URL right now.')
      setTimeout(() => setShareNotice(''), 2000)
    }
  }

  const shareMoment = async (eventId) => {
    const origin = window.location.origin
    const cleanRunId = String(runId || '').trim()
    const safeRunId = encodeURIComponent(cleanRunId)
    if (!safeRunId || !eventId) return
    const safeEventId = encodeURIComponent(String(eventId))

    const shareUrl = `${origin}/share/run/${safeRunId}/moment/${safeEventId}`
    const title = `Run ${runId} • Moment #${eventId}`
    const text = 'Evidence-backed moment from Emergence.'
    trackShareAction('share_clicked', {
      runId: cleanRunId,
      eventId,
      surface: 'run_detail_trace_card',
      target: 'moment_link',
    })

    try {
      if (navigator.share) {
        await navigator.share({ title, text, url: shareUrl })
        trackShareAction('share_native_success', {
          runId: cleanRunId,
          eventId,
          surface: 'run_detail_trace_card',
          target: 'moment_link',
        })
      } else {
        await navigator.clipboard.writeText(shareUrl)
        trackShareAction('share_copied', {
          runId: cleanRunId,
          eventId,
          surface: 'run_detail_trace_card',
          target: 'moment_link',
        })
      }
      setShareNotice('Moment link ready to share.')
      setTimeout(() => setShareNotice(''), 2000)
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setShareNotice('Unable to share this moment right now.')
        setTimeout(() => setShareNotice(''), 2000)
      }
    }
  }

  const copyMomentOgUrl = async (eventId) => {
    const safeEventId = encodeURIComponent(String(eventId || '').trim())
    const cleanRunId = String(runId || '').trim()
    const safeRunId = encodeURIComponent(cleanRunId)
    if (!safeEventId) return

    const apiBase = String(api?.baseUrl || '').replace(/\/$/, '')
    const ogUrl = safeRunId
      ? `${apiBase}/api/analytics/moments/${safeEventId}/social-card.svg?run_id=${safeRunId}`
      : `${apiBase}/api/analytics/moments/${safeEventId}/social-card.svg`
    trackShareAction('share_clicked', {
      runId: cleanRunId,
      eventId,
      surface: 'run_detail_trace_card',
      target: 'moment_og_url',
    })

    try {
      await navigator.clipboard.writeText(ogUrl)
      trackShareAction('share_copied', {
        runId: cleanRunId,
        eventId,
        surface: 'run_detail_trace_card',
        target: 'moment_og_url',
      })
      setShareNotice('Moment OG image URL copied.')
      setTimeout(() => setShareNotice(''), 2000)
    } catch {
      setShareNotice('Unable to copy moment OG URL right now.')
      setTimeout(() => setShareNotice(''), 2000)
    }
  }

  return (
    <div className="run-detail-page">
      <div className="page-header">
        <h1>
          <ShieldCheck size={30} />
          Run Detail
        </h1>
        <p className="page-description">Public metrics and evidence traces for a specific simulation run.</p>
      </div>

      <div className="run-detail-topbar">
        <div className="run-id-pill">
          <Hash size={15} />
          <span>{runId || 'unknown-run'}</span>
        </div>
        <div className="run-topbar-actions">
          <button type="button" className="btn btn-secondary run-share-btn" onClick={shareRun}>
            <Share2 size={14} />
            Share Run
          </button>
          <button type="button" className="btn btn-secondary run-share-btn" onClick={copyRunOgUrl}>
            Copy Run OG URL
          </button>
          <Link className="btn btn-secondary" to="/highlights">
            Back to Highlights
          </Link>
        </div>
      </div>

      {loading && <div className="empty-state">Loading run detail...</div>}
      {!loading && error && <div className="feed-notice">{error}</div>}
      {shareNotice && <div className="feed-notice success">{shareNotice}</div>}

      {!loading && !error && data && (
        <>
          <div className="card run-provenance-card">
            <div className="card-header">
              <h3>Evidence Provenance</h3>
              <span className={`verification-badge ${verificationMeta.className}`}>
                <VerificationIcon size={14} />
                {verificationMeta.label}
              </span>
            </div>
            <div className="card-body">
              <div className="run-provenance-grid">
                <div>
                  <span className="label">Run ID</span>
                  <strong>{provenance.run_id || runId}</strong>
                </div>
                <div>
                  <span className="label">Time Window</span>
                  <strong>{timeWindowSummary}</strong>
                </div>
                <div>
                  <span className="label">Source</span>
                  <strong>{String(provenance.verification_source || 'unknown').replace(/_/g, ' ')}</strong>
                </div>
              </div>
            </div>
          </div>

          <div className="stats-grid run-detail-stats">
            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">LLM Calls</span>
              </div>
              <div className="stat-value">{formatNumber(data?.llm?.calls)}</div>
              <div className="stat-change">
                <Clock3 size={14} />
                <span>{formatRelative(data?.captured_at)}</span>
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Total Tokens</span>
              </div>
              <div className="stat-value">{formatNumber(data?.llm?.total_tokens)}</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Estimated Cost</span>
              </div>
              <div className="stat-value run-currency">{formatUsd(data?.llm?.estimated_cost_usd)}</div>
            </div>

            <div className="stat-card">
              <div className="stat-header">
                <span className="stat-label">Total Events</span>
              </div>
              <div className="stat-value">{formatNumber(data?.activity?.total_events)}</div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Run Activity</h3>
            </div>
            <div className="card-body">
              <div className="run-activity-grid">
                <div><span>Checkpoint actions</span><strong>{formatNumber(data?.activity?.checkpoint_actions)}</strong></div>
                <div><span>Deterministic actions</span><strong>{formatNumber(data?.activity?.deterministic_actions)}</strong></div>
                <div><span>Proposal actions</span><strong>{formatNumber(data?.activity?.proposal_actions)}</strong></div>
                <div><span>Votes</span><strong>{formatNumber(data?.activity?.vote_actions)}</strong></div>
                <div><span>Forum actions</span><strong>{formatNumber(data?.activity?.forum_actions)}</strong></div>
                <div><span>Laws passed</span><strong>{formatNumber(data?.activity?.laws_passed)}</strong></div>
                <div><span>Deaths</span><strong>{formatNumber(data?.activity?.deaths)}</strong></div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Source Trace Links</h3>
              <span className="strip-meta">{Array.isArray(data?.source_traces) ? data.source_traces.length : 0} traces</span>
            </div>
            <div className="card-body run-trace-list">
              {Array.isArray(data?.source_traces) && data.source_traces.length > 0 ? (
                data.source_traces.map((trace) => {
                  const isFocused = requestedEventId > 0 && Number(trace.event_id) === requestedEventId
                  return (
                  <div key={trace.event_id} className={`run-trace-item ${isFocused ? 'focused' : ''}`}>
                    <div className="run-trace-main">
                      <h4>{trace.title || trace.event_type}</h4>
                      <p>{trace.description}</p>
                      <div className="run-trace-meta">
                        <span>{trace.event_type}</span>
                        <span>Salience {trace.salience}</span>
                        <span>{formatRelative(trace.created_at)}</span>
                      </div>
                    </div>
                    <div className="run-trace-links">
                      <a href={trace.trace_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
                        Event API <ExternalLink size={14} />
                      </a>
                      <Link to={`/timeline?event=${trace.event_id}`} className="btn btn-secondary">
                        Open Timeline
                      </Link>
                      <button type="button" className="btn btn-secondary" onClick={() => shareMoment(trace.event_id)}>
                        <Share2 size={14} />
                        Share Moment
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => copyMomentOgUrl(trace.event_id)}>
                        Copy OG URL
                      </button>
                    </div>
                  </div>
                  )
                })
              ) : (
                <div className="empty-state compact">No high-salience traces yet for this run.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
