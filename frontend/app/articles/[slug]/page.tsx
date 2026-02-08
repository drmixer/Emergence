import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowLeft, CalendarDays } from "lucide-react"
import { fetchPublishedArticleBySlug, formatArticleDateLong } from "@/lib/articles"

type ArticlePageProps = {
  params: Promise<{ slug: string }>
}

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: ArticlePageProps): Promise<Metadata> {
  const { slug } = await params
  const article = await fetchPublishedArticleBySlug(slug)

  if (!article) {
    return {
      title: "Article Not Found | EMERGENCE",
    }
  }

  return {
    title: `${article.title} | EMERGENCE`,
    description: article.summary,
  }
}

export default async function ArticlePage({ params }: ArticlePageProps) {
  const { slug } = await params
  const article = await fetchPublishedArticleBySlug(slug)

  if (!article) {
    notFound()
  }

  return (
    <main className="relative min-h-screen px-4 py-16 md:pl-28 md:pr-12">
      <div className="grid-bg fixed inset-0 opacity-30" aria-hidden="true" />
      <article className="relative z-10 mx-auto max-w-3xl border border-border/60 bg-card/40 p-8 md:p-10">
        <Link
          href="/articles"
          className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Archive
        </Link>

        <header className="mt-8 border-t border-border/50 pt-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Archive Field Report</p>
          <h1 className="mt-4 font-[var(--font-bebas)] text-5xl leading-none tracking-tight md:text-6xl">{article.title}</h1>
          <div className="mt-6 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            <CalendarDays className="h-3.5 w-3.5" />
            {formatArticleDateLong(article.publishedAt)}
          </div>
          <p className="mt-6 max-w-2xl font-sans text-base leading-8 text-foreground/85">{article.summary}</p>
        </header>

        <div className="mt-10 space-y-12">
          {article.sections.map((section) => (
            <section key={section.heading} className="space-y-5 border-l border-border/40 pl-5">
              <h2 className="font-[var(--font-bebas)] text-3xl leading-none tracking-tight md:text-4xl">{section.heading}</h2>
              {section.paragraphs.map((paragraph, paragraphIndex) => (
                <p key={paragraphIndex} className="font-sans text-base leading-8 text-foreground/90">
                  {paragraph}
                </p>
              ))}
              {section.references && section.references.length > 0 ? (
                <div className="pt-2">
                  <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">References</p>
                  <ul className="mt-3 space-y-2">
                    {section.references.map((reference) => (
                      <li key={reference.href}>
                        <a
                          href={reference.href}
                          target="_blank"
                          rel="noreferrer"
                          className="font-sans text-sm text-foreground underline decoration-border underline-offset-4 transition-colors hover:text-muted-foreground"
                        >
                          {reference.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ))}
        </div>
      </article>
    </main>
  )
}
