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

const REPORT_LABELS = {
  approachable_report: 'Approachable Report',
  technical_report: 'Technical Report',
  planner_report: 'Next-Run Plan',
  run_summary: 'Run Summary',
}

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

function getStoryItems(story, playbackItems) {
  const storyItems = Array.isArray(story?.items) ? story.items : []
  if (storyItems.length > 0) return storyItems
  return (Array.isArray(playbackItems) ? playbackItems : [])
    .filter((item) => getEventDescription(item) && isReplayMomentCandidate(item))
    .slice(0, 8)
    .map((item, index) => ({
      ...item,
      chapter: index === 0 ? 'Trigger' : index < 3 ? 'Escalation' : index < 6 ? 'Turning Point' : 'Outcome',
      why_this_matters: item?.why_this_matters || getEventDescription(item),
    }))
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
      value: `${storyItems.length.toLocaleString()} chapters`,
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
        api.getRunPlayback(runId),
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

  function getReportUrl(row, action) {
    const format = preferredReportFormat(row)
    if (!format || !row?.type) return ''
    return action === 'download'
      ? api.getRunReportDownloadUrl(runId, row.type, format)
      : api.getRunReportViewUrl(runId, row.type, format)
  }

  const provenance = runDetail?.provenance || {}
  const runMetadata = runDetail?.run_metadata || {}
  const activity = runDetail?.activity || {}
  const llm = runDetail?.llm || {}
  const cleanRunId = String(runId || '').trim()

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
                onClick={() => setActiveTab(key)}
              >
                {createElement(icon, { size: 15 })}
                {label}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <>
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
            <div className="run-replay-grid">
              <div className="card run-replay-rail">
                <div className="card-header">
                  <h3>
                    <ListTree size={18} />
                    Key Moments
                  </h3>
                  <span className="strip-meta">{storyItems.length} moments</span>
                </div>
                <div className="card-body">
                  {storyItems.length === 0 ? (
                    <div className="empty-state compact">No curated replay moments are available yet. Routine work and idle events are hidden here; use Evidence for the raw log.</div>
                  ) : (
                    <div className="run-replay-chapter-list">
                      {storyItems.map((item, index) => {
                        const eventId = getEventId(item)
                        const selected = eventId > 0 && eventId === getEventId(activeStoryItem)
                        return (
                          <button
                            key={`${eventId || index}-${getEventTitle(item)}`}
                            type="button"
                            className={`run-replay-chapter ${selected ? 'active' : ''}`}
                            onClick={() => setSelectedEventId(eventId)}
                          >
                            <span>{item?.chapter ? `Moment ${index + 1} - ${item.chapter}` : `Moment ${index + 1}`}</span>
                            <strong>{getEventTitle(item)}</strong>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="card run-replay-main">
                <div className="card-header">
                  <h3>{activeStoryItem ? getEventTitle(activeStoryItem) : 'Replay'}</h3>
                  {activeStoryItem && <span className="strip-meta">{formatRelative(getEventTime(activeStoryItem))}</span>}
                </div>
                <div className="card-body">
                  {activeStoryItem ? (
                    <>
                      <p className="run-replay-description">{getEventDescription(activeStoryItem)}</p>
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
                    </>
                  ) : (
                    <div className="empty-state compact">Replay data has not been generated for this run.</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'evidence' && (
            <div className="card">
              <div className="card-header">
                <h3>Evidence Links</h3>
                <span className="strip-meta">{sourceTraces.length || playbackItems.length} available</span>
              </div>
              <div className="card-body run-trace-list">
                {(sourceTraces.length > 0 ? sourceTraces : playbackItems.slice(0, 20)).map((trace, index) => {
                  const eventId = Number(trace?.event_id || trace?.id || 0)
                  return (
                    <div key={`${eventId || index}-${getEventTitle(trace)}`} className="run-trace-item">
                      <div className="run-trace-main">
                        <h4>{trace.title || getEventTitle(trace)}</h4>
                        <p>{getEventDescription(trace)}</p>
                        <div className="run-trace-meta">
                          <span>{formatLabel(trace.event_type || trace.category || 'event')}</span>
                          {trace.salience !== undefined && <span>Salience {trace.salience}</span>}
                          <span>{formatRelative(getEventTime(trace))}</span>
                        </div>
                      </div>
                      <div className="run-trace-links">
                        {trace.trace_url && (
                          <a href={trace.trace_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">
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
                {sourceTraces.length === 0 && playbackItems.length === 0 && (
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
                        <a
                          className="btn btn-secondary"
                          href={getReportUrl(row, 'view')}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink size={14} />
                          Open
                        </a>
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
