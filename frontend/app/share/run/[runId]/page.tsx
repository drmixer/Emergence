import type { Metadata } from "next"
import Link from "next/link"
import { ShareRedirect } from "@/components/share-redirect"
import { resolvePublicApiBase, resolveSiteBase, withDeployVersion } from "@/lib/share"

type ShareRunPageProps = {
  params: Promise<{ runId: string }>
}

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: ShareRunPageProps): Promise<Metadata> {
  const { runId } = await params
  const safeRunId = encodeURIComponent(String(runId || "").trim())
  const apiBase = resolvePublicApiBase()
  const siteBase = resolveSiteBase()
  const imageUrl = withDeployVersion(`${apiBase}/api/analytics/runs/${safeRunId}/social-card.png`)
  const pageUrl = `${siteBase}/share/run/${safeRunId}`

  return {
    title: `Run ${runId} | EMERGENCE`,
    description: `Verified run snapshot for ${runId} in the Emergence simulation.`,
    robots: { index: false, follow: false },
    openGraph: {
      title: `Run ${runId} | EMERGENCE`,
      description: `Run-level evidence snapshot with traceable source links.`,
      url: pageUrl,
      type: "website",
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: `Emergence run ${runId} social card`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: `Run ${runId} | EMERGENCE`,
      description: `Run-level evidence snapshot with traceable source links.`,
      images: [imageUrl],
    },
  }
}

export default async function ShareRunPage({ params }: ShareRunPageProps) {
  const { runId } = await params
  const safeRunId = encodeURIComponent(String(runId || "").trim())
  const targetPath = `/runs/${safeRunId}?kpi_src=share_run`

  return (
    <main className="relative min-h-screen px-4 py-20 md:pl-24 md:pr-12">
      <ShareRedirect targetPath={targetPath} kpiSource="share_run" runId={String(runId || "").trim()} />
      <div className="mx-auto max-w-2xl border border-border/60 bg-card/60 p-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">Share Redirect</p>
        <h1 className="mt-4 font-[var(--font-bebas)] text-5xl tracking-tight">Run {runId}</h1>
        <p className="mt-4 font-mono text-sm text-muted-foreground">
          Opening the run detail page. If redirect does not start, use the link below.
        </p>
        <Link href={targetPath} className="mt-6 inline-flex font-mono text-xs uppercase tracking-[0.2em] underline">
          Open run detail
        </Link>
      </div>
    </main>
  )
}
