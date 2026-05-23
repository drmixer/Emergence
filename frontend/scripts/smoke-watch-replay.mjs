#!/usr/bin/env node

import { spawn } from "node:child_process"
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
const SKIP_RENDER_CHECK = String(process.env.SMOKE_SKIP_RENDER_CHECK || "").toLowerCase() === "true"
const GENERIC_EVENT_TYPES = new Set(["direct_message", "forum_post", "forum_reply", "work", "idle", "vote"])

const BROWSER_CANDIDATES = [
  process.env.SMOKE_BROWSER_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "google-chrome",
  "google-chrome-stable",
  "chromium",
  "chromium-browser",
].filter(Boolean)

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

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const timeoutMs = Number(options.timeoutMs || TIMEOUT_MS)
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      ...options,
      timeoutMs: undefined,
    })
    let settled = false
    let stdout = ""
    let stderr = ""
    const timer = setTimeout(() => {
      if (settled) return
      child.kill("SIGKILL")
      settled = true
      resolve({ code: null, stdout, stderr: `${stderr}\nCommand timed out after ${timeoutMs}ms` })
    }, timeoutMs)
    child.stdout?.setEncoding("utf8")
    child.stderr?.setEncoding("utf8")
    child.stdout?.on("data", (chunk) => {
      stdout += chunk
    })
    child.stderr?.on("data", (chunk) => {
      stderr += chunk
    })
    child.on("error", (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(error)
    })
    child.on("close", (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ code, stdout, stderr })
    })
  })
}

async function findBrowserBin() {
  for (const candidate of BROWSER_CANDIDATES) {
    const result = candidate.includes("/")
      ? await runCommand(candidate, ["--version"]).catch(() => null)
      : await runCommand("which", [candidate]).catch(() => null)
    if (result?.code === 0) return candidate
  }
  return ""
}

async function dumpRenderedDom(url) {
  const browserBin = await findBrowserBin()
  ensure(browserBin, "Could not find Chrome/Chromium for rendered watch smoke; set SMOKE_BROWSER_BIN or SMOKE_SKIP_RENDER_CHECK=true")
  const result = await runCommand(browserBin, [
    "--headless=new",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
    "--no-sandbox",
    `--virtual-time-budget=${Math.max(TIMEOUT_MS, 12000)}`,
    "--dump-dom",
    url,
  ], { timeoutMs: Math.max(TIMEOUT_MS + 5000, 25000) })
  ensure(result.code === 0, `Rendered watch page check failed with exit ${result.code ?? "timeout"}: ${result.stderr.slice(0, 400)}`)
  return result.stdout
}

async function resolveLatestArchivedRunId() {
  const archive = await fetchJson(`${API_BASE}/api/reports/archive/runs?limit=1`)
  const runId = String(archive?.items?.[0]?.run_id || "").trim()
  ensure(runId, "Could not resolve latest archived run id")
  return runId
}

async function resolveDefaultWatchRunId() {
  if (RUN_ID) return RUN_ID
  const overview = await fetchJson(`${API_BASE}/api/analytics/overview`).catch(() => null)
  const scope = overview?.scope || {}
  const activeRunId = String(scope.active_run_id || "").trim()
  if (scope.simulation_active === true && scope.simulation_paused !== true && activeRunId) {
    return activeRunId
  }
  return resolveLatestArchivedRunId()
}

async function resolveDefaultRenderRunId(explicitRunId) {
  if (RUN_ID) return explicitRunId
  return resolveDefaultWatchRunId()
}

async function resolveSmokeRunIds() {
  const archive = await fetchJson(`${API_BASE}/api/reports/archive/runs?limit=1`)
  const explicitRunId = String(archive?.items?.[0]?.run_id || "").trim()
  ensure(explicitRunId, "Could not resolve latest archived run id")
  const defaultRunId = await resolveDefaultRenderRunId(explicitRunId)
  return { explicitRunId, defaultRunId }
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

function validateRenderedDefaultWatch(dom, runId, pageUrl) {
  ensure(dom && typeof dom === "string", "Rendered default watch DOM is empty")
  ensure(!dom.includes("__next_error__"), "Default watch route rendered a Next error page")
  ensure(!dom.includes("Application error"), "Default watch route rendered an application error")
  ensure(
    dom.includes("Watch Map") || dom.includes("Watch Replay"),
    "Default watch route missing Watch Map/Watch Replay heading",
  )
  ensure(dom.includes(runId), `Default watch route did not render expected run ${runId}`)
  ensure(dom.includes("Timeline density"), "Default watch route missing timeline density section")
  ensure(dom.includes("Category lanes"), "Default watch route missing category lanes")
  ensure(dom.includes("watch-density-bar"), "Default watch route missing rendered density bars")
  ensure(dom.includes("watch-lane"), "Default watch route missing rendered lanes")
  ensure(!dom.includes("latest-completed-run"), "Default watch route did not resolve beyond the placeholder run id")
  console.log(`[ok] default watch route rendered: ${pageUrl}`)
}

async function main() {
  ensure(API_BASE.length > 0, "Resolved API base is empty")
  const { explicitRunId: runId, defaultRunId } = await resolveSmokeRunIds()
  const watchUrl = `${API_BASE}/api/analytics/runs/${encodeURIComponent(runId)}/watch?bucket_minutes=60&limit=240`
  const payload = await fetchJson(watchUrl)
  validateWatchPayload(payload, runId)
  console.log(`[ok] watch payload: ${watchUrl}`)
  console.log(`     moments=${payload.count}, buckets=${payload.bucket_count}, events=${payload.activity.total_events}`)

  if (!SKIP_SITE_CHECK) {
    const pageUrl = `${SITE_BASE}/watch?run=${encodeURIComponent(runId)}`
    await fetchWithTimeout(pageUrl)
    console.log(`[ok] watch page reachable: ${pageUrl}`)

    if (!SKIP_RENDER_CHECK) {
      const defaultPageUrl = `${SITE_BASE}/watch?smoke=default-route`
      const dom = await dumpRenderedDom(defaultPageUrl)
      validateRenderedDefaultWatch(dom, defaultRunId, defaultPageUrl)
    }
  }

  console.log("")
  console.log(`[done] Watch map smoke passed for site=${SITE_BASE}, api=${API_BASE}, run=${runId}, default=${defaultRunId}`)
}

main().catch((error) => {
  console.error(`[fail] ${error?.message || error}`)
  process.exitCode = 1
})
