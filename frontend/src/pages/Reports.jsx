import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  FileSearch,
  RefreshCw,
  Download,
  ExternalLink,
  Hash,
  Layers,
} from 'lucide-react'
import { api } from '../services/api'
import GlossaryTooltip from '../components/GlossaryTooltip'

function formatTimestamp(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return date.toLocaleString()
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function Reports() {
  const [runIdInput, setRunIdInput] = useState('')
  const [conditionInput, setConditionInput] = useState('')
  const [runReports, setRunReports] = useState(null)
  const [conditionReports, setConditionReports] = useState(null)
  const [loadingRun, setLoadingRun] = useState(false)
  const [loadingCondition, setLoadingCondition] = useState(false)
  const [error, setError] = useState('')

  const activeRunId = useMemo(() => String(runReports?.run_id || '').trim(), [runReports])
  const activeCondition = useMemo(
    () => String(conditionReports?.condition_name || '').trim(),
    [conditionReports]
  )

  async function loadRunReports() {
    const cleanRunId = String(runIdInput || '').trim()
    if (!cleanRunId) {
      setError('Run ID is required')
      return
    }
    setError('')
    setLoadingRun(true)
    try {
      const payload = await api.getRunReports(cleanRunId)
      setRunReports(payload || null)
    } catch (loadError) {
      setError(loadError?.message || 'Failed to load run reports')
      setRunReports(null)
    } finally {
      setLoadingRun(false)
    }
  }

  async function loadConditionReports() {
    const cleanCondition = String(conditionInput || '').trim()
    if (!cleanCondition) {
      setError('Condition is required')
      return
    }
    setError('')
    setLoadingCondition(true)
    try {
      const payload = await api.getConditionReports(cleanCondition)
      setConditionReports(payload || null)
    } catch (loadError) {
      setError(loadError?.message || 'Failed to load condition reports')
      setConditionReports(null)
    } finally {
      setLoadingCondition(false)
    }
  }

  function openRunDownload(item) {
    const href = api.getRunReportDownloadUrl(
      activeRunId,
      String(item?.artifact_type || ''),
      String(item?.artifact_format || 'json')
    )
    window.open(href, '_blank', 'noopener,noreferrer')
  }

  function openConditionDownload(item) {
    const href = api.getConditionReportDownloadUrl(
      activeCondition,
      String(item?.artifact_format || 'json')
    )
    window.open(href, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="reports-page">
      <div className="page-header">
        <h1>
          <FileSearch size={30} />
          Reports
        </h1>
        <p className="page-description">
          Viewer-facing artifact index for
          {' '}
          <GlossaryTooltip termKey="run">run</GlossaryTooltip>
          {' '}
          summaries and
          {' '}
          <GlossaryTooltip termKey="condition">condition</GlossaryTooltip>
          {' '}
          comparisons.
        </p>
      </div>

      {error && <div className="feed-notice">{error}</div>}

      <div className="reports-filters">
        <div className="card reports-filter-card">
          <div className="card-header">
            <h3>
              <Hash size={16} />
              <GlossaryTooltip termKey="run">Run</GlossaryTooltip>
              {' '}
              Reports
            </h3>
          </div>
          <div className="card-body reports-filter-body">
            <label htmlFor="reports-run-id">Run ID</label>
            <input
              id="reports-run-id"
              type="text"
              value={runIdInput}
              onChange={(event) => setRunIdInput(event.target.value)}
              placeholder="real-pilot-20260211T063855Z"
            />
            <button type="button" className="btn btn-primary" onClick={loadRunReports} disabled={loadingRun}>
              {loadingRun ? (
                <>
                  <RefreshCw size={14} className="reports-spin" />
                  Loading
                </>
              ) : (
                'Load Run Reports'
              )}
            </button>
            {activeRunId && (
              <Link to={`/runs/${encodeURIComponent(activeRunId)}`} className="btn btn-secondary">
                Open Run Detail
              </Link>
            )}
          </div>
        </div>

        <div className="card reports-filter-card">
          <div className="card-header">
            <h3>
              <Layers size={16} />
              <GlossaryTooltip termKey="condition">Condition</GlossaryTooltip>
              {' '}
              Reports
            </h3>
          </div>
          <div className="card-body reports-filter-body">
            <label htmlFor="reports-condition-name">Condition</label>
            <input
              id="reports-condition-name"
              type="text"
              value={conditionInput}
              onChange={(event) => setConditionInput(event.target.value)}
              placeholder="baseline_v1"
            />
            <button
              type="button"
              className="btn btn-primary"
              onClick={loadConditionReports}
              disabled={loadingCondition}
            >
              {loadingCondition ? (
                <>
                  <RefreshCw size={14} className="reports-spin" />
                  Loading
                </>
              ) : (
                'Load Condition Reports'
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="reports-grid">
        <div className="card">
          <div className="card-header">
            <h3>Run Artifact Registry</h3>
            <span className="strip-meta">{Number(runReports?.count || 0)} artifacts</span>
          </div>
          <div className="card-body">
            {loadingRun && <div className="empty-state compact">Loading run artifacts…</div>}
            {!loadingRun && (!runReports || Number(runReports?.count || 0) === 0) && (
              <div className="empty-state compact">No run artifacts loaded yet.</div>
            )}
            {!loadingRun && Array.isArray(runReports?.items) && runReports.items.length > 0 && (
              <div className="reports-list">
                {runReports.items.map((item) => (
                  <div key={item.id} className="reports-item">
                    <div className="reports-item-main">
                      <strong>{formatLabel(item.artifact_type)}</strong>
                      <span>{String(item.artifact_format || '').toUpperCase()}</span>
                      <span>Status: {item.status}</span>
                      <span>Updated: {formatTimestamp(item.updated_at)}</span>
                    </div>
                    <div className="reports-item-actions">
                      <button type="button" className="btn btn-secondary" onClick={() => openRunDownload(item)}>
                        <Download size={14} />
                        Download
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Condition Comparison Registry</h3>
            <span className="strip-meta">{Number(conditionReports?.count || 0)} artifacts</span>
          </div>
          <div className="card-body">
            {loadingCondition && <div className="empty-state compact">Loading condition artifacts…</div>}
            {!loadingCondition && (!conditionReports || Number(conditionReports?.count || 0) === 0) && (
              <div className="empty-state compact">No condition artifacts loaded yet.</div>
            )}
            {!loadingCondition &&
              Array.isArray(conditionReports?.items) &&
              conditionReports.items.length > 0 && (
                <div className="reports-list">
                  {conditionReports.items.map((item) => {
                    const metadata = item?.metadata || {}
                    return (
                      <div key={item.id} className="reports-item">
                        <div className="reports-item-main">
                          <strong>{String(item.artifact_format || '').toUpperCase()}</strong>
                          <span>
                            <GlossaryTooltip termKey="replicate">Replicates</GlossaryTooltip>
                            : {Number(metadata.replicate_count || 0)}
                          </span>
                          <span>
                            Threshold met: {metadata.meets_replicate_threshold ? 'yes' : 'no'}
                          </span>
                          <span>Updated: {formatTimestamp(item.updated_at)}</span>
                        </div>
                        <div className="reports-item-actions">
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => openConditionDownload(item)}
                          >
                            <Download size={14} />
                            Download
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Transparency Endpoints</h3>
          <span className="strip-meta">Direct API access</span>
        </div>
        <div className="card-body reports-links">
          {activeRunId && (
            <a
              href={`${api.baseUrl}/api/reports/runs/${encodeURIComponent(activeRunId)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
            >
              Run Registry JSON <ExternalLink size={14} />
            </a>
          )}
          {activeCondition && (
            <a
              href={`${api.baseUrl}/api/reports/conditions/${encodeURIComponent(activeCondition)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
            >
              Condition Registry JSON <ExternalLink size={14} />
            </a>
          )}
          {!activeRunId && !activeCondition && (
            <div className="empty-state compact">Load a run ID or condition to expose direct endpoints.</div>
          )}
        </div>
      </div>
    </div>
  )
}
