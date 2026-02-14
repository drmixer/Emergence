import { resolveApiBase } from '../../lib/api-base'

const ALLOWED_EVENTS = new Set([
  'landing_view',
  'landing_run_click',
  'run_detail_view',
  'replay_start',
  'replay_complete',
  'share_clicked',
  'share_copied',
  'share_native_success',
  'shared_link_open',
  'onboarding_shown',
  'onboarding_completed',
  'onboarding_skipped',
  'onboarding_glossary_opened',
])

const VISITOR_KEY = 'emergence_kpi_visitor_id'
const SESSION_KEY = 'emergence_kpi_session'
const ONCE_PREFIX = 'emergence_kpi_once'
const SESSION_TIMEOUT_MS = 30 * 60 * 1000

function cleanText(value, maxLen = 128) {
  const text = String(value || '').trim()
  if (!text) return ''
  return text.slice(0, maxLen)
}

function cleanRunId(value) {
  return cleanText(value, 64)
}

function cleanEventId(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return null
  return Math.trunc(numeric)
}

function randomId(prefix) {
  try {
    const bytes = new Uint8Array(12)
    crypto.getRandomValues(bytes)
    const token = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
    return `${prefix}_${token}`
  } catch {
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
  }
}

function getVisitorId() {
  try {
    const existing = cleanText(localStorage.getItem(VISITOR_KEY), 128)
    if (existing) return existing
    const created = randomId('v')
    localStorage.setItem(VISITOR_KEY, created)
    return created
  } catch {
    return randomId('v')
  }
}

function getSessionId() {
  const now = Date.now()
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const id = cleanText(parsed?.id, 128)
      const lastSeen = Number(parsed?.last_seen || 0)
      if (id && Number.isFinite(lastSeen) && now - lastSeen < SESSION_TIMEOUT_MS) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, last_seen: now }))
        return id
      }
    }
    const created = randomId('s')
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id: created, last_seen: now }))
    return created
  } catch {
    return randomId('s')
  }
}

function getDefaultPath() {
  if (typeof window === 'undefined') return ''
  const pathname = String(window.location.pathname || '')
  const search = String(window.location.search || '')
  return `${pathname}${search}`.slice(0, 255)
}

function sendPayload(payload) {
  if (typeof window === 'undefined') return
  const apiBase = resolveApiBase()
  if (!apiBase) return
  const endpoint = `${apiBase}/api/analytics/kpi/events`
  const body = JSON.stringify(payload)

  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' })
      const queued = navigator.sendBeacon(endpoint, blob)
      if (queued) return
    }
  } catch {
    // Fall through to fetch.
  }

  fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {
    // KPI tracking should never block the UI.
  })
}

export function trackKpiEvent(eventName, payload = {}) {
  const cleanEventName = cleanText(eventName, 64).toLowerCase()
  if (!ALLOWED_EVENTS.has(cleanEventName)) return

  const visitorId = getVisitorId()
  const sessionId = getSessionId()
  const runId = cleanRunId(payload.runId)
  const eventId = cleanEventId(payload.eventId)
  const surface = cleanText(payload.surface, 64)
  const target = cleanText(payload.target, 64)
  const path = cleanText(payload.path || getDefaultPath(), 255)
  const referrer = cleanText(payload.referrer || (typeof document !== 'undefined' ? document.referrer : ''), 255)

  sendPayload({
    event_name: cleanEventName,
    visitor_id: visitorId,
    session_id: sessionId || null,
    run_id: runId || null,
    event_id: eventId,
    surface: surface || null,
    target: target || null,
    path: path || null,
    referrer: referrer || null,
    metadata: typeof payload.metadata === 'object' && payload.metadata ? payload.metadata : {},
  })
}

export function trackKpiEventOnce(eventName, key, payload = {}) {
  const cleanEventName = cleanText(eventName, 64).toLowerCase()
  if (!ALLOWED_EVENTS.has(cleanEventName)) return
  const onceKey = `${ONCE_PREFIX}:${cleanEventName}:${cleanText(key, 180)}`

  try {
    if (sessionStorage.getItem(onceKey)) return
    sessionStorage.setItem(onceKey, '1')
  } catch {
    // Fall through and send event.
  }

  trackKpiEvent(cleanEventName, payload)
}
