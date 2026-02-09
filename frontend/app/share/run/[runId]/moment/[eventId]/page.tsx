import type { Metadata } from "next"
import Link from "next/link"
import { ShareRedirect } from "@/components/share-redirect"
import { resolvePublicApiBase, resolveSiteBase, withDeployVersion } from "@/lib/share"

type ShareRunMomentPageProps = {
  params: Promise<{ runId: string; eventId: string }>
}

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: ShareRunMomentPageProps): Promise<Metadata> {
  const { runId, eventId } = await params
  const safeRunId = encodeURIComponent(String(runId || "").trim())
  const safeEventId = encodeURIComponent(String(eventId || "").trim())
  const apiBase = resolvePublicApiBase()
  const siteBase = resolveSiteBase()
  const imageUrl = withDeployVersion(
    `${apiBase}/api/analytics/moments/${safeEventId}/social-card.png?run_id=${safeRunId}`
  )
  const pageUrl = `${siteBase}/share/run/${safeRunId}/moment/${safeEventId}`

  return {
    title: `Run ${runId} • Moment #${eventId} | EMERGENCE`,
    description: `Evidence-backed moment from run ${runId} in Emergence.`,
    robots: { index: false, follow: false },
    openGraph: {
      title: `Run ${runId} • Moment #${eventId} | EMERGENCE`,
      description: `Evidence-backed moment from run ${runId}.`,
      url: pageUrl,
      type: "website",
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: `Emergence run ${runId} moment ${eventId} social card`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: `Run ${runId} • Moment #${eventId} | EMERGENCE`,
      description: `Evidence-backed moment from run ${runId}.`,
      images: [imageUrl],
    },
  }
}

export default async function ShareRunMomentPage({ params }: ShareRunMomentPageProps) {
  const { runId, eventId } = await params
  const safeRunId = encodeURIComponent(String(runId || "").trim())
  const safeEventId = encodeURIComponent(String(eventId || "").trim())
  const targetPath = `/runs/${safeRunId}?event=${safeEventId}&kpi_src=share_run_moment`

  return (
    <main className="relative min-h-screen px-4 py-20 md:pl-24 md:pr-12">
      <ShareRedirect
        targetPath={targetPath}
        kpiSource="share_run_moment"
        runId={String(runId || "").trim()}
        eventId={Number.parseInt(String(eventId || "0"), 10) || null}
      />
      <div className="mx-auto max-w-2xl border border-border/60 bg-card/60 p-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">Share Redirect</p>
        <h1 className="mt-4 font-[var(--font-bebas)] text-5xl tracking-tight">Run {runId} · Moment #{eventId}</h1>
        <p className="mt-4 font-mono text-sm text-muted-foreground">
          Opening the run detail view for this moment. If redirect does not start, use the link below.
        </p>
        <Link href={targetPath} className="mt-6 inline-flex font-mono text-xs uppercase tracking-[0.2em] underline">
          Open run moment
        </Link>
      </div>
    </main>
  )
}
