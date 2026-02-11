"use client"

import { resolveApiBase } from "@/lib/api-base"

type KpiPayload = {
  runId?: string | null
  eventId?: number | string | null
  surface?: string | null
  target?: string | null
  path?: string | null
  referrer?: string | null
  metadata?: Record<string, unknown> | null
}

const ALLOWED_EVENTS = new Set([
  "landing_view",
  "landing_run_click",
  "run_detail_view",
  "replay_start",
  "replay_complete",
  "share_clicked",
  "share_copied",
  "share_native_success",
  "shared_link_open",
])

const VISITOR_KEY = "emergence_kpi_visitor_id"
const SESSION_KEY = "emergence_kpi_session"
const ONCE_PREFIX = "emergence_kpi_once"
const SESSION_TIMEOUT_MS = 30 * 60 * 1000

function cleanText(value: unknown, maxLen = 128): string {
  const text = String(value || "").trim()
  if (!text) return ""
  return text.slice(0, maxLen)
}

function cleanEventId(value: unknown): number | null {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return null
  return Math.trunc(numeric)
}

function randomId(prefix: string): string {
  try {
    const bytes = new Uint8Array(12)
    crypto.getRandomValues(bytes)
    const token = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")
    return `${prefix}_${token}`
  } catch {
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
  }
}

function getVisitorId(): string {
  try {
    const existing = cleanText(localStorage.getItem(VISITOR_KEY), 128)
    if (existing) return existing
    const created = randomId("v")
    localStorage.setItem(VISITOR_KEY, created)
    return created
  } catch {
    return randomId("v")
  }
}

function getSessionId(): string {
  const now = Date.now()
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as { id?: string; last_seen?: number }
      const id = cleanText(parsed?.id, 128)
      const lastSeen = Number(parsed?.last_seen || 0)
      if (id && Number.isFinite(lastSeen) && now - lastSeen < SESSION_TIMEOUT_MS) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, last_seen: now }))
        return id
      }
    }
    const created = randomId("s")
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id: created, last_seen: now }))
    return created
  } catch {
    return randomId("s")
  }
}

function defaultPath(): string {
  if (typeof window === "undefined") return ""
  return `${window.location.pathname || ""}${window.location.search || ""}`.slice(0, 255)
}

function sendPayload(payload: Record<string, unknown>) {
  if (typeof window === "undefined") return
  const endpoint = `${resolveApiBase()}/api/analytics/kpi/events`
  const body = JSON.stringify(payload)

  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" })
      const queued = navigator.sendBeacon(endpoint, blob)
      if (queued) return
    }
  } catch {
    // Fall through to fetch.
  }

  fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {
    // KPI tracking must be non-blocking.
  })
}

export function trackKpiEvent(eventName: string, payload: KpiPayload = {}) {
  const cleanEventName = cleanText(eventName, 64).toLowerCase()
  if (!ALLOWED_EVENTS.has(cleanEventName)) return

  const visitorId = getVisitorId()
  const sessionId = getSessionId()

  sendPayload({
    event_name: cleanEventName,
    visitor_id: visitorId,
    session_id: sessionId || null,
    run_id: cleanText(payload.runId, 64) || null,
    event_id: cleanEventId(payload.eventId),
    surface: cleanText(payload.surface, 64) || null,
    target: cleanText(payload.target, 64) || null,
    path: cleanText(payload.path || defaultPath(), 255) || null,
    referrer: cleanText(payload.referrer || document.referrer, 255) || null,
    metadata: payload.metadata && typeof payload.metadata === "object" ? payload.metadata : {},
  })
}

export function trackKpiEventOnce(eventName: string, key: string, payload: KpiPayload = {}) {
  const cleanEventName = cleanText(eventName, 64).toLowerCase()
  if (!ALLOWED_EVENTS.has(cleanEventName)) return
  const onceKey = `${ONCE_PREFIX}:${cleanEventName}:${cleanText(key, 180)}`

  try {
    if (sessionStorage.getItem(onceKey)) return
    sessionStorage.setItem(onceKey, "1")
  } catch {
    // If storage is unavailable, still emit once best-effort.
  }

  trackKpiEvent(cleanEventName, payload)
}
