const LOCAL_DEV_BACKEND_BASE = "http://localhost:8000"
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0"])

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

export function resolveConfiguredApiBase() {
  return normalizeConfiguredBase(resolveConfiguredBase())
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

function isLocalHost(value) {
  return LOCAL_HOSTS.has(hostFromUrl(value))
}

export function resolveApiBase({
  allowWindowOrigin = false,
  fallbackLocalBase = LOCAL_DEV_BACKEND_BASE,
  siteBaseHint = "",
} = {}) {
  const configuredBase = resolveConfiguredApiBase()
  if (configuredBase) return configuredBase

  if (allowWindowOrigin && typeof window !== "undefined" && window.location?.origin) {
    const origin = trimBaseUrl(window.location.origin)
    if (origin) return origin
  }

  const localCandidates = [
    siteBaseHint,
    readEnvVar("NEXT_PUBLIC_SITE_URL"),
    readEnvVar("VERCEL_URL"),
    readEnvVar("RAILWAY_PUBLIC_DOMAIN"),
  ]

  if (typeof window !== "undefined" && window.location?.hostname) {
    localCandidates.unshift(window.location.hostname)
  } else if (String(globalThis?.process?.env?.NODE_ENV || "").toLowerCase() !== "production") {
    localCandidates.unshift("localhost")
  }

  if (localCandidates.some(isLocalHost)) {
    return trimBaseUrl(fallbackLocalBase) || LOCAL_DEV_BACKEND_BASE
  }

  return ""
}
