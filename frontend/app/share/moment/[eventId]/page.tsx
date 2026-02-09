import type { Metadata } from "next"
import Link from "next/link"
import { ShareRedirect } from "@/components/share-redirect"
import { resolvePublicApiBase, resolveSiteBase, withDeployVersion } from "@/lib/share"

type ShareMomentPageProps = {
  params: Promise<{ eventId: string }>
}

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: ShareMomentPageProps): Promise<Metadata> {
  const { eventId } = await params
  const safeEventId = encodeURIComponent(String(eventId || "").trim())
  const apiBase = resolvePublicApiBase()
  const siteBase = resolveSiteBase()
  const imageUrl = withDeployVersion(`${apiBase}/api/analytics/moments/${safeEventId}/social-card.png`)
  const pageUrl = `${siteBase}/share/moment/${safeEventId}`

  return {
    title: `Moment #${eventId} | EMERGENCE`,
    description: `High-salience simulation moment from Emergence.`,
    robots: { index: false, follow: false },
    openGraph: {
      title: `Moment #${eventId} | EMERGENCE`,
      description: `High-salience event trace from the Emergence simulation.`,
      url: pageUrl,
      type: "website",
      images: [
        {
          url: imageUrl,
          width: 1200,
          height: 630,
          alt: `Emergence moment ${eventId} social card`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: `Moment #${eventId} | EMERGENCE`,
      description: `High-salience event trace from the Emergence simulation.`,
      images: [imageUrl],
    },
  }
}

export default async function ShareMomentPage({ params }: ShareMomentPageProps) {
  const { eventId } = await params
  const safeEventId = encodeURIComponent(String(eventId || "").trim())
  const targetPath = `/highlights?tab=replay&event=${safeEventId}&kpi_src=share_moment`

  return (
    <main className="relative min-h-screen px-4 py-20 md:pl-24 md:pr-12">
      <ShareRedirect
        targetPath={targetPath}
        kpiSource="share_moment"
        eventId={Number.parseInt(String(eventId || "0"), 10) || null}
      />
      <div className="mx-auto max-w-2xl border border-border/60 bg-card/60 p-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted-foreground">Share Redirect</p>
        <h1 className="mt-4 font-[var(--font-bebas)] text-5xl tracking-tight">Moment #{eventId}</h1>
        <p className="mt-4 font-mono text-sm text-muted-foreground">
          Opening highlights replay. If redirect does not start, use the link below.
        </p>
        <Link href={targetPath} className="mt-6 inline-flex font-mono text-xs uppercase tracking-[0.2em] underline">
          Open highlights replay
        </Link>
      </div>
    </main>
  )
}
