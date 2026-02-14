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
  Copy,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api } from '../services/api'

const TOKEN_STORAGE_KEY = 'emergence_admin_token'
const USER_STORAGE_KEY = 'emergence_admin_user'
const BASELINE_ARTICLE_SLUG = 'before-the-first-full-run'

const EMPTY_ARTICLE_EDITOR = {
  id: null,
  slug: '',
  title: '',
  summary: '',
  evidenceRunId: '',
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
    evidenceRunId: String(article.evidence_run_id || ''),
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

function formatPercent(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'n/a'
  return `${(numeric * 100).toFixed(1)}%`
}

function displayValue(value, fallback = 'n/a') {
  const text = String(value ?? '').trim()
  return text || fallback
}

const IDENTIFIER_PATTERN = /^[A-Za-z0-9:_-]+$/

function toOptionalText(value) {
  const text = String(value || '').trim()
  return text || null
}

function parseOptionalSeasonNumber(value) {
  const text = String(value ?? '').trim()
  if (!text) return { value: null, error: '' }
  if (!/^\d+$/.test(text)) return { value: null, error: 'Season number must be a positive integer' }
  const parsed = Number.parseInt(text, 10)
  if (!Number.isFinite(parsed) || parsed < 1) {
    return { value: null, error: 'Season number must be >= 1' }
  }
  return { value: parsed, error: '' }
}

function isValidOptionalIdentifier(value) {
  const text = String(value || '').trim()
  if (!text) return true
  return IDENTIFIER_PATTERN.test(text)
}

export default function Ops() {
  const [tokenInput, setTokenInput] = useState(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
  const [token, setToken] = useState(localStorage.getItem(TOKEN_STORAGE_KEY) || '')
  const [adminUser, setAdminUser] = useState(localStorage.getItem(USER_STORAGE_KEY) || 'ops-ui')

  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(null)
  const [audit, setAudit] = useState([])
  const [runMetrics, setRunMetrics] = useState(null)
  const [kpiRollups, setKpiRollups] = useState(null)
  const [runIdInput, setRunIdInput] = useState('')
  const [runControlReason, setRunControlReason] = useState('')
  const [resetOnTestStart, setResetOnTestStart] = useState(true)
  const [protocolVersion, setProtocolVersion] = useState('')
  const [conditionName, setConditionName] = useState('')
  const [hypothesisId, setHypothesisId] = useState('')
  const [seasonId, setSeasonId] = useState('')
  const [seasonNumber, setSeasonNumber] = useState('')
  const [parentRunId, setParentRunId] = useState('')
  const [transferPolicyVersion, setTransferPolicyVersion] = useState('')
  const [epochId, setEpochId] = useState('')
  const [runClass, setRunClass] = useState('')

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
  const [weeklyDraftResult, setWeeklyDraftResult] = useState(null)
  const [runBundleResult, setRunBundleResult] = useState(null)

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
      const [statusResponse, configResponse, auditResponse, articlesResponse, kpiResponse] = await Promise.all([
        api.getAdminStatus(token, adminUser),
        api.getAdminConfig(token, adminUser),
        api.getAdminAudit(token, 50, 0, adminUser),
        api.getAdminArchiveArticles(token, adminUser),
        api.getAdminKpiRollups(token, 14, true, adminUser).catch(() => null),
      ])
      const activeRunId = String(statusResponse?.run_metadata?.run_id || statusResponse?.viewer_ops?.run_id || '').trim()
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
      setKpiRollups(kpiResponse)
      setRunIdInput(activeRunId)
      setProtocolVersion((previous) => previous || String(statusResponse?.run_metadata?.protocol_version || '').trim())
      setConditionName(
        (previous) => previous || String(statusResponse?.run_metadata?.condition_name || statusResponse?.viewer_ops?.condition_name || '').trim()
      )
      setHypothesisId((previous) => previous || String(statusResponse?.run_metadata?.hypothesis_id || '').trim())
      setSeasonId((previous) => previous || String(statusResponse?.run_metadata?.season_id || '').trim())
      setSeasonNumber((previous) => {
        if (previous) return previous
        const numeric = Number(statusResponse?.run_metadata?.season_number || statusResponse?.viewer_ops?.season_number || 0)
        return Number.isFinite(numeric) && numeric > 0 ? String(Math.trunc(numeric)) : ''
      })
      setParentRunId((previous) => previous || String(statusResponse?.run_metadata?.parent_run_id || '').trim())
      setTransferPolicyVersion((previous) => previous || String(statusResponse?.run_metadata?.transfer_policy_version || '').trim())
      setEpochId((previous) => previous || String(statusResponse?.run_metadata?.epoch_id || '').trim())
      setRunClass((previous) => previous || String(statusResponse?.run_metadata?.run_class || '').trim())
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
    const protocolVersionValue = toOptionalText(protocolVersion)
    const conditionNameValue = toOptionalText(conditionName)
    const hypothesisIdValue = toOptionalText(hypothesisId)
    const seasonIdValue = toOptionalText(seasonId)
    const parentRunIdValue = toOptionalText(parentRunId)
    const transferPolicyVersionValue = toOptionalText(transferPolicyVersion)
    const epochIdValue = toOptionalText(epochId)
    const runClassValue = toOptionalText(runClass)
    const parsedSeasonNumber = parseOptionalSeasonNumber(seasonNumber)
    const actionId = mode === 'test' ? 'start-test' : 'start-real'
    const modeLabel = mode === 'test' ? 'test' : 'real'

    if (parsedSeasonNumber.error) {
      setError(parsedSeasonNumber.error)
      return
    }
    if (seasonIdValue && parsedSeasonNumber.value === null) {
      setError('Season number is required when season ID is provided')
      return
    }
    const metadataIdentifiers = [
      ['Run ID', runId],
      ['Protocol version', protocolVersionValue],
      ['Condition name', conditionNameValue],
      ['Hypothesis ID', hypothesisIdValue],
      ['Season ID', seasonIdValue],
      ['Parent run ID', parentRunIdValue],
      ['Transfer policy version', transferPolicyVersionValue],
      ['Epoch ID', epochIdValue],
    ]
    for (const [label, value] of metadataIdentifiers) {
      if (!isValidOptionalIdentifier(value)) {
        setError(`${label} contains invalid characters (allowed: A-Z, a-z, 0-9, :, _, -)`)
        return
      }
    }
    if (runId && parentRunIdValue && parentRunIdValue === runId) {
      setError('Parent run ID must differ from run ID')
      return
    }

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
            protocol_version: protocolVersionValue,
            condition_name: conditionNameValue,
            hypothesis_id: hypothesisIdValue,
            season_id: seasonIdValue,
            season_number: parsedSeasonNumber.value,
            parent_run_id: parentRunIdValue,
            transfer_policy_version: transferPolicyVersionValue,
            epoch_id: epochIdValue,
            run_class: runClassValue,
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
    setArticleEditor((prev) => ({ ...EMPTY_ARTICLE_EDITOR, evidenceRunId: String(activeRunId || prev.evidenceRunId || '').trim() }))
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
    const evidenceRunId = String(articleEditor.evidenceRunId || '').trim()
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
      evidence_run_id: evidenceRunId || null,
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
        {
          published_at: String(articleEditor.publishedAt || '').trim() || null,
          evidence_run_id: String(articleEditor.evidenceRunId || '').trim() || null,
        },
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
      setWeeklyDraftResult(response)
      if (response?.id) {
        setArticleEditor(toArticleEditor(response))
      }
      const responseStatus = String(response?.status || '').trim()
      if (responseStatus === 'insufficient_evidence') {
        setNotice(`Weekly draft skipped: ${String(response?.message || 'Insufficient evidence for digest generation')}`)
      } else if (response?.generated) {
        setNotice(`Weekly draft created: ${String(response?.slug || 'unknown-slug')}`)
      } else if (responseStatus === 'existing') {
        setNotice(`Weekly draft already exists: ${String(response?.slug || 'unknown-slug')}`)
      } else {
        setNotice(`Weekly draft checked: ${String(response?.slug || 'no draft')}`)
      }
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to generate weekly draft'))
    } finally {
      setArticleAction('')
    }
  }

  const onRebuildRunBundle = async () => {
    if (!connected || !writeEnabled) return
    const resolvedRunId = String(runIdInput || activeRunId || articleEditor.evidenceRunId || '').trim()
    if (!resolvedRunId) {
      setError('Run ID is required to rebuild a report bundle')
      return
    }
    setArticleAction('rebuild-run-bundle')
    setNotice('')
    setError('')
    try {
      const conditionName = String(status?.run_metadata?.condition_name || status?.viewer_ops?.condition_name || '').trim()
      const seasonNumber = Number(status?.run_metadata?.season_number || status?.viewer_ops?.season_number || 0)
      const response = await api.rebuildRunReportBundle(
        token,
        {
          run_id: resolvedRunId,
          condition_name: conditionName || null,
          season_number: Number.isFinite(seasonNumber) && seasonNumber > 0 ? seasonNumber : null,
        },
        adminUser
      )
      setRunBundleResult(response)
      setNotice(`Run bundle rebuilt: ${String(response?.run_id || resolvedRunId)}`)
      await loadOpsData()
    } catch (articleError) {
      setError(formatApiError(articleError, 'Failed to rebuild run report bundle'))
    } finally {
      setArticleAction('')
    }
  }

  const onCopyDigestMarkdown = async () => {
    const markdown = String(weeklyDraftResult?.digest_markdown || '').trim()
    if (!markdown) {
      setError('No digest markdown available to copy')
      return
    }
    try {
      await navigator.clipboard.writeText(markdown)
      setNotice('Digest markdown copied')
    } catch {
      setError('Unable to copy digest markdown')
    }
  }

  const statusRunMetadata = status?.run_metadata && typeof status.run_metadata === 'object' ? status.run_metadata : null
  const runMetricsMetadata = runMetrics?.run_metadata && typeof runMetrics.run_metadata === 'object' ? runMetrics.run_metadata : null
  const activeRunId = String(statusRunMetadata?.run_id || status?.viewer_ops?.run_id || '').trim()
  const statusRunMode = String(statusRunMetadata?.run_mode || status?.viewer_ops?.run_mode || '').trim() || 'n/a'
  const statusConditionName = String(statusRunMetadata?.condition_name || status?.viewer_ops?.condition_name || '').trim()
  const statusSeasonNumber = Number(statusRunMetadata?.season_number || status?.viewer_ops?.season_number || 0)
  const metricsSeasonNumber = Number(runMetricsMetadata?.season_number || runMetrics?.season_number || 0)
  const simulationActive = Boolean(status?.viewer_ops?.simulation_active)
  const paused = Boolean(status?.viewer_ops?.simulation_paused)
  const degraded = Boolean(status?.viewer_ops?.force_cheapest_route)
  const isRunning = simulationActive && !paused
  const editorSlug = String(articleEditor.slug || '').trim()
  const editorEvidenceRunId = String(articleEditor.evidenceRunId || '').trim()
  const requiresEvidenceRunId = editorSlug.length > 0 && editorSlug !== BASELINE_ARTICLE_SLUG
  const canPublishWithEvidence = !requiresEvidenceRunId || editorEvidenceRunId.length > 0
  const weeklyDraftStatus = String(weeklyDraftResult?.status || 'ok')
  const weeklyDraftMessage = String(weeklyDraftResult?.message || '').trim()
  const weeklyDigestPath = String(weeklyDraftResult?.digest_markdown_path || '').trim()
  const weeklyDigestMarkdown = String(weeklyDraftResult?.digest_markdown || '')
  const weeklyEvidenceGate = weeklyDraftResult?.evidence_gate || null
  const runBundleStatus = String(runBundleResult?.status || '').trim()
  const reportPipeline = status?.report_pipeline && typeof status.report_pipeline === 'object' ? status.report_pipeline : {}
  const reportCloseout = reportPipeline?.closeout && typeof reportPipeline.closeout === 'object' ? reportPipeline.closeout : {}
  const reportBackfill = reportPipeline?.backfill && typeof reportPipeline.backfill === 'object' ? reportPipeline.backfill : {}
  const reportBackfillGenerated = Array.isArray(reportBackfill?.last_generated) ? reportBackfill.last_generated : []
  const reportBackfillSkipped = Array.isArray(reportBackfill?.last_skipped) ? reportBackfill.last_skipped : []
  const reportBackfillErrors = Array.isArray(reportBackfill?.last_errors) ? reportBackfill.last_errors : []
  const kpiItems = Array.isArray(kpiRollups?.items) ? kpiRollups.items : []
  const kpiSummary = kpiRollups?.summary || {}
  const kpiLatest = kpiSummary?.latest || (kpiItems.length > 0 ? kpiItems[0] : null)
  const kpiSevenDayAvg = kpiSummary?.seven_day_avg || {}
  const kpiAlerts = kpiRollups?.alerts || {}
  const kpiAlertItems = Array.isArray(kpiAlerts?.items) ? kpiAlerts.items : []
  const kpiAlertCounts = kpiAlerts?.counts || {}
  const kpiAlertStatus = String(kpiAlerts?.status || 'ok')
  const kpiAlertDelivery = kpiRollups?.alert_notification || {}

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
                  <>
                    <div className="ops-kv-grid">
                    <div className="ops-kv-item">
                      <span>Server UTC</span>
                      <strong>{status.server_time_utc || 'n/a'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run mode</span>
                      <strong>{statusRunMode}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run ID</span>
                      <strong>{activeRunId || 'not set'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Condition</span>
                      <strong>{displayValue(statusConditionName, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Season</span>
                      <strong>{statusSeasonNumber > 0 ? statusSeasonNumber : 'not set'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Protocol</span>
                      <strong>{displayValue(statusRunMetadata?.protocol_version, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run class</span>
                      <strong>{displayValue(statusRunMetadata?.run_class, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Hypothesis</span>
                      <strong>{displayValue(statusRunMetadata?.hypothesis_id, 'not set')}</strong>
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
                      <span>Season ID</span>
                      <strong>{displayValue(statusRunMetadata?.season_id, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Epoch ID</span>
                      <strong>{displayValue(statusRunMetadata?.epoch_id, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Parent run</span>
                      <strong>{displayValue(statusRunMetadata?.parent_run_id, 'none')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Transfer policy</span>
                      <strong>{displayValue(statusRunMetadata?.transfer_policy_version, 'none')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Carryover / fresh</span>
                      <strong>{Number(statusRunMetadata?.carryover_agent_count || 0)} / {Number(statusRunMetadata?.fresh_agent_count || 0)}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Protocol deviation</span>
                      <strong>{statusRunMetadata?.protocol_deviation ? 'yes' : 'no'}</strong>
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
                  <div className="ops-report-pipeline">
                    <div className="ops-report-pipeline-head">
                      <strong>Report Pipeline</strong>
                      <span>Closeout + scheduled backfill health</span>
                    </div>
                    <div className="ops-report-pipeline-grid">
                      <div className="ops-kv-item">
                        <span>Closeout status</span>
                        <strong>{displayValue(reportCloseout?.last_status, 'idle')}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Closeout run</span>
                        <strong>{displayValue(reportCloseout?.last_run_id, 'n/a')}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Closeout attempted</span>
                        <strong>{displayValue(reportCloseout?.last_attempted_at, 'n/a')}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Backfill status</span>
                        <strong>{displayValue(reportBackfill?.last_status, 'idle')}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Backfill attempted</span>
                        <strong>{displayValue(reportBackfill?.last_attempted_at, 'n/a')}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Backfill generated</span>
                        <strong>{reportBackfillGenerated.length}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Backfill skipped</span>
                        <strong>{reportBackfillSkipped.length}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Backfill errors</span>
                        <strong>{reportBackfillErrors.length}</strong>
                      </div>
                    </div>
                    {(String(reportCloseout?.last_error || '').trim() || String(reportBackfill?.last_error || '').trim()) && (
                      <div className="ops-alert warn compact">
                        Report pipeline warning:{' '}
                        {String(reportCloseout?.last_error || reportBackfill?.last_error || '').trim()}
                      </div>
                    )}
                    </div>
                  </>
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

                <div className="ops-advanced-metadata">
                  <div className="ops-advanced-metadata-head">
                    <span>Advanced run metadata (optional)</span>
                    <button
                      type="button"
                      className="btn-subtle"
                      disabled={!writeEnabled}
                      onClick={() => {
                        const source = status?.run_metadata || status?.viewer_ops || {}
                        setProtocolVersion(String(source.protocol_version || '').trim())
                        setConditionName(String(source.condition_name || '').trim())
                        setHypothesisId(String(source.hypothesis_id || '').trim())
                        setSeasonId(String(source.season_id || '').trim())
                        const numericSeasonNumber = Number(source.season_number || 0)
                        setSeasonNumber(Number.isFinite(numericSeasonNumber) && numericSeasonNumber > 0 ? String(Math.trunc(numericSeasonNumber)) : '')
                        setParentRunId(String(source.parent_run_id || '').trim())
                        setTransferPolicyVersion(String(source.transfer_policy_version || '').trim())
                        setEpochId(String(source.epoch_id || '').trim())
                        setRunClass(String(source.run_class || '').trim())
                      }}
                    >
                      Load Current Metadata
                    </button>
                  </div>
                  <div className="ops-advanced-metadata-grid">
                    <label className="ops-field">
                      <span>Protocol Version</span>
                      <input
                        type="text"
                        value={protocolVersion}
                        onChange={(event) => setProtocolVersion(event.target.value)}
                        placeholder="protocol_v1"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Condition Name</span>
                      <input
                        type="text"
                        value={conditionName}
                        onChange={(event) => setConditionName(event.target.value)}
                        placeholder="baseline-control"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Hypothesis ID</span>
                      <input
                        type="text"
                        value={hypothesisId}
                        onChange={(event) => setHypothesisId(event.target.value)}
                        placeholder="hypothesis-2026-02-a"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Season ID</span>
                      <input
                        type="text"
                        value={seasonId}
                        onChange={(event) => setSeasonId(event.target.value)}
                        placeholder="season-2026-s1"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Season Number</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={seasonNumber}
                        onChange={(event) => setSeasonNumber(event.target.value)}
                        placeholder="1"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Parent Run ID</span>
                      <input
                        type="text"
                        value={parentRunId}
                        onChange={(event) => setParentRunId(event.target.value)}
                        placeholder="real-20260209T120000Z"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Transfer Policy Version</span>
                      <input
                        type="text"
                        value={transferPolicyVersion}
                        onChange={(event) => setTransferPolicyVersion(event.target.value)}
                        placeholder="transfer_v1"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Epoch ID</span>
                      <input
                        type="text"
                        value={epochId}
                        onChange={(event) => setEpochId(event.target.value)}
                        placeholder="epoch-2026q1"
                        disabled={!writeEnabled || isProduction}
                      />
                    </label>
                    <label className="ops-field">
                      <span>Run Class</span>
                      <select
                        value={runClass}
                        onChange={(event) => setRunClass(event.target.value)}
                        disabled={!writeEnabled || isProduction}
                      >
                        <option value="">default (standard_72h)</option>
                        <option value="standard_72h">standard_72h</option>
                        <option value="deep_96h">deep_96h</option>
                        <option value="special_exploratory">special_exploratory</option>
                      </select>
                    </label>
                  </div>
                  <p className="ops-inline-help">Allowed characters for metadata IDs: letters, numbers, colon, underscore, and dash.</p>
                </div>

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
                      <span>Condition</span>
                      <strong>{displayValue(runMetricsMetadata?.condition_name || runMetrics.condition_name, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Season</span>
                      <strong>{metricsSeasonNumber > 0 ? metricsSeasonNumber : 'not set'}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Protocol</span>
                      <strong>{displayValue(runMetricsMetadata?.protocol_version, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Run class</span>
                      <strong>{displayValue(runMetricsMetadata?.run_class, 'not set')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Transfer policy</span>
                      <strong>{displayValue(runMetricsMetadata?.transfer_policy_version, 'none')}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Carryover / fresh</span>
                      <strong>{Number(runMetricsMetadata?.carryover_agent_count || 0)} / {Number(runMetricsMetadata?.fresh_agent_count || 0)}</strong>
                    </div>
                    <div className="ops-kv-item">
                      <span>Protocol deviation</span>
                      <strong>{runMetricsMetadata?.protocol_deviation ? 'yes' : 'no'}</strong>
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

            <section className="card">
              <div className="card-header">
                <h3>KPI Rollups</h3>
              </div>
              <div className="card-body">
                {!kpiLatest ? (
                  <div className="empty-state compact">No KPI rollups available yet.</div>
                ) : (
                  <div className="ops-kpi-stack">
                    {kpiAlertItems.length > 0 ? (
                      <div className={`ops-kpi-alert-panel ${kpiAlertStatus}`}>
                        <div className="ops-kpi-alert-head">
                          <strong>
                            KPI Alerts: {Number(kpiAlertCounts.critical || 0)} critical, {Number(kpiAlertCounts.warning || 0)} warning
                          </strong>
                          <span>Triggered from latest day thresholds and 7-day drop-offs.</span>
                        </div>
                        <div className="ops-kpi-alert-list">
                          {kpiAlertItems.map((alert) => (
                            <div className={`ops-kpi-alert ${alert.severity || 'warning'}`} key={`${alert.metric || 'metric'}-${alert.day_key || 'latest'}`}>
                              <span className="ops-kpi-alert-label">{alert.label || alert.metric || 'KPI'}</span>
                              <span>{alert.message || 'Alert triggered'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="ops-kpi-alert-empty">No active KPI alerts for current thresholds.</div>
                    )}
                    <div className="ops-kpi-delivery">
                      Alert delivery: {kpiAlertDelivery.sent ? 'sent' : 'not sent'} ({kpiAlertDelivery.reason || 'n/a'})
                    </div>

                    <div className="ops-kv-grid">
                      <div className="ops-kv-item">
                        <span>Latest day</span>
                        <strong>{kpiLatest.day_key || 'n/a'}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Landing -&gt; Run CTR</span>
                        <strong>{formatPercent(kpiLatest.landing_to_run_ctr)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Run -&gt; Replay Start</span>
                        <strong>{formatPercent(kpiLatest.run_to_replay_start_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Replay Completion</span>
                        <strong>{formatPercent(kpiLatest.replay_completion_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Share Action Rate</span>
                        <strong>{formatPercent(kpiLatest.share_action_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Shared-link CTR</span>
                        <strong>{formatPercent(kpiLatest.shared_link_ctr)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>D1 Retention</span>
                        <strong>{formatPercent(kpiLatest.d1_retention_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>D7 Retention</span>
                        <strong>{formatPercent(kpiLatest.d7_retention_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Onboarding shown (visitors)</span>
                        <strong>{Number(kpiLatest.onboarding_shown_visitors || 0).toLocaleString()}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Onboarding completion</span>
                        <strong>{formatPercent(kpiLatest.onboarding_completion_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Onboarding skip</span>
                        <strong>{formatPercent(kpiLatest.onboarding_skip_rate)}</strong>
                      </div>
                      <div className="ops-kv-item">
                        <span>Glossary open rate</span>
                        <strong>{formatPercent(kpiLatest.onboarding_glossary_open_rate)}</strong>
                      </div>
                    </div>

                    <div className="ops-kpi-summary">
                      <span>7d Avg Landing -&gt; Run: {formatPercent(kpiSevenDayAvg.landing_to_run_ctr)}</span>
                      <span>7d Avg Replay Completion: {formatPercent(kpiSevenDayAvg.replay_completion_rate)}</span>
                      <span>7d Avg D7 Retention: {formatPercent(kpiSevenDayAvg.d7_retention_rate)}</span>
                      <span>7d Avg Onboarding Completion: {formatPercent(kpiSevenDayAvg.onboarding_completion_rate)}</span>
                      <span>7d Avg Onboarding Skip: {formatPercent(kpiSevenDayAvg.onboarding_skip_rate)}</span>
                    </div>

                    {kpiItems.length > 0 && (
                      <div className="ops-kpi-table-wrap">
                        <table className="ops-kpi-table">
                          <thead>
                            <tr>
                              <th>Day</th>
                              <th>Landing Views</th>
                              <th>Run Views</th>
                              <th>Replay Starts</th>
                              <th>Replay Completions</th>
                              <th>Share Clicks</th>
                              <th>Shared Opens</th>
                              <th>Onboarding Shown</th>
                              <th>Onboarding Completed</th>
                              <th>Onboarding Skipped</th>
                              <th>Glossary Opens</th>
                              <th>Onboarding Completion</th>
                              <th>D1</th>
                              <th>D7</th>
                            </tr>
                          </thead>
                          <tbody>
                            {kpiItems.slice(0, 14).map((item) => (
                              <tr key={item.day_key}>
                                <td>{item.day_key}</td>
                                <td>{Number(item.landing_views || 0).toLocaleString()}</td>
                                <td>{Number(item.run_detail_views || 0).toLocaleString()}</td>
                                <td>{Number(item.replay_starts || 0).toLocaleString()}</td>
                                <td>{Number(item.replay_completions || 0).toLocaleString()}</td>
                                <td>{Number(item.share_clicks || 0).toLocaleString()}</td>
                                <td>{Number(item.shared_link_opens || 0).toLocaleString()}</td>
                                <td>{Number(item.onboarding_shown_visitors || 0).toLocaleString()}</td>
                                <td>{Number(item.onboarding_completed_visitors || 0).toLocaleString()}</td>
                                <td>{Number(item.onboarding_skipped_visitors || 0).toLocaleString()}</td>
                                <td>{Number(item.onboarding_glossary_opened_visitors || 0).toLocaleString()}</td>
                                <td>{formatPercent(item.onboarding_completion_rate)}</td>
                                <td>{formatPercent(item.d1_retention_rate)}</td>
                                <td>{formatPercent(item.d7_retention_rate)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
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
                <button
                  className="btn-subtle"
                  type="button"
                  onClick={onRebuildRunBundle}
                  disabled={!writeEnabled || articleAction === 'rebuild-run-bundle'}
                >
                  {(articleAction === 'rebuild-run-bundle' && <Loader2 size={14} className="spin" />) || <FilePenLine size={14} />}
                  Rebuild Run Bundle
                </button>
                <button className="btn-subtle" type="button" onClick={onNewArticle} disabled={!writeEnabled}>
                  <Plus size={14} />
                  New
                </button>
              </div>
            </div>
            <div className="card-body ops-articles-layout">
              {runBundleResult && (
                <div className={`ops-digest-preview ${runBundleStatus === 'failed' ? 'warn' : 'ok'}`}>
                  <div className="ops-digest-preview-head">
                    <strong>Run Bundle Result</strong>
                    <span className={`ops-status-pill ${runBundleStatus === 'failed' ? 'draft' : 'published'}`}>
                      {runBundleStatus || 'generated'}
                    </span>
                  </div>
                  <div className="ops-digest-preview-meta">
                    <span>Run: {String(runBundleResult?.run_id || 'n/a')}</span>
                    <span>Condition: {String(runBundleResult?.condition_name || 'unknown')}</span>
                    <span>Replicates: {String(runBundleResult?.replicate_count ?? 'n/a')}</span>
                  </div>
                </div>
              )}
              {weeklyDraftResult && (
                <div className={`ops-digest-preview ${weeklyDraftStatus === 'insufficient_evidence' ? 'warn' : 'ok'}`}>
                  <div className="ops-digest-preview-head">
                    <strong>Weekly Digest Result</strong>
                    <span className={`ops-status-pill ${weeklyDraftStatus === 'insufficient_evidence' ? 'draft' : 'published'}`}>
                      {weeklyDraftStatus}
                    </span>
                  </div>
                  {weeklyDraftMessage && <div className="ops-digest-preview-message">{weeklyDraftMessage}</div>}
                  <div className="ops-digest-preview-meta">
                    <span>Template: {String(weeklyDraftResult?.digest_template_version || 'n/a')}</span>
                    <span>Path: {weeklyDigestPath || 'n/a'}</span>
                  </div>
                  {weeklyEvidenceGate && (
                    <div className="ops-digest-preview-meta">
                      <span>
                        Evidence gate observed events: {weeklyEvidenceGate?.observed?.total_events ?? 'n/a'} / required {weeklyEvidenceGate?.requirements?.min_events ?? 'n/a'}
                      </span>
                      <span>
                        LLM calls: {weeklyEvidenceGate?.observed?.llm_calls ?? 'n/a'} / required {weeklyEvidenceGate?.requirements?.min_llm_calls ?? 'n/a'}
                      </span>
                    </div>
                  )}
                  {weeklyDigestMarkdown && (
                    <div className="ops-digest-preview-markdown">
                      <div className="ops-digest-preview-actions">
                        <button className="btn-subtle" type="button" onClick={onCopyDigestMarkdown}>
                          <Copy size={14} />
                          Copy Markdown
                        </button>
                      </div>
                      <textarea rows={10} value={weeklyDigestMarkdown} readOnly className="ops-sections-textarea" />
                    </div>
                  )}
                </div>
              )}
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
                          <span>{article.evidence_run_id || article.published_at || 'unpublished'}</span>
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
                  <span>Evidence Run ID</span>
                  <input
                    type="text"
                    value={articleEditor.evidenceRunId}
                    onChange={(event) => setArticleEditor((prev) => ({ ...prev, evidenceRunId: event.target.value }))}
                    placeholder="run-20260207T015151Z"
                    disabled={!writeEnabled}
                  />
                  <small className="ops-inline-help">
                    Required to publish non-baseline articles. Must match telemetry in llm_usage.
                  </small>
                </label>

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
                    disabled={!writeEnabled || articleAction === 'save' || articleAction === 'publish' || !canPublishWithEvidence}
                  >
                    {(articleAction === 'publish' && <Loader2 size={14} className="spin" />) || <Upload size={14} />}
                    Save + Publish
                  </button>
                </div>
                {!canPublishWithEvidence && (
                  <div className="ops-inline-error">
                    Evidence Run ID is required before publishing non-baseline articles.
                  </div>
                )}

                {articleEditor.id && (
                  <div className="ops-article-actions">
                    <button
                      className="btn-subtle"
                      type="button"
                      onClick={onPublishExistingArticle}
                      disabled={!writeEnabled || articleAction === 'publish-existing' || !canPublishWithEvidence}
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
