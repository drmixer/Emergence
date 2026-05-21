#!/usr/bin/env node

import { resolveConfiguredApiBase } from "../lib/api-base.js"

const SITE_BASE = String(
  process.env.SMOKE_SITE_BASE || process.env.NEXT_PUBLIC_SITE_URL || "https://www.emergence.quest"
).replace(/\/+$/, "")
const API_BASE = String(
  process.env.SMOKE_API_BASE || resolveConfiguredApiBase() || "https://api.emergence.quest"
).replace(/\/+$/, "")
const TIMEOUT_MS = Number(process.env.SMOKE_TIMEOUT_MS || 20000)
const RUN_ID = String(process.env.SMOKE_RUN_ID || "").trim()
const SKIP_SITE_CHECK = String(process.env.SMOKE_SKIP_SITE_CHECK || "").toLowerCase() === "true"
const GENERIC_EVENT_TYPES = new Set(["direct_message", "forum_post", "forum_reply", "work", "idle", "vote"])

function fail(message) {
  throw new Error(message)
}

function ensure(condition, message) {
  if (!condition) fail(message)
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, { redirect: "follow", signal: controller.signal, ...options })
    ensure(response.ok, `Expected 2xx for ${url}, got ${response.status}`)
    return response
  } finally {
    clearTimeout(timer)
  }
}

async function fetchJson(url) {
  const response = await fetchWithTimeout(url, { headers: { Accept: "application/json" } })
  const contentType = String(response.headers.get("content-type") || "").toLowerCase()
  ensure(contentType.includes("application/json"), `Expected JSON for ${url}, got ${contentType || "n/a"}`)
  return response.json()
}

async function resolveRunId() {
  if (RUN_ID) return RUN_ID
  const archive = await fetchJson(`${API_BASE}/api/reports/archive/runs?limit=1`)
  const runId = String(archive?.items?.[0]?.run_id || "").trim()
  ensure(runId, "Could not resolve latest archived run id")
  return runId
}

function validateWatchPayload(payload, runId) {
  ensure(payload && typeof payload === "object", "Watch payload must be an object")
  ensure(payload.run_id === runId, `Expected run_id=${runId}, got ${payload.run_id || "n/a"}`)
  ensure(payload.contract?.source_type === "watch_replay_board", "Watch payload source_type mismatch")
  ensure(payload.contract?.moment_policy === "explicit_watch_signal_event_types", "Watch payload moment policy mismatch")
  ensure(Number(payload.activity?.total_events || 0) > 0, "Watch payload missing activity totals")
  ensure(Number(payload.bucket_count || 0) > 0, "Watch payload missing buckets")
  ensure(Array.isArray(payload.buckets) && payload.buckets.length === Number(payload.bucket_count), "Watch bucket count mismatch")
  ensure(Array.isArray(payload.items), "Watch payload items must be an array")
  ensure(Array.isArray(payload.lanes), "Watch payload lanes must be an array")

  for (const item of payload.items) {
    const eventType = String(item?.event_type || "")
    ensure(!GENERIC_EVENT_TYPES.has(eventType), `Generic event type leaked into watch moments: ${eventType}`)
    ensure(String(item?.lane || ""), `Watch moment ${item?.event_id || "n/a"} missing lane`)
    ensure(Number(item?.event_id || 0) > 0, "Watch moment missing event_id")
  }
}

async function main() {
  ensure(API_BASE.length > 0, "Resolved API base is empty")
  const runId = await resolveRunId()
  const watchUrl = `${API_BASE}/api/analytics/runs/${encodeURIComponent(runId)}/watch?bucket_minutes=60&limit=240`
  const payload = await fetchJson(watchUrl)
  validateWatchPayload(payload, runId)
  console.log(`[ok] watch payload: ${watchUrl}`)
  console.log(`     moments=${payload.count}, buckets=${payload.bucket_count}, events=${payload.activity.total_events}`)

  if (!SKIP_SITE_CHECK) {
    const pageUrl = `${SITE_BASE}/watch?run=${encodeURIComponent(runId)}`
    await fetchWithTimeout(pageUrl)
    console.log(`[ok] watch page reachable: ${pageUrl}`)
  }

  console.log("")
  console.log(`[done] Watch replay smoke passed for site=${SITE_BASE}, api=${API_BASE}, run=${runId}`)
}

main().catch((error) => {
  console.error(`[fail] ${error?.message || error}`)
  process.exitCode = 1
})
