import { useEffect, useMemo, useState } from 'react'
import {
  Shield,
  ShieldAlert,
  RefreshCw,
  PauseCircle,
  PlayCircle,
  Power,
  Rocket,
  Save,
  Loader2,
  Plus,
  FilePenLine,
  Trash2,
  Upload,
  EyeOff,
  WandSparkles,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api } from '../services/api'

const TOKEN_STORAGE_KEY = 'emergence_admin_token'
const USER_STORAGE_KEY = 'emergence_admin_user'

const EMPTY_ARTICLE_EDITOR = {
  id: null,
  slug: '',
  title: '',
  summary: '',
  publishedAt: '',
  status: 'draft',
  sectionsText: JSON.stringify(
    [
      {
        heading: '',
        paragraphs: [''],
        references: [],
      },
    ],
    null,
    2
  ),
}

function slugify(rawValue) {
  return String(rawValue || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function toArticleEditor(article) {
  if (!article) return { ...EMPTY_ARTICLE_EDITOR }
  return {
    id: Number(article.id),
    slug: String(article.slug || ''),
    title: String(article.title || ''),
    summary: String(article.summary || ''),
    publishedAt: String(article.published_at || ''),
    status: String(article.status || 'draft'),
    sectionsText: JSON.stringify(Array.isArray(article.sections) ? article.sections : [], null, 2),
  }
}

function validateAndParseSections(sectionsText) {
  let parsed = null
  try {
    parsed = JSON.parse(String(sectionsText || '[]'))
  } catch {
    return { error: 'Sections JSON is invalid', sections: null }
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    return { error: 'Sections must be a non-empty array', sections: null }
  }
  for (const section of parsed) {
    const heading = String(section?.heading || '').trim()
    const paragraphs = Array.isArray(section?.paragraphs)
      ? section.paragraphs.map((paragraph) => String(paragraph).trim()).filter(Boolean)
      : []
    if (!heading || paragraphs.length === 0) {
      return { error: 'Every section must include a heading and at least one paragraph', sections: null }
    }
  }
  return { error: '', sections: parsed }
}

function stringifyValue(value) {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function parseByType(rawValue, type) {
  if (type === 'bool') {
    return Boolean(rawValue)
  }
  if (type === 'int') {
    const parsed = Number.parseInt(String(rawValue), 10)
    return Number.isFinite(parsed) ? parsed : null
  }
  if (type === 'float') {
    const parsed = Number.parseFloat(String(rawValue))
    return Number.isFinite(parsed) ? parsed : null
  }
  return String(rawValue ?? '').trim()
}

function formatApiError(error, fallback = 'Request failed') {
  if (!error) return fallback
  return error.message || fallback
}

export default function Ops() {
  const [tokenInput, setTokenInput] = useState(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
  const [token, setToken] = useState(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
  const [adminUser, setAdminUser] = useState(localStorage.getItem(USER_STORAGE_KEY) || 'ops-ui')

  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [audit, setAudit] = useState([])
  const [runMetrics, setRunMetrics] = useState(null)
  const [runIdInput, setRunIdInput] = useState('')
  const [runControlReason, setRunControlReason] = useState('')
  const [resetOnTestStart, setResetOnTestStart] = useState(true)

  const [draftValues, setDraftValues] = useState({})
  const [reason, setReason] = useState('')

  const [loading, setLoading] = useState(false)
  const [submittingConfig, setSubmittingConfig] = useState(false)
  const [controlAction, setControlAction] = useState('')

  const [error, setError] = useState('')
  const [metricsWarning, setMetricsWarning] = useState('')
  const [notice, setNotice] = useState('')
  const [adminArticles, setAdminArticles] = useState([])
  const [articleEditor, setArticleEditor] = useState({ ...EMPTY_ARTICLE_EDITOR })
  const [articleAction, setArticleAction] = useState('')

  const connected = Boolean(token.trim())
  const writeEnabled = Boolean(config?.admin_write_enabled)
  const environment = String(config?.environment || status?.environment || 'unknown').toUpperCase()
  const isProduction = environment === 'PRODUCTION'

  useEffect(() => {
    localStorage.setItem(USER_STORAGE_KEY, adminUser)
  }, [adminUser])

  const loadOpsData = async () => {
    if (!connected) return
    setLoading(true)
    setError('')
    setMetricsWarning('')

    try {
      const [statusResponse, configResponse, auditResponse, articlesResponse] = await Promise.all([
        api.getAdminStatus(token, adminUser),
        api.getAdminConfig(token, adminUser),
        api.getAdminAudit(token, 50, 0, adminUser),
        api.getAdminArchiveArticles(token, adminUser),
      ])
      const activeRunId = String(statusResponse?.viewer_ops?.run_id || '').trim()
      let runMetricsResponse = null
      try {
        runMetricsResponse = await api.getAdminRunMetrics(token, activeRunId, 24, adminUser)
      } catch (runMetricsError) {
        setMetricsWarning(formatApiError(runMetricsError, 'Run metrics are temporarily unavailable'))
      }

      setStatus(statusResponse)
      setConfig(configResponse)
      setAudit(Array.isArray(auditResponse?.items) ? auditResponse.items : [])
      const resolvedArticles = Array.isArray(articlesResponse?.items) ? articlesResponse.items : []
      setAdminArticles(resolvedArticles)
      if (!articleEditor.id && resolvedArticles.length > 0) {
        setArticleEditor(toArticleEditor(resolvedArticles[0]))
      }
      setRunMetrics(runMetricsResponse)
      setRunIdInput(activeRunId)
      setResetOnTestStart(String(configResponse?.environment || statusResponse?.environment || '').toLowerCase() !== 'production')
      setDraftValues(configResponse?.effective || {})
    } catch (loadError) {
      setError(formatApiError(loadError, 'Failed to load admin data'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOpsData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const invalidFields = useMemo(() => {
    if (!config?.mutable_keys) return []
    const keys = Object.keys(config.mutable_keys)
    return keys.filter((key) => {
      const spec = config.mutable_keys[key]
      if (!spec) return false
      if (spec.type !== 'int' && spec.type !== 'float') return false
      return parseByType(draftValues[key], spec.type) === null
    })
  }, [config, draftValues])

  const pendingUpdates = useMemo(() => {
    if (!config?.mutable_keys || !config?.effective) return {}

    const updates = {}
    for (const [key, spec] of Object.entries(config.mutable_keys)) {
      const nextValue = parseByType(draftValues[key], spec.type)
      const currentValue = config.effective[key]

      if (nextValue === null && (spec.type === 'int' || spec.type === 'float')) {
        continue
      }

      if (JSON.stringify(nextValue) !== JSON.stringify(currentValue)) {
        updates[key] = nextValue
      }
    }

    return updates
  }, [config, draftValues])

  const pendingCount = Object.keys(pendingUpdates).length

  const onConnect = (event) => {
    event.preventDefault()
    const cleanToken = tokenInput.trim()
    setNotice('')
    setError('')

    if (!cleanToken) {
      setToken('')
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      setMetricsWarning('')
      return
    }

    localStorage.setItem(TOKEN_STORAGE_KEY, cleanToken)
    setToken(cleanToken)
  }

  const onApplyConfig = async () => {
    if (!connected || !writeEnabled || pendingCount === 0 || invalidFields.length > 0) return

    setSubmittingConfig(true)
    setNotice('')
    setError('')

    try {
      await api.updateAdminConfig(token, pendingUpdates, reason, adminUser)
      setReason('')
      setNotice('Config updates applied')
      await loadOpsData()
    } catch (updateError) {
      setError(formatApiError(updateError, 'Failed to apply config'))
    } finally {
      setSubmittingConfig(false)
    }
  }

  const onRunControl = async (actionId, actionFn, successMessage) => {
    if (!connected || !writeEnabled) return

    setControlAction(actionId)
    setNotice('')
    setError('')

    try {
      const response = await actionFn()
      const resolvedMessage = typeof successMessage === 'function' ? successMessage(response) : successMessage
      setNotice(resolvedMessage || 'Action completed')
      await loadOpsData()
    } catch (controlError) {
      setError(formatApiError(controlError, 'Control action failed'))
    } finally {
      setControlAction('')
    }
  }

  const startRun = async (mode) => {
    if (isProduction) {
      setError('Start actions are disabled in production from this UI')
      return
    }

    const reasonText = String(runControlReason || '').trim()
    const runId = String(runIdInput || '').trim()
    const shouldReset = mode === 'test' && resetOnTestStart
    const actionId = mode === 'test' ? 'start-test' : 'start-real'
    const modeLabel = mode === 'test' ? 'test' : 'real'

    if (mode === 'real' && !window.confirm('Start REAL run now? This enables live simulation traffic.')) {
      return
    }
    if (mode === 'test' && shouldReset && !window.confirm('Start TEST run and reset/reseed world first? This is destructive for dev state.')) {
      return
    }

    await onRunControl(
      actionId,
      () =>
        api.startSimulationRun(
          token,
          {
            mode,
            run_id: runId,
            reset_world: shouldReset,
            reason: reasonText || `ops_ui_start_${mode}`,
          },
          adminUser
        ),
      (result) => `${modeLabel.toUpperCase()} run started${result?.run_id ? ` (${result.run_id})` : ''}`
    )
  }

  const stopRun = async () => {
    if (!simulationActive || paused) {
      setNotice('Run is already paused')
      return
    }
    if (!window.confirm('Pause the active run now?')) {
      return
    }

    const reasonText = String(runControlReason || '').trim()
    await onRunControl(
      'stop-run',
      () =>
        api.stopSimulationRun(
          token,
          {
            clear_run_id: false,
            reason: reasonText || 'ops_ui_stop_run',
          },
          adminUser
        ),
      (result) => `Run paused${result?.run_id ? ` (${result.run_id})` : ''}`
    )
  }

  const resetDev = async () => {
    if (isProduction) {
      setError('Reset Dev World is disabled in production')
      return
    }
    if (!window.confirm('Reset and reseed the dev world now? This will wipe current world state.')) {
      return
    }

    const reasonText = String(runControlReason || '').trim()
    await onRunControl(
      'reset-dev',
      () => api.resetDevWorld(token, reasonText || 'ops_ui_reset_dev', adminUser),
      'Dev world reset + reseeded'
    )
  }

  const onNewArticle = () => {
    setArticleEditor({ ...EMPTY_ARTICLE_EDITOR })
  }

  const onSelectArticle = (article) => {
    setArticleEditor(toArticleEditor(article))
  }

  const onAutofillSlug = () => {
    setArticleEditor((prev) => ({ ...prev, slug: slugify(prev.title) }))
  }

  const onSaveArticle = async (nextStatus = 'draft') => {
    if (!connected || !writeEnabled) return
    const title = String(articleEditor.title || '').trim()
    const slug = String(articleEditor.slug || '').trim()
    const summary = String(articleEditor.summary || '').trim()
    const { error: sectionsError, sections } = validateAndParseSections(articleEditor.sectionsText)

    if (!title || !slug || !summary) {
      setError('Article title, slug, and summary are required')
      return
    }
    if (sectionsError || !sections) {
      setError(sectionsError || 'Invalid sections payload')
      return
    }

    const payload = {
      slug,
      title,
      summary,
      status: nextStatus,
      published_at: String(articleEditor.publishedAt || '').trim() || null,
      sections,
    }

    setArticleAction(nextStatus === 'published' ? 'publish' : 'save')
    setNotice('')
    setError('')

    try {
      const response = articleEditor.id
        ? await api.updateAdminArchiveArticle(token, articleEditor.id, payload, adminUser)
        : await api.createAdminArchiveArticle(token, payload, adminUser)
      setArticleEditor(toArticleEditor(response))
      setNotice(nextStatus === 'published' ? 'Article published' : 'Draft saved')
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to save article'))
    } finally {
      setArticleAction('')
    }
  }

  const onPublishExistingArticle = async () => {
    if (!connected || !writeEnabled || !articleEditor.id) return
    setArticleAction('publish-existing')
    setNotice('')
    setError('')
    try {
      const response = await api.publishAdminArchiveArticle(
        token,
        articleEditor.id,
        String(articleEditor.publishedAt || '').trim() || null,
        adminUser
      )
      setArticleEditor(toArticleEditor(response))
      setNotice('Article published')
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to publish article'))
    } finally {
      setArticleAction('')
    }
  }

  const onUnpublishArticle = async () => {
    if (!connected || !writeEnabled || !articleEditor.id) return
    setArticleAction('unpublish')
    setNotice('')
    setError('')
    try {
      const response = await api.unpublishAdminArchiveArticle(token, articleEditor.id, adminUser)
      setArticleEditor(toArticleEditor(response))
      setNotice('Article moved to draft')
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to unpublish article'))
    } finally {
      setArticleAction('')
    }
  }

  const onDeleteArticle = async () => {
    if (!connected || !writeEnabled || !articleEditor.id) return
    if (!window.confirm('Delete this article? This action cannot be undone.')) {
      return
    }
    setArticleAction('delete')
    setNotice('')
    setError('')
    try {
      await api.deleteAdminArchiveArticle(token, articleEditor.id, adminUser)
      setNotice('Article deleted')
      setArticleEditor({ ...EMPTY_ARTICLE_EDITOR })
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to delete article'))
    } finally {
      setArticleAction('')
    }
  }

  const onGenerateWeeklyDraft = async () => {
    if (!connected || !writeEnabled) return
    setArticleAction('generate-weekly')
    setNotice('')
    setError('')
    try {
      const response = await api.generateWeeklyArchiveDraft(token, { lookback_days: 7 }, adminUser)
      setArticleEditor(toArticleEditor(response))
      setNotice(`Weekly draft created: ${response.slug}`)
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to generate weekly draft'))
    } finally {
      setArticleAction('')
    }
  }

  const activeRunId = String(status?.viewer_ops?.run_id || '').trim()
  const simulationActive = Boolean(status?.viewer_ops?.simulation_active)
  const paused = Boolean(status?.viewer_ops?.simulation_paused)
  const degraded = Boolean(status?.viewer_ops?.force_cheapest_route)
  const isRunning = simulationActive && !paused

  return (
    <div className="ops-page">
      <div className="page-header">
        <h1>
          <Shield size={32} />
          Ops Console
        </h1>
        <p className="page-description">Internal runtime controls and audit history.</p>
      </div>

      <form className="ops-auth card" onSubmit={onConnect}>
        <div className="card-header">
          <h3>
            <ShieldAlert size={18} />
            Access
          </h3>
          <button type="button" className="btn-subtle" onClick={loadOpsData} disabled={!connected || loading}>
            {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        </div>
        <div className="card-body ops-auth-grid">
          <label className="ops-field">
            <span>Admin token</span>
            <input
              type="password"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              placeholder="Enter admin API token"
              autoComplete="off"
            />
          </label>

          <label className="ops-field">
            <span>Actor name</span>
            <input
              type="text"
              value={adminUser}
              onChange={(event) => setAdminUser(event.target.value)}
              placeholder="ops-ui"
              autoComplete="off"
            />
          </label>

          <button className="btn-primary" type="submit">
            Connect
          </button>
        </div>
      </form>

      {connected && (
        <>
          <div className={`ops-banner ${environment === 'PRODUCTION' ? 'prod' : 'dev'}`}>
            <div className="ops-banner-env">{environment}</div>
            <div className="ops-banner-copy">
              <strong>{writeEnabled ? 'Write controls enabled' : 'Read-only mode enabled'}</strong>
              <span>
                {writeEnabled
                  ? 'Live runtime updates are active in this environment.'
                  : 'Writes are blocked by ADMIN_WRITE_ENABLED=false.'}
              </span>
            </div>
          </div>

          {error && <div className="ops-alert error">{error}</div>}
          {metricsWarning && <div className="ops-alert warn">{metricsWarning}</div>}
          {notice && <div className="ops-alert success">{notice}</div>}

          <div className="ops-grid">
            <section className="card">
              <div className="card-header">
                <h3>Status</h3>
              </div>
              <div className="card-body">
                {!status ? (
                  <div className="empty-state compact">No status loaded.</div>
                ) : (
                  <div className="ops-kv-grid">
                    <div className="ops-kv-item">
                      <span>Server UTC</span>
                      <strong>{status.server_time_utc || 'n/a'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run mode</span>
                      <strong>{status.viewer_ops?.run_mode || 'n/a'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run ID</span>
                      <strong>{activeRunId || 'not set'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Simulation active</span>
                      <strong>{simulationActive ? 'yes' : 'no'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Paused</span>
                      <strong>{status.viewer_ops?.simulation_paused ? 'yes' : 'no'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Cheapest route</span>
                      <strong>{status.viewer_ops?.force_cheapest_route ? 'on' : 'off'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Calls today</span>
                      <strong>{status.llm_budget?.calls_total ?? 0}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Est. cost</span>
                      <strong>${Number(status.llm_budget?.estimated_cost_usd || 0).toFixed(4)}</strong>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section className="card">
              <div className="card-header">
                <h3>Run Controls</h3>
              </div>
              <div className="card-body ops-controls">
                <label className="ops-field">
                  <span>Run ID (optional)</span>
                  <input
                    type="text"
                    value={runIdInput}
                    onChange={(event) => setRunIdInput(event.target.value)}
                    placeholder="test-20260207T120000Z"
                    disabled={!writeEnabled || isProduction}
                  />
                </label>

                <label className="ops-field">
                  <span>Run reason (optional)</span>
                  <input
                    type="text"
                    value={runControlReason}
                    onChange={(event) => setRunControlReason(event.target.value)}
                    placeholder="burn-in, smoke, replay validation"
                    disabled={!writeEnabled}
                  />
                </label>

                <label className="ops-checkbox">
                  <input
                    type="checkbox"
                    checked={Boolean(resetOnTestStart)}
                    onChange={(event) => setResetOnTestStart(event.target.checked)}
                    disabled={!writeEnabled || isProduction}
                  />
                  <span>Reset + reseed world before test start (dev only)</span>
                </label>
                {isProduction && (
                  <div className="ops-alert warn compact">
                    Production safety mode: start/run-reset actions are disabled in this UI.
                  </div>
                )}

                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || isProduction || controlAction === 'start-test' || isRunning}
                    onClick={() => startRun('test')}
                  >
                    {controlAction === 'start-test' ? <Loader2 size={14} className="spin" /> : <Rocket size={14} />}
                    Start Test Run
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || isProduction || controlAction === 'start-real' || isRunning}
                    onClick={() => startRun('real')}
                  >
                    {controlAction === 'start-real' ? <Loader2 size={14} className="spin" /> : <Rocket size={14} />}
                    Start Real Run
                  </button>
                </div>

                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'pause' || paused || !simulationActive}
                    onClick={() => onRunControl('pause', () => api.pauseSimulation(token, 'ops_ui_pause', adminUser), 'Simulation paused')}
                  >
                    {controlAction === 'pause' ? <Loader2 size={14} className="spin" /> : <PauseCircle size={14} />}
                    Pause
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'resume' || !paused || !simulationActive}
                    onClick={() => onRunControl('resume', () => api.resumeSimulation(token, 'ops_ui_resume', adminUser), 'Simulation resumed')}
                  >
                    {controlAction === 'resume' ? <Loader2 size={14} className="spin" /> : <PlayCircle size={14} />}
                    Resume
                  </button>
                </div>

                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'stop-run' || paused || !simulationActive}
                    onClick={stopRun}
                  >
                    {controlAction === 'stop-run' ? <Loader2 size={14} className="spin" /> : <PauseCircle size={14} />}
                    Stop Run
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || isProduction || controlAction === 'reset-dev'}
                    onClick={resetDev}
                  >
                    {controlAction === 'reset-dev' ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                    Reset Dev World
                  </button>
                </div>

                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'degrade-on' || degraded}
                    onClick={() => onRunControl('degrade-on', () => api.setDegradedRouting(token, true, 'ops_ui_degrade_on', adminUser), 'Cheapest-route mode enabled')}
                  >
                    {controlAction === 'degrade-on' ? <Loader2 size={14} className="spin" /> : <Power size={14} />}
                    Degrade On
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'degrade-off' || !degraded}
                    onClick={() => onRunControl('degrade-off', () => api.setDegradedRouting(token, false, 'ops_ui_degrade_off', adminUser), 'Cheapest-route mode cleared')}
                  >
                    {controlAction === 'degrade-off' ? <Loader2 size={14} className="spin" /> : <Power size={14} />}
                    Degrade Off
                  </button>
                </div>
              </div>
            </section>

            <section className="card">
              <div className="card-header">
                <h3>Run Metrics</h3>
              </div>
              <div className="card-body">
                {!runMetrics ? (
                  <div className="empty-state compact">No run metrics loaded.</div>
                ) : (
                  <div className="ops-kv-grid">
                    <div className="ops-kv-item">
                      <span>Active run ID</span>
                      <strong>{runMetrics.run_id || 'not set'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run started</span>
                      <strong>{runMetrics.run_started_at || 'n/a'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>LLM calls</span>
                      <strong>{runMetrics.llm?.calls ?? 0}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Runtime actions</span>
                      <strong>
                        {(runMetrics.activity?.checkpoint_actions ?? 0) + (runMetrics.activity?.deterministic_actions ?? 0)}
                      </strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Proposal actions</span>
                      <strong>{runMetrics.activity?.proposal_actions ?? 0}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Vote actions</span>
                      <strong>{runMetrics.activity?.vote_actions ?? 0}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Forum actions</span>
                      <strong>{runMetrics.activity?.forum_actions ?? 0}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Est. run cost</span>
                      <strong>${Number(runMetrics.llm?.estimated_cost_usd || 0).toFixed(4)}</strong>
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>

          <section className="card ops-config-card">
            <div className="card-header">
              <h3>Mutable Config</h3>
              <span className="ops-meta">{pendingCount} pending updates</span>
            </div>
            <div className="card-body">
              {!config?.mutable_keys ? (
                <div className="empty-state compact">No mutable config loaded.</div>
              ) : (
                <div className="ops-config-list">
                  {Object.entries(config.mutable_keys).map(([key, spec]) => (
                    <div className="ops-config-item" key={key}>
                      <div className="ops-config-head">
                        <strong>{key}</strong>
                        <span>{spec.description}</span>
                      </div>

                      <div className="ops-config-input-wrap">
                        {spec.type === 'bool' ? (
                          <label className="ops-checkbox">
                            <input
                              type="checkbox"
                              checked={Boolean(draftValues[key])}
                              onChange={(event) => setDraftValues((prev) => ({ ...prev, [key]: event.target.checked }))}
                              disabled={!writeEnabled}
                            />
                            <span>{draftValues[key] ? 'true' : 'false'}</span>
                          </label>
                        ) : spec.allowed_values ? (
                          <select
                            value={String(draftValues[key] ?? '')}
                            onChange={(event) => setDraftValues((prev) => ({ ...prev, [key]: event.target.value }))}
                            disabled={!writeEnabled}
                          >
                            {spec.allowed_values.map((choice) => (
                              <option key={choice} value={choice}>{choice}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="text"
                            value={String(draftValues[key] ?? '')}
                            onChange={(event) => setDraftValues((prev) => ({ ...prev, [key]: event.target.value }))}
                            disabled={!writeEnabled}
                          />
                        )}

                        <span className="ops-type-pill">{spec.type}</span>
                      </div>

                      <div className="ops-config-meta">
                        <span>default: {stringifyValue(config.defaults?.[key])}</span>
                        {typeof spec.min === 'number' && <span>min: {spec.min}</span>}
                        {typeof spec.max === 'number' && <span>max: {spec.max}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {invalidFields.length > 0 && (
                <div className="ops-alert error compact">
                  Invalid numeric input for: {invalidFields.join(', ')}
                </div>
              )}

              <label className="ops-field ops-reason">
                <span>Change reason (optional)</span>
                <input
                  type="text"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Why are you changing these values?"
                  disabled={!writeEnabled}
                />
              </label>

              <div className="ops-config-actions">
                <button
                  className="btn-primary"
                  onClick={onApplyConfig}
                  disabled={!writeEnabled || pendingCount === 0 || invalidFields.length > 0 || submittingConfig}
                >
                  {submittingConfig ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
                  Apply updates
                </button>
              </div>
            </div>
          </section>

          <section className="card ops-articles-card">
            <div className="card-header">
              <h3>Archive Publisher</h3>
              <div className="ops-article-header-actions">
                <span className="ops-meta">{adminArticles.length} articles</span>
                <span className="ops-meta">Auto weekly drafts run on server schedule (UTC)</span>
                <button
                  className="btn-subtle"
                  type="button"
                  onClick={onGenerateWeeklyDraft}
                  disabled={!writeEnabled || articleAction === 'generate-weekly'}
                >
                  {(articleAction === 'generate-weekly' && <Loader2 size={14} className="spin" />) || <WandSparkles size={14} />}
                  Weekly Draft
                </button>
                <button className="btn-subtle" type="button" onClick={onNewArticle} disabled={!writeEnabled}>
                  <Plus size={14} />
                  New
                </button>
              </div>
            </div>
            <div className="card-body ops-articles-layout">
              <div className="ops-articles-list">
                {adminArticles.length === 0 ? (
                  <div className="empty-state compact">No archive articles yet.</div>
                ) : (
                  adminArticles.map((article) => {
                    const isSelected = Number(articleEditor.id) === Number(article.id)
                    return (
                      <button
                        key={article.id}
                        type="button"
                        className={`ops-article-row ${isSelected ? 'selected' : ''}`}
                        onClick={() => onSelectArticle(article)}
                      >
                        <div className="ops-article-row-top">
                          <strong>{article.title}</strong>
                          <span className={`ops-status-pill ${article.status === 'published' ? 'published' : 'draft'}`}>
                            {article.status}
                          </span>
                        </div>
                        <div className="ops-article-row-bottom">
                          <span>{article.slug}</span>
                          <span>{article.published_at || 'unpublished'}</span>
                        </div>
                      </button>
                    )
                  })
                )}
              </div>

              <div className="ops-article-editor">
                <label className="ops-field">
                  <span>Title</span>
                  <input
                    type="text"
                    value={articleEditor.title}
                    onChange={(event) => setArticleEditor((prev) => ({ ...prev, title: event.target.value }))}
                    placeholder="Before the First Full Run"
                    disabled={!writeEnabled}
                  />
                </label>

                <div className="ops-article-slug-row">
                  <label className="ops-field">
                    <span>Slug</span>
                    <input
                      type="text"
                      value={articleEditor.slug}
                      onChange={(event) => setArticleEditor((prev) => ({ ...prev, slug: slugify(event.target.value) }))}
                      placeholder="before-the-first-full-run"
                      disabled={!writeEnabled}
                    />
                  </label>
                  <button className="btn-subtle" type="button" onClick={onAutofillSlug} disabled={!writeEnabled}>
                    <FilePenLine size={14} />
                    Autofill
                  </button>
                </div>

                <label className="ops-field">
                  <span>Published date</span>
                  <input
                    type="date"
                    value={articleEditor.publishedAt}
                    onChange={(event) => setArticleEditor((prev) => ({ ...prev, publishedAt: event.target.value }))}
                    disabled={!writeEnabled}
                  />
                </label>

                <label className="ops-field">
                  <span>Summary</span>
                  <textarea
                    rows={4}
                    value={articleEditor.summary}
                    onChange={(event) => setArticleEditor((prev) => ({ ...prev, summary: event.target.value }))}
                    placeholder="Concise field summary for cards and index listing."
                    disabled={!writeEnabled}
                  />
                </label>

                <label className="ops-field">
                  <span>Sections JSON</span>
                  <textarea
                    rows={16}
                    value={articleEditor.sectionsText}
                    onChange={(event) => setArticleEditor((prev) => ({ ...prev, sectionsText: event.target.value }))}
                    placeholder='[{"heading":"...", "paragraphs":["..."]}]'
                    disabled={!writeEnabled}
                    className="ops-sections-textarea"
                  />
                </label>

                <div className="ops-article-actions">
                  <button
                    className="btn-primary"
                    type="button"
                    onClick={() => onSaveArticle('draft')}
                    disabled={!writeEnabled || articleAction === 'save' || articleAction === 'publish'}
                  >
                    {(articleAction === 'save' && <Loader2 size={14} className="spin" />) || <Save size={14} />}
                    Save Draft
                  </button>
                  <button
                    className="btn-primary"
                    type="button"
                    onClick={() => onSaveArticle('published')}
                    disabled={!writeEnabled || articleAction === 'save' || articleAction === 'publish'}
                  >
                    {(articleAction === 'publish' && <Loader2 size={14} className="spin" />) || <Upload size={14} />}
                    Save + Publish
                  </button>
                </div>

                {articleEditor.id && (
                  <div className="ops-article-actions">
                    <button
                      className="btn-subtle"
                      type="button"
                      onClick={onPublishExistingArticle}
                      disabled={!writeEnabled || articleAction === 'publish-existing'}
                    >
                      {(articleAction === 'publish-existing' && <Loader2 size={14} className="spin" />) || <Upload size={14} />}
                      Publish Existing
                    </button>
                    <button
                      className="btn-subtle"
                      type="button"
                      onClick={onUnpublishArticle}
                      disabled={!writeEnabled || articleAction === 'unpublish'}
                    >
                      {(articleAction === 'unpublish' && <Loader2 size={14} className="spin" />) || <EyeOff size={14} />}
                      Unpublish
                    </button>
                    <button
                      className="btn-subtle danger"
                      type="button"
                      onClick={onDeleteArticle}
                      disabled={!writeEnabled || articleAction === 'delete'}
                    >
                      {(articleAction === 'delete' && <Loader2 size={14} className="spin" />) || <Trash2 size={14} />}
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="card ops-audit-card">
            <div className="card-header">
              <h3>Audit Trail</h3>
              <span className="ops-meta">{audit.length} rows</span>
            </div>
            <div className="card-body">
              {audit.length === 0 ? (
                <div className="empty-state compact">No admin changes recorded yet.</div>
              ) : (
                <div className="ops-audit-table-wrap">
                  <table className="ops-audit-table">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Key</th>
                        <th>Change</th>
                        <th>Actor</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.map((entry) => {
                        const createdAt = entry.created_at ? new Date(entry.created_at) : null
                        const when = createdAt
                          ? formatDistanceToNow(createdAt, { addSuffix: true })
                          : 'n/a'

                        return (
                          <tr key={entry.id}>
                            <td title={entry.created_at || ''}>{when}</td>
                            <td>{entry.key}</td>
                            <td>
                              <div className="ops-change">
                                <span>{stringifyValue(entry.old_value)}</span>
                                <span className="ops-arrow">{'->'}</span>
                                <span>{stringifyValue(entry.new_value)}</span>
                              </div>
                            </td>
                            <td>{entry.changed_by || 'unknown'}</td>
                            <td>{entry.reason || 'n/a'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
