import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Download,
  FileSearch,
  FileText,
  RefreshCw,
  TimerReset,
} from 'lucide-react'
import { api } from '../services/api'

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

export default function Reports() {
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

  return (
    <div className="reports-page archive-page">
      <div className="page-header">
        <h1>
          <FileSearch size={30} />
          Runs Archive
        </h1>
        <p className="page-description">
          Completed runs, top-line closeout stats, and direct links into recap, replay story, and report artifacts.
        </p>
      </div>

      {error && <div className="feed-notice">{error}</div>}
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
              <Link to="/highlights" className="btn btn-primary">
                Open Live Highlights
              </Link>
              <Link to={`/runs/${encodeURIComponent(activeRunId)}`} className="btn btn-secondary">
                Open Run Detail
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

                return (
                  <article key={runId} className="archive-run-card">
                    <div className="archive-run-card-head">
                      <div>
                        <h3>{runId}</h3>
                        <p>
                          Ended {formatTimestamp(summary.run_ended_at)} · {formatDuration(summary.duration_hours)}
                        </p>
                      </div>
                      <Link to={`/runs/${encodeURIComponent(runId)}`} className="btn btn-secondary">
                        Run Detail
                      </Link>
                    </div>

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
                        to={`/highlights?tab=replay&mode=story60&run=${encodeURIComponent(runId)}`}
                        className="btn btn-primary"
                      >
                        <TimerReset size={14} />
                        Replay Story
                      </Link>
                      <Link
                        to={`/highlights?tab=recap&run=${encodeURIComponent(runId)}`}
                        className="btn btn-secondary"
                      >
                        <FileText size={14} />
                        Run Recap
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
