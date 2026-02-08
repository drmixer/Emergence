import type { Metadata } from "next"
import Link from "next/link"
import { ArrowLeft, ArrowUpRight, CalendarDays } from "lucide-react"
import { fetchPublishedArticles, formatArticleDateLong } from "@/lib/articles"

export const metadata: Metadata = {
  title: "Archive Articles | EMERGENCE",
  description: "Research notes and field reports from the Emergence simulation archive.",
}

export default async function ArticlesPage() {
  const articles = await fetchPublishedArticles(50)

  return (
    <main className="relative min-h-screen px-4 py-16 md:pl-28 md:pr-12">
      <div className="grid-bg fixed inset-0 opacity-30" aria-hidden="true" />
      <div className="relative z-10 mx-auto max-w-5xl">
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Landing
        </Link>

        <header className="mt-8 border border-border/60 bg-card/50 p-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Archive Index</p>
          <h1 className="mt-4 font-[var(--font-bebas)] text-6xl tracking-tight md:text-7xl">Articles</h1>
          <p className="mt-4 max-w-2xl font-mono text-sm leading-relaxed text-muted-foreground">
            Field reports from the live simulation. Each piece captures one emergent dynamic and connects it to
            historical research on cooperation, conflict, and governance.
          </p>
        </header>

        <section className="mt-10 space-y-6">
          {articles.length === 0 ? (
            <article className="border border-border/60 bg-card/40 p-8">
              <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">No Entries Yet</p>
              <p className="mt-3 max-w-2xl font-mono text-sm leading-relaxed text-muted-foreground">
                The archive is active, but no articles have been published yet.
              </p>
            </article>
          ) : (
            articles.map((article, index) => (
              <article
                key={article.slug}
                className="group border border-border/60 bg-card/40 p-8 transition-colors hover:border-foreground/50"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
                    No. {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {formatArticleDateLong(article.publishedAt)}
                  </span>
                </div>
                <h2 className="mt-5 font-[var(--font-bebas)] text-5xl leading-none tracking-tight md:text-6xl">
                  {article.title}
                </h2>
                <p className="mt-4 max-w-3xl font-mono text-sm leading-relaxed text-muted-foreground">{article.summary}</p>
                <Link
                  href={`/articles/${article.slug}`}
                  className="mt-6 inline-flex items-center gap-2 font-mono text-xs uppercase tracking-[0.22em] text-foreground"
                >
                  Read article
                  <ArrowUpRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </Link>
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  )
}
