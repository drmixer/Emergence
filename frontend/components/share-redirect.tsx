"use client"

import { useEffect } from "react"
import { trackKpiEventOnce } from "@/lib/kpi-client"

type ShareRedirectProps = {
  targetPath: string
  kpiSource: string
  runId?: string
  eventId?: number | null
}

export function ShareRedirect({ targetPath, kpiSource, runId = "", eventId = null }: ShareRedirectProps) {
  useEffect(() => {
    const normalizedSource = String(kpiSource || "").trim() || "share_unknown"
    trackKpiEventOnce(
      "shared_link_open",
      `share_redirect:${normalizedSource}:${runId}:${eventId || 0}:${targetPath}`,
      {
        runId: runId || null,
        eventId: eventId || null,
        surface: "share_redirect",
        target: normalizedSource,
      }
    )

    const timer = window.setTimeout(() => {
      window.location.replace(targetPath)
    }, 50)
    return () => window.clearTimeout(timer)
  }, [targetPath, kpiSource, runId, eventId])

  return null
}

