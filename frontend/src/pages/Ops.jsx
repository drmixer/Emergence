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
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api } from '../services/api'
import './Ops.css'

const TOKEN_STORAGE_KEY = 'emergence_admin_token'
const USER_STORAGE_KEY = 'emergence_admin_user'

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
      const [statusResponse, configResponse, auditResponse] = await Promise.all([
        api.getAdminStatus(token, adminUser),
        api.getAdminConfig(token, adminUser),
        api.getAdminAudit(token, 50, 0, adminUser),
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
