import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Download,
  FileSearch,
  FileText,
  RefreshCw,
  TimerReset,
} from 'lucide-react'
import { api } from '../services/api'
import { getStoryReplayHref } from '../utils/bestMoments'

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

function getRunCondition(item) {
  return String(item?.summary?.condition_name || item?.run_metadata?.condition_name || '').trim()
}

function getRunSeason(item) {
  return String(item?.summary?.season_number || item?.run_metadata?.season_number || '').trim()
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const payload = await api.getRunsArchive(60)
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
  }, [])

  function openArtifact(runId, artifactType, artifact) {
    const format = preferredFormat(artifact)
    if (!runId || !artifact?.available || !format) return
    const href = api.getRunReportDownloadUrl(runId, artifactType, format)
    window.open(href, '_blank', 'noopener,noreferrer')
  }

  const items = Array.isArray(archive?.items) ? archive.items : []
  const stats = archive?.stats || {}
  const activeRunId = String(archive?.active_run_id || '').trim()
  const hiddenTuningCount = Number(archive?.hidden_tuning_count || 0)
  const legacyReportsRoute = String(location.pathname || '').trim() === '/reports'
  const comparisonGroups = buildComparisonGroups(items)

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

      {activeRunId && (
        <div className="card archive-current-run-card">
          <div className="card-body archive-current-run-body">
            <div>
              <strong>Current live run</strong>
              <p>{activeRunId} stays on the live tabs. Completed runs move here after closeout.</p>
            </div>
            <div className="archive-current-run-actions">
              <Link to="/dashboard" className="btn btn-primary">
                Current Run
              </Link>
              <Link to={getStoryReplayHref(activeRunId)} className="btn btn-secondary">
                Live Replay
              </Link>
              <Link to={`/runs/${encodeURIComponent(activeRunId)}`} className="btn btn-secondary">
                Live Evidence
              </Link>
            </div>
          </div>
        </div>
      )}

      <div className="stats-grid archive-stats-grid">
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Completed Runs</span>
            <div className="stat-icon blue">
              <FileSearch size={18} />
            </div>
          </div>
          <div className="stat-value">{Number(stats.completed_runs || 0).toLocaleString()}</div>
          <div className="stat-change">
            <span>Runs with archived closeout bundles</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-header">
            <span className="stat-label">Total Events</span>
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
            <span className="stat-label">LLM Calls</span>
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
            <span className="stat-label">Estimated Cost</span>
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
                          <Link to={getStoryReplayHref(runId)} className="btn btn-secondary">
                            Replay
                          </Link>
                          <Link to={`/runs/${encodeURIComponent(runId)}`} className="btn btn-secondary">
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
              {items.map((item) => {
                const runId = String(item?.run_id || '').trim()
                const summary = item?.summary || {}
                const metrics = summary?.metrics || {}
                const runMetadata = item?.run_metadata || {}
                const artifacts = item?.artifacts || {}
                const researchArtifact = artifacts.approachable_report
                const technicalArtifact = artifacts.technical_report
                const takeaway = getRunTakeaway(item)

                return (
                  <article key={runId} className="archive-run-card">
                    <div className="archive-run-card-head">
                      <div>
                        <h3>{runId}</h3>
                        <p>
                          Ended {formatTimestamp(summary.run_ended_at)} · {formatDuration(summary.duration_hours)}
                        </p>
                      </div>
                      <Link to={getStoryReplayHref(runId)} className="btn btn-primary">
                        <TimerReset size={14} />
                        Open Replay
                      </Link>
                    </div>

                    {takeaway && (
                      <p className="archive-run-takeaway">{takeaway}</p>
                    )}

                    <div className="archive-run-meta">
                      <span>{formatLabel(runMetadata.run_mode || 'archived')}</span>
                      <span>{formatLabel(summary.condition_name || runMetadata.condition_name || 'unknown condition')}</span>
                      <span>Season {summary.season_number || runMetadata.season_number || 'n/a'}</span>
                      <span>{formatLabel(summary.run_class || runMetadata.run_class || 'unspecified')}</span>
                      <span>{Number(summary.replicate_count || 1)} replicate(s)</span>
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
                        to={`/runs/${encodeURIComponent(runId)}`}
                      >
                        <FileSearch size={14} />
                        Evidence
                      </Link>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={!researchArtifact?.available}
                        onClick={() => openArtifact(runId, 'approachable_report', researchArtifact)}
                      >
                        <Download size={14} />
                        Research Report
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={!technicalArtifact?.available}
                        onClick={() => openArtifact(runId, 'technical_report', technicalArtifact)}
                      >
                        <Download size={14} />
                        Technical Report
                      </button>
                    </div>

                    <div className="archive-run-foot">
                      <span>Summary generated {formatDate(summary.generated_at_utc)}</span>
                      <span>
                        Research: {preferredFormat(researchArtifact) || 'n/a'} · Technical: {preferredFormat(technicalArtifact) || 'n/a'}
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
