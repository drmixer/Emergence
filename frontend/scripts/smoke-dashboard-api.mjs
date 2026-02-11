#!/usr/bin/env node

import { resolveApiBase } from "../lib/api-base.js"

const SITE_BASE = String(
  process.env.SMOKE_SITE_BASE || process.env.NEXT_PUBLIC_SITE_URL || "https://www.emergence.quest"
).replace(/\/+$/, "")
const TIMEOUT_MS = Number(process.env.SMOKE_TIMEOUT_MS || 15000)
const SKIP_SITE_CHECK = String(process.env.SMOKE_SKIP_SITE_CHECK || "").toLowerCase() === "true"
const API_BASE = String(
  process.env.SMOKE_API_BASE || resolveApiBase({ siteBaseHint: SITE_BASE })
).replace(/\/+$/, "")

function fail(message) {
  throw new Error(message)
}

function ensure(condition, message) {
  if (!condition) fail(message)
}

async function fetchJson(url) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      redirect: "follow",
      signal: controller.signal,
    })
    ensure(response.ok, `Expected 2xx for ${url}, got ${response.status}`)
    const contentType = String(response.headers.get("content-type") || "").toLowerCase()
    ensure(contentType.includes("application/json"), `Expected JSON for ${url}, got ${contentType || "n/a"}`)
    return await response.json()
  } finally {
    clearTimeout(timer)
  }
}

async function fetchSite(pathname) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  const url = `${SITE_BASE}${pathname}`
  try {
    const response = await fetch(url, { redirect: "follow", signal: controller.signal })
    ensure(response.ok, `Expected 2xx for ${url}, got ${response.status}`)
  } finally {
    clearTimeout(timer)
  }
}

function validateOverview(payload) {
  ensure(payload && typeof payload === "object", "Overview payload must be an object")
  ensure(Number.isFinite(Number(payload.day_number)), "Overview missing numeric day_number")
  ensure(payload.agents && typeof payload.agents === "object", "Overview missing agents object")
}

function validateResources(payload) {
  ensure(payload && typeof payload === "object", "Resources payload must be an object")
  ensure(payload.totals && typeof payload.totals === "object", "Resources missing totals object")
  ensure(payload.common_pool && typeof payload.common_pool === "object", "Resources missing common_pool object")
}

function validateProposals(payload) {
  ensure(Array.isArray(payload), "Proposals payload must be an array")
}

async function main() {
  ensure(API_BASE.length > 0, "Resolved API base is empty")

  if (!SKIP_SITE_CHECK) {
    await fetchSite("/dashboard")
    console.log(`[ok] site reachable: ${SITE_BASE}/dashboard`)
  }

  const checks = [
    {
      path: "/api/analytics/overview",
      label: "analytics_overview",
      validate: validateOverview,
    },
    {
      path: "/api/resources",
      label: "resources",
      validate: validateResources,
    },
    {
      path: "/api/proposals?status=active&limit=5",
      label: "active_proposals",
      validate: validateProposals,
    },
  ]

  for (const check of checks) {
    const url = `${API_BASE}${check.path}`
    const payload = await fetchJson(url)
    check.validate(payload)
    console.log(`[ok] ${check.label}: ${url}`)
  }

  console.log("")
  console.log(`[done] Dashboard API smoke passed for site=${SITE_BASE}, api=${API_BASE}`)
}

main().catch((error) => {
  console.error(`[fail] ${error?.message || error}`)
  process.exitCode = 1
})

