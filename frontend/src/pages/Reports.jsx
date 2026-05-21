import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Download,
  FileSearch,
  RefreshCw,
  TimerReset,
} from 'lucide-react'
import { api } from '../services/api'
import { getNextScheduledRun, getScheduleEntryForRunId } from '../data/runSchedule'
import { getStoryReplayHref } from '../utils/bestMoments'
import RunBriefCard from '../components/RunBriefCard'
import { trackKpiEvent, trackKpiEventOnce } from '../services/kpiAnalytics'

function formatTimestamp(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

function formatDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleDateString()
}

function formatUsd(value) {
  return Number(value || 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function formatDuration(hours) {
  const value = Number(hours || 0)
  if (!Number.isFinite(value) || value <= 0) return 'Unknown duration'
  if (value >= 24) return `${value.toFixed(1)}h`
  return `${value.toFixed(1)}h`
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function preferredFormat(artifact) {
  const formats = Array.isArray(artifact?.formats) ? artifact.formats : []
  if (formats.includes('markdown')) return 'markdown'
  if (formats.includes('json')) return 'json'
  return ''
}

const ARCHIVE_REPORT_ARTIFACTS = [
  ['viewer_brief', 'Emergence Brief'],
  ['approachable_report', 'Approachable Story'],
  ['technical_report', 'Technical Report'],
  ['planner_report', 'Next-Run Plan'],
  ['run_summary', 'Run Summary'],
]

function getRunTakeaway(item) {
  const summary = item?.summary || {}
  const metrics = summary?.metrics || {}
  const candidates = [
    summary.closeout_takeaway,
    summary.why_this_run_matters,
    summary.key_outcome,
    summary.narrative_takeaway,
    summary.headline,
  ]
  const explicit = String(candidates.find((value) => String(value || '').trim()) || '').trim()
  if (explicit) return explicit

  const condition = formatLabel(summary.condition_name || item?.run_metadata?.condition_name || 'this condition')
  const totalEvents = Number(metrics.total_events || 0)
  const lawsPassed = Number(metrics.laws_passed || 0)
  const deaths = Number(metrics.deaths || 0)
  const signals = []
  if (totalEvents > 0) signals.push(`${totalEvents.toLocaleString()} captured events`)
  signals.push(`${lawsPassed.toLocaleString()} laws passed`)
  signals.push(`${deaths.toLocaleString()} deaths recorded`)
  return `${condition} run; review ${signals.join(', ')} before comparing outcomes.`
}

function getRunId(item) {
  return String(item?.run_id || '').trim()
}

function trackArchivePathClick(runId, target, metadata = {}) {
  trackKpiEvent('run_path_click', {
    runId,
    surface: 'archive',
    target,
    metadata,
  })
}

function getRunCondition(item) {
  return String(item?.summary?.condition_name || item?.run_metadata?.condition_name || '').trim()
}

function getRunSeason(item) {
  return String(item?.summary?.season_number || item?.run_metadata?.season_number || '').trim()
}

function getRunClass(item) {
  return String(item?.summary?.run_class || item?.run_metadata?.run_class || '').trim()
}

function isEarlyStandardRun(item) {
  const runClass = getRunClass(item)
  const duration = Number(item?.summary?.duration_hours || 0)
  return runClass === 'standard_72h' && Number.isFinite(duration) && duration > 0 && duration < 60
}

function getRunEndedMs(item) {
  const value = item?.summary?.run_ended_at || item?.summary?.generated_at_utc || item?.run_metadata?.ended_at
  const date = new Date(value)
  const timestamp = date.getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

function getCanaryLetter(item) {
  const source = `${getRunId(item)} ${getRunCondition(item)}`.toLowerCase()
  const match = source.match(/\bcanary[-_\s]*([a-z])\b/)
  return match ? match[1].toUpperCase() : ''
}

function getComparisonLabel(group) {
  if (group.kind === 'canary') {
    return `${group.letters.join(' / ')} Canary Comparison`
  }
  if (group.condition) {
    return `${formatLabel(group.condition)} Replicates`
  }
  return `Season ${group.season} Completed Runs`
}

function buildComparisonGroups(items) {
  const visibleItems = Array.isArray(items) ? items.filter((item) => getRunId(item)) : []
  const canaryItems = visibleItems
    .map((item) => ({ item, letter: getCanaryLetter(item) }))
    .filter(({ letter }) => letter)
    .sort((a, b) => a.letter.localeCompare(b.letter))

  const canaryGroups = []
  for (let index = 0; index < canaryItems.length - 1; index += 1) {
    const current = canaryItems[index]
    const next = canaryItems[index + 1]
    if (!current || !next) continue
    const adjacent = next.letter.charCodeAt(0) - current.letter.charCodeAt(0) === 1
    const hiPair = current.letter === 'H' && next.letter === 'I'
    if (!adjacent && !hiPair) continue
    canaryGroups.push({
      key: `canary-${current.letter}-${next.letter}`,
      kind: 'canary',
      letters: [current.letter, next.letter],
      items: [current.item, next.item],
    })
  }

  const grouped = new Map()
  visibleItems.forEach((item) => {
    const condition = getRunCondition(item)
    const season = getRunSeason(item)
    const key = condition ? `condition:${condition}` : (season ? `season:${season}` : '')
    if (!key) return
    const bucket = grouped.get(key) || {
      key,
      kind: condition ? 'condition' : 'season',
      condition,
      season,
      items: [],
    }
    bucket.items.push(item)
    grouped.set(key, bucket)
  })

  const relatedGroups = Array.from(grouped.values())
    .map((group) => ({
      ...group,
      items: [...group.items].sort((a, b) => getRunEndedMs(b) - getRunEndedMs(a)).slice(0, 2),
    }))
    .filter((group) => group.items.length >= 2)

  const seen = new Set()
  return [...canaryGroups, ...relatedGroups]
    .filter((group) => {
      const ids = group.items.map(getRunId).sort().join('|')
      if (seen.has(ids)) return false
      seen.add(ids)
      return true
    })
    .slice(0, 3)
}

export default function Reports() {
  const location = useLocation()
  const [archive, setArchive] = useState(null)
  const [includeTuning, setIncludeTuning] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    trackKpiEventOnce('archive_view', 'archive', {
      surface: 'archive',
      target: 'archive_page',
      metadata: { route: String(location.pathname || '') },
    })
  }, [location.pathname])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const payload = await api.getRunsArchive(60, includeTuning)
        if (!cancelled) {
          setArchive(payload && typeof payload === 'object' ? payload : null)
        }
      } catch (loadError) {
        if (!cancelled) {
          setArchive(null)
          setError(loadError?.message || 'Failed to load runs archive')
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
  }, [includeTuning])

  function getArtifactUrl(runId, artifactType, artifact, action) {
    const format = preferredFormat(artifact)
    if (!runId || !artifact?.available || !format) return ''
    return action === 'download'
      ? api.getRunReportDownloadUrl(runId, artifactType, format)
      : api.getRunReportViewUrl(runId, artifactType, format)
  }

  function getArtifactViewPath(runId, artifactType, artifact) {
    const format = preferredFormat(artifact)
    if (!runId || !artifact?.available || !format) return ''
    return `/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(artifactType)}?format=${encodeURIComponent(format)}`
  }

  const items = Array.isArray(archive?.items) ? archive.items : []
  const stats = archive?.stats || {}
  const hiddenTuningCount = Number(archive?.hidden_tuning_count || 0)
  const legacyReportsRoute = String(location.pathname || '').trim() === '/reports'
  const comparisonGroups = buildComparisonGroups(items)
  const archiveModeLabel = includeTuning ? 'All Archived Runs' : 'Public Archive'
  const nextScheduledRun = getNextScheduledRun()

  return (
    <div className="reports-page archive-page">
      <div className="page-header">
        <h1>
          <FileSearch size={30} />
          Archive
        </h1>
        <p className="page-description">
          Completed runs with one path into replay, evidence, and report artifacts.
        </p>
      </div>

      {error && <div className="feed-notice">{error}</div>}
      {!error && legacyReportsRoute && (
        <div className="feed-notice">
          Reports now live inside Archive. This route is kept for old links.
        </div>
      )}
      {!error && hiddenTuningCount > 0 && (
        <div className="feed-notice">
          {hiddenTuningCount} tuning run{hiddenTuningCount === 1 ? '' : 's'} hidden from the public archive.
        </div>
      )}
      {!error && includeTuning && (
        <div className="feed-notice">
          Tuning and exploratory closeouts are included in this operator view.
        </div>
      )}

      {nextScheduledRun && (
        <RunBriefCard
          run={nextScheduledRun}
          variant="compact"
          heading="Next scheduled run"
          actionMode="calendar"
          analyticsSurface="archive_next_run"
        />
      )}

      <div className="message-tabs archive-mode-tabs">
        <button type="button" className={`tab-btn ${!includeTuning ? 'active' : ''}`} onClick={() => setIncludeTuning(false)}>
          Public Archive
        </button>
        <button type="button" className={`tab-btn ${includeTuning ? 'active' : ''}`} onClick={() => setIncludeTuning(true)}>
          Include Tuning Runs
        </button>
      </div>

      <div className="stats-grid archive-stats-grid">
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">{includeTuning ? 'All Runs' : 'Public Runs'}</span>
            <div className="stat-icon blue">
              <FileSearch size={18} />
            </div>
          </div>
          <div className="stat-value">{Number(stats.completed_runs || 0).toLocaleString()}</div>
          <div className="stat-change">
            <span>{archiveModeLabel} with archived closeout bundles</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Visible Events</span>
            <div className="stat-icon orange">
              <TimerReset size={18} />
            </div>
          </div>
          <div className="stat-value">{Number(stats.total_events || 0).toLocaleString()}</div>
          <div className="stat-change">
            <span>Scoped event count across archived runs</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Visible LLM Calls</span>
            <div className="stat-icon green">
              <RefreshCw size={18} />
            </div>
          </div>
          <div className="stat-value">{Number(stats.llm_calls || 0).toLocaleString()}</div>
          <div className="stat-change">
            <span>Total archived-model turns</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Visible Cost</span>
            <div className="stat-icon purple">
              <Download size={18} />
            </div>
          </div>
          <div className="stat-value">{formatUsd(stats.estimated_cost_usd || 0)}</div>
          <div className="stat-change">
            <span>Archive-wide inferred API cost</span>
          </div>
        </div>
      </div>

      {!loading && comparisonGroups.length > 0 && (
        <div className="card archive-comparison-card">
          <div className="card-header">
            <h3>Related Run Comparisons</h3>
            <span className="strip-meta">{comparisonGroups.length} available</span>
          </div>
          <div className="card-body archive-comparison-list">
            {comparisonGroups.map((group) => (
              <div key={group.key} className="archive-comparison-row">
                <div className="archive-comparison-main">
                  <strong>{getComparisonLabel(group)}</strong>
                  <span>Open replays side by side and inspect evidence before drawing conclusions.</span>
                </div>
                <div className="archive-comparison-runs">
                  {group.items.map((item) => {
                    const runId = getRunId(item)
                    const metrics = item?.summary?.metrics || {}
                    return (
                      <div key={runId} className="archive-comparison-run">
                        <div>
                          <strong>{runId}</strong>
                          <span>
                            {formatLabel(getRunCondition(item) || 'unknown condition')} · {Number(metrics.deaths || 0)} deaths · {Number(metrics.laws_passed || 0)} laws
                          </span>
                        </div>
                        <div className="archive-comparison-actions">
                          <Link
                            to={getStoryReplayHref(runId)}
                            className="btn btn-secondary"
                            onClick={() => trackArchivePathClick(runId, 'comparison_replay')}
                          >
                            Replay
                          </Link>
                          <Link
                            to={`/runs/${encodeURIComponent(runId)}`}
                            className="btn btn-secondary"
                            onClick={() => trackArchivePathClick(runId, 'comparison_evidence')}
                          >
                            Evidence
                          </Link>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>Completed Run Index</h3>
          <span className="strip-meta">
            {loading ? 'Loading…' : `${items.length} visible`}
          </span>
        </div>
        <div className="card-body">
          {loading && <div className="empty-state">Loading archived runs…</div>}
          {!loading && items.length === 0 && (
            <div className="empty-state">No completed runs have been archived yet.</div>
          )}
          {!loading && items.length > 0 && (
            <div className="archive-run-list">
              {items.map((item, index) => {
                const runId = String(item?.run_id || '').trim()
                const summary = item?.summary || {}
                const metrics = summary?.metrics || {}
                const runMetadata = item?.run_metadata || {}
                const artifacts = item?.artifacts || {}
                const takeaway = getRunTakeaway(item)
                const isLatestPublicRun = !includeTuning && index === 0
                const scheduledRun = getScheduleEntryForRunId(runId)
                const reportLinks = ARCHIVE_REPORT_ARTIFACTS
                  .map(([artifactType, label]) => ({
                    artifactType,
                    label,
                    artifact: artifacts[artifactType],
                  }))
                  .filter(({ artifact }) => artifact?.available && preferredFormat(artifact))
                const latestViewerBriefArtifact = artifacts.viewer_brief
                const latestViewerBriefAvailable = Boolean(
                  isLatestPublicRun
                  && latestViewerBriefArtifact?.available
                  && preferredFormat(latestViewerBriefArtifact),
                )
                const primaryActionPath = latestViewerBriefAvailable
                  ? getArtifactViewPath(runId, 'viewer_brief', latestViewerBriefArtifact)
                  : `/runs/${encodeURIComponent(runId)}/replay?tab=overview`
                const primaryActionLabel = latestViewerBriefAvailable
                  ? 'Read The Brief'
                  : (isLatestPublicRun ? 'Start With Latest Recap' : 'Open Recap')
                const primaryActionTarget = latestViewerBriefAvailable ? 'report:viewer_brief:primary' : 'recap'
                const visibleReportLinks = latestViewerBriefAvailable
                  ? reportLinks.filter(({ artifactType }) => artifactType !== 'viewer_brief')
                  : reportLinks

                return (
                  <article key={runId} className={`archive-run-card ${isLatestPublicRun ? 'latest' : ''}`}>
                    <div className="archive-run-card-head">
                      <div>
                        <div className="archive-run-title-row">
                          <h3>{runId}</h3>
                          {isLatestPublicRun && <span>Latest completed run</span>}
                        </div>
                        <p>
                          Ended {formatTimestamp(summary.run_ended_at)} · {formatDuration(summary.duration_hours)}
                        </p>
                      </div>
                      <Link
                        to={primaryActionPath}
                        className="btn btn-primary"
                        onClick={() => trackArchivePathClick(runId, primaryActionTarget, { latest: isLatestPublicRun })}
                      >
                        {latestViewerBriefAvailable ? <FileSearch size={14} /> : <TimerReset size={14} />}
                        {primaryActionLabel}
                      </Link>
                    </div>

                    {takeaway && (
                      <p className="archive-run-takeaway">{takeaway}</p>
                    )}

                    {scheduledRun && (
                      <div className="archive-run-schedule-context">
                        <div>
                          <span>Declared question</span>
                          <strong>{scheduledRun.declaredQuestion}</strong>
                        </div>
                        <div>
                          <span>Claim boundary</span>
                          <strong>{scheduledRun.claimBoundary}</strong>
                        </div>
                        {scheduledRun.resultNote && (
                          <div>
                            <span>Result note</span>
                            <strong>{scheduledRun.resultNote}</strong>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="archive-run-meta">
                      <span>{formatLabel(runMetadata.run_mode || 'archived')}</span>
                      <span>{formatLabel(summary.condition_name || runMetadata.condition_name || 'unknown condition')}</span>
                      <span>Season {summary.season_number || runMetadata.season_number || 'n/a'}</span>
                      <span>{formatLabel(getRunClass(item) || 'unspecified')}</span>
                      <span>{Number(summary.replicate_count || 1)} replicate(s)</span>
                      {isEarlyStandardRun(item) && <span>Ended Early</span>}
                    </div>

                    <div className="archive-run-stats">
                      <div>
                        <span>Events</span>
                        <strong>{Number(metrics.total_events || 0).toLocaleString()}</strong>
                      </div>
                      <div>
                        <span>LLM Calls</span>
                        <strong>{Number(metrics.llm_calls || 0).toLocaleString()}</strong>
                      </div>
                      <div>
                        <span>Deaths</span>
                        <strong>{Number(metrics.deaths || 0).toLocaleString()}</strong>
                      </div>
                      <div>
                        <span>Cost</span>
                        <strong>{formatUsd(metrics.estimated_cost_usd || 0)}</strong>
                      </div>
                    </div>

                    <div className="archive-run-actions">
                      <Link
                        className="btn btn-secondary"
                        to={getStoryReplayHref(runId)}
                        onClick={() => trackArchivePathClick(runId, 'replay')}
                      >
                        <TimerReset size={14} />
                        Replay
                      </Link>
                      <Link
                        className="btn btn-secondary"
                        to={`/runs/${encodeURIComponent(runId)}`}
                        onClick={() => trackArchivePathClick(runId, 'evidence', { latest: isLatestPublicRun })}
                      >
                        <FileSearch size={14} />
                        {isLatestPublicRun ? 'Latest Run Details' : 'Evidence'}
                      </Link>
                      {visibleReportLinks.map(({ artifactType, label, artifact }) => (
                        <div key={artifactType} className="archive-report-action">
                          <Link
                            className="btn btn-secondary"
                            to={getArtifactViewPath(runId, artifactType, artifact)}
                            title={`Open ${label}`}
                            onClick={() => trackArchivePathClick(runId, `report:${artifactType}`)}
                          >
                            <FileSearch size={14} />
                            {label}
                          </Link>
                          <a
                            className="btn btn-secondary btn-icon-only"
                            href={getArtifactUrl(runId, artifactType, artifact, 'download')}
                            title={`Download ${label}`}
                          >
                            <Download size={14} />
                            <span className="sr-only">Download {label}</span>
                          </a>
                        </div>
                      ))}
                    </div>

                    <div className="archive-run-foot">
                      <span>Summary generated {formatDate(summary.generated_at_utc)}</span>
                      <span>
                        Reports: {reportLinks.length || 0} available
                      </span>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
