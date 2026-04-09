/* global process */

const LOCAL_DEV_BACKEND_BASE = "http://localhost:8000"
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0"])
const PRODUCTION_API_HOST = "https://api.emergence.quest"

function trimBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "")
}

function readEnvVar(name) {
  const nodeEnv =
    typeof process !== "undefined" && process?.env
      ? {
          NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
          VITE_API_URL: process.env.VITE_API_URL,
          NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
          VERCEL_URL: process.env.VERCEL_URL,
          RAILWAY_PUBLIC_DOMAIN: process.env.RAILWAY_PUBLIC_DOMAIN,
        }
      : null

  if (nodeEnv && Object.prototype.hasOwnProperty.call(nodeEnv, name)) {
    const value = trimBaseUrl(nodeEnv[name])
    if (value) return value
  }

  if (typeof import.meta !== "undefined" && import.meta?.env) {
    const viteEnv =
      name === "NEXT_PUBLIC_API_URL"
        ? import.meta.env.NEXT_PUBLIC_API_URL
        : name === "VITE_API_URL"
          ? import.meta.env.VITE_API_URL
          : name === "NEXT_PUBLIC_SITE_URL"
            ? import.meta.env.NEXT_PUBLIC_SITE_URL
            : name === "VERCEL_URL"
              ? import.meta.env.VERCEL_URL
              : name === "RAILWAY_PUBLIC_DOMAIN"
                ? import.meta.env.RAILWAY_PUBLIC_DOMAIN
                : ""
    const value = trimBaseUrl(viteEnv)
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

function inferProductionApiBase() {
  if (typeof window === "undefined" || !window.location?.hostname) return ""
  const host = String(window.location.hostname || "").toLowerCase()
  if (host === "emergence.quest" || host === "www.emergence.quest") {
    return PRODUCTION_API_HOST
  }
  return ""
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

  const inferredProductionBase = inferProductionApiBase()
  if (inferredProductionBase) {
    return inferredProductionBase
  }

  return ""
}
