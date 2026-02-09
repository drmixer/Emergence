import { track } from '@vercel/analytics/react'
import { trackKpiEvent } from './kpiAnalytics'

const ALLOWED_SHARE_ACTIONS = new Set(['share_clicked', 'share_copied', 'share_native_success'])

function cleanText(value, fallback = '') {
  const text = String(value || '').trim()
  return text || fallback
}

function cleanEventId(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return null
  return Math.trunc(numeric)
}

export function trackShareAction(action, payload = {}) {
  const eventName = cleanText(action).toLowerCase()
  if (!ALLOWED_SHARE_ACTIONS.has(eventName)) return

  const runId = cleanText(payload.runId)
  const eventId = cleanEventId(payload.eventId)
  const surface = cleanText(payload.surface, 'unknown')
  const target = cleanText(payload.target)

  try {
    track(eventName, {
      run_id: runId || null,
      event_id: eventId,
      surface,
      target: target || null,
    })
    trackKpiEvent(eventName, {
      runId,
      eventId,
      surface,
      target: target || null,
    })
  } catch {
    // Share analytics should never block UI interactions.
  }
}
