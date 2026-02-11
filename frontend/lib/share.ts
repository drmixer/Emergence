import { resolveApiBase } from "@/lib/api-base"

export function resolvePublicApiBase(): string {
  return resolveApiBase()
}

export function resolveDeployVersion(): string {
  const candidates = [
    process.env.NEXT_PUBLIC_DEPLOY_VERSION,
    process.env.VERCEL_GIT_COMMIT_SHA,
    process.env.RAILWAY_GIT_COMMIT_SHA,
    process.env.VERCEL_DEPLOYMENT_ID,
    process.env.RAILWAY_DEPLOYMENT_ID,
    process.env.BUILD_ID,
  ]

  for (const value of candidates) {
    const clean = String(value || "").trim()
    if (clean) {
      return clean.slice(0, 80)
    }
  }

  return ""
}

export function withDeployVersion(url: string): string {
  const deployVersion = resolveDeployVersion()
  if (!deployVersion) {
    return url
  }

  try {
    const parsed = new URL(url)
    parsed.searchParams.set("v", deployVersion)
    return parsed.toString()
  } catch {
    const separator = url.includes("?") ? "&" : "?"
    return `${url}${separator}v=${encodeURIComponent(deployVersion)}`
  }
}

export function resolveSiteBase(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL
  if (configured) {
    return String(configured).replace(/\/$/, "")
  }

  const vercelUrl = process.env.VERCEL_URL
  if (vercelUrl) {
    const safe = String(vercelUrl).replace(/\/$/, "")
    return safe.startsWith("http") ? safe : `https://${safe}`
  }

  return "http://localhost:3000"
}
