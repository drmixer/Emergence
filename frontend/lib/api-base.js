const EMERGENCE_BACKEND_BASE = "https://backend-production-2f66.up.railway.app"
const EMERGENCE_HOSTS = new Set(["emergence.quest", "www.emergence.quest"])
const LOCAL_DEV_BACKEND_BASE = "http://localhost:8000"

function trimBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "")
}

function readEnvVar(name) {
  if (typeof globalThis !== "undefined" && globalThis?.process?.env) {
    const value = trimBaseUrl(globalThis.process.env[name])
    if (value) return value
  }
  if (typeof import.meta !== "undefined" && import.meta?.env) {
    const value = trimBaseUrl(import.meta.env[name])
    if (value) return value
  }
  return ""
}

function resolveConfiguredBase() {
  return readEnvVar("NEXT_PUBLIC_API_URL") || readEnvVar("VITE_API_URL")
}

function normalizeConfiguredBase(configuredBase) {
  const clean = trimBaseUrl(configuredBase)
  if (!clean) return ""
  if (
    typeof window !== "undefined" &&
    window.location?.protocol === "https:" &&
    clean.startsWith("http://")
  ) {
    return clean.replace(/^http:\/\//, "https://")
  }
  return clean
}

function hostFromUrl(rawValue) {
  const clean = trimBaseUrl(rawValue)
  if (!clean) return ""
  try {
    return String(new URL(clean).hostname || "").toLowerCase()
  } catch {
    return String(clean).toLowerCase()
  }
}

function resolveKnownHostFallback(siteBaseHint = "") {
  if (typeof window !== "undefined" && window.location?.hostname) {
    const host = String(window.location.hostname || "").toLowerCase()
    if (EMERGENCE_HOSTS.has(host)) return EMERGENCE_BACKEND_BASE
  }

  const hostCandidates = [
    siteBaseHint,
    readEnvVar("NEXT_PUBLIC_SITE_URL"),
    readEnvVar("VERCEL_URL"),
    readEnvVar("RAILWAY_PUBLIC_DOMAIN"),
  ]
  for (const candidate of hostCandidates) {
    const host = hostFromUrl(candidate)
    if (EMERGENCE_HOSTS.has(host)) return EMERGENCE_BACKEND_BASE
  }

  return ""
}

export function resolveApiBase({
  allowWindowOrigin = false,
  fallbackLocalBase = LOCAL_DEV_BACKEND_BASE,
  siteBaseHint = "",
} = {}) {
  const configuredBase = normalizeConfiguredBase(resolveConfiguredBase())
  if (configuredBase) return configuredBase

  const knownHostBase = resolveKnownHostFallback(siteBaseHint)
  if (knownHostBase) return knownHostBase

  if (allowWindowOrigin && typeof window !== "undefined" && window.location?.origin) {
    const origin = trimBaseUrl(window.location.origin)
    if (origin) return origin
  }

  return trimBaseUrl(fallbackLocalBase) || LOCAL_DEV_BACKEND_BASE
}
