export function resolvePublicApiBase(): string {
  const raw =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.VITE_API_URL ||
    "http://localhost:8000"
  return String(raw).replace(/\/$/, "")
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
