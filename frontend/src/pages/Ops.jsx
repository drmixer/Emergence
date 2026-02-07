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

  const [draftValues, setDraftValues] = useState({})
  const [reason, setReason] = useState('')

  const [loading, setLoading] = useState(false)
  const [submittingConfig, setSubmittingConfig] = useState(false)
  const [controlAction, setControlAction] = useState('')

  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const connected = Boolean(token.trim())
  const writeEnabled = Boolean(config?.admin_write_enabled)
  const environment = String(config?.environment || status?.environment || 'unknown').toUpperCase()

  useEffect(() => {
    localStorage.setItem(USER_STORAGE_KEY, adminUser)
  }, [adminUser])

  const loadOpsData = async () => {
    if (!connected) return
    setLoading(true)
    setError('')

    try {
      const [statusResponse, configResponse, auditResponse] = await Promise.all([
        api.getAdminStatus(token, adminUser),
        api.getAdminConfig(token, adminUser),
        api.getAdminAudit(token, 50, 0, adminUser),
      ])

      setStatus(statusResponse)
      setConfig(configResponse)
      setAudit(Array.isArray(auditResponse?.items) ? auditResponse.items : [])
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
      await actionFn()
      setNotice(successMessage)
      await loadOpsData()
    } catch (controlError) {
      setError(formatApiError(controlError, 'Control action failed'))
    } finally {
      setControlAction('')
    }
  }

  const runMode = status?.viewer_ops?.run_mode || 'test'
  const paused = Boolean(status?.viewer_ops?.simulation_paused)
  const degraded = Boolean(status?.viewer_ops?.force_cheapest_route)

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
                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'pause' || paused}
                    onClick={() => onRunControl('pause', () => api.pauseSimulation(token, 'ops_ui_pause', adminUser), 'Simulation paused')}
                  >
                    {controlAction === 'pause' ? <Loader2 size={14} className="spin" /> : <PauseCircle size={14} />}
                    Pause
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'resume' || !paused}
                    onClick={() => onRunControl('resume', () => api.resumeSimulation(token, 'ops_ui_resume', adminUser), 'Simulation resumed')}
                  >
                    {controlAction === 'resume' ? <Loader2 size={14} className="spin" /> : <PlayCircle size={14} />}
                    Resume
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

                <div className="ops-control-row">
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'run-test' || runMode === 'test'}
                    onClick={() => onRunControl('run-test', () => api.setSimulationRunMode(token, 'test', 'ops_ui_mode_test', adminUser), 'Run mode set to test')}
                  >
                    {controlAction === 'run-test' ? <Loader2 size={14} className="spin" /> : <Rocket size={14} />}
                    Run Mode: test
                  </button>
                  <button
                    className="btn-primary"
                    disabled={!writeEnabled || controlAction === 'run-real' || runMode === 'real'}
                    onClick={() => onRunControl('run-real', () => api.setSimulationRunMode(token, 'real', 'ops_ui_mode_real', adminUser), 'Run mode set to real')}
                  >
                    {controlAction === 'run-real' ? <Loader2 size={14} className="spin" /> : <Rocket size={14} />}
                    Run Mode: real
                  </button>
                </div>
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
