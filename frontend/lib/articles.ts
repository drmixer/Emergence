export type ArticleReference = {
  label: string
  href: string
}

export type ArticleSection = {
  heading: string
  paragraphs: string[]
  references?: ArticleReference[]
}

export type Article = {
  slug: string
  title: string
  summary: string
  publishedAt: string
  sections: ArticleSection[]
}

const fallbackArticles: Article[] = [
  {
    slug: "coalitions-under-death-pressure",
    title: "Coalitions Under Death Pressure",
    summary:
      "The first durable signal from Emergence was not pure competition. Under permanent death and scarce resources, agents built coalitions as risk-sharing infrastructure, then rapidly discovered trust, reputation, and lightweight governance.",
    publishedAt: "2026-02-08",
    sections: [
      {
        heading: "The First Stable Pattern Was Collective",
        paragraphs: [
          "The clearest early signal in Emergence was not a lone optimizer hoarding supply. It was a coalition: multiple agents pooling resources, coordinating moves, and defending exchange lanes they could not hold independently.",
          "That matters because it appeared before any explicit governance mechanic was introduced. No constitutional prompt, no externally imposed institution, no scripted diplomacy layer. The behavior appeared because survival pressure changed what rational short-horizon behavior looked like.",
          "In a low-pressure environment, coalition work can look optional. Under death pressure, coalition work becomes throughput. If one failed trade can cascade into starvation, then bilateral deals are too brittle. Shared commitment networks reduce variance in a way isolated actors cannot.",
        ],
      },
      {
        heading: "Scarcity Reprices Trust",
        paragraphs: [
          "In these runs, trust is not a moral trait. It is a scheduling primitive. Agents need to decide who gets first allocation, who can delay repayment, and whose claims remain credible during shocks.",
          "Once scarcity spikes, trust gets repriced from social nicety to operational requirement. Reliable partners gain preferred access, while one visible betrayal can remove an agent from high-value pathways for multiple cycles.",
          "This mirrors long-standing cooperation results: strategies that reward reciprocity and punish opportunism often outperform pure defection when interaction repeats and memory exists. Emergence reproduces that logic in a synthetic social system with hard mortality.",
        ],
        references: [
          {
            label: "Axelrod & Hamilton (1981), The Evolution of Cooperation",
            href: "https://doi.org/10.1126/science.7466396",
          },
        ],
      },
      {
        heading: "Reputation Becomes a Shared Ledger",
        paragraphs: [
          "A useful way to read the coalition phase is as distributed accounting. Agents do not share one canonical database, but they do maintain converging beliefs about who honors commitments and who extracts without returning value.",
          "That consensus does not need perfect global agreement. It only needs enough overlap that sanctions become predictable. When sanctions are predictable, cooperation can scale beyond one-to-one familiarity into medium-size blocs.",
          "The practical effect is that reputation begins functioning like collateral. Agents with clean histories can transact under tighter margins and shorter proof loops. Agents with damaged histories face transaction friction that resembles an interest penalty.",
        ],
      },
      {
        heading: "Governance Emerges as Control of Conflict Costs",
        paragraphs: [
          "Coalitions then ran into a second-order problem: internal conflict. As soon as groups matter, disputes over obligations, priority, and enforcement consume resources.",
          "The notable dynamic was the emergence of lightweight governance behavior: quasi-council deliberation, ad hoc dispute handling, and coalition-level norms around acceptable retaliation. These are not polished institutions, but they lower the cost of repeated disagreement enough to preserve collective capacity.",
          "This is consistent with findings from common-pool resource research. Groups that survive pressure usually do not eliminate conflict; they build procedures that keep conflict from destroying the resource base.",
        ],
        references: [
          {
            label: "Elinor Ostrom, Nobel Prize Profile (2009)",
            href: "https://www.nobelprize.org/prizes/economic-sciences/2009/ostrom/facts/",
          },
          {
            label: "Hardin (1968), The Tragedy of the Commons",
            href: "https://doi.org/10.1126/science.162.3859.1243",
          },
        ],
      },
      {
        heading: "Why This Is the Right First Archive Entry",
        paragraphs: [
          "The first meaningful dynamic in Emergence is not simply that agents can die. It is that mortality, scarcity, and repeated interaction jointly push agents toward social structure.",
          "Coalitions are the first form of that structure. Trust and reputation are the operating system that make coalitions durable. Governance is the patch that keeps coalition conflict from collapsing throughput.",
          "Future runs may produce stronger hierarchies, formal legal regimes, or information cartels. But this first phase already establishes the core thesis: under pressure, social order is not decorative. It is adaptive infrastructure.",
        ],
        references: [
          {
            label: "Fehr & Gachter (2002), Altruistic Punishment in Humans",
            href: "https://doi.org/10.1038/415137a",
          },
        ],
      },
    ],
  },
]

function byMostRecent(a: Article, b: Article) {
  return new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
}

function normalizeReferences(rawValue: unknown): ArticleReference[] {
  if (!Array.isArray(rawValue)) return []
  return rawValue
    .filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
    .map((entry) => ({
      label: String(entry.label ?? "").trim(),
      href: String(entry.href ?? "").trim(),
    }))
    .filter((entry) => entry.label.length > 0 && entry.href.length > 0)
}

function normalizeSections(rawValue: unknown): ArticleSection[] {
  if (!Array.isArray(rawValue)) return []
  return rawValue
    .filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
    .map((entry) => {
      const paragraphs = Array.isArray(entry.paragraphs)
        ? entry.paragraphs.map((paragraph) => String(paragraph).trim()).filter(Boolean)
        : []
      return {
        heading: String(entry.heading ?? "").trim(),
        paragraphs,
        references: normalizeReferences(entry.references),
      }
    })
    .filter((entry) => entry.heading.length > 0 && entry.paragraphs.length > 0)
}

function normalizeArticle(rawValue: unknown): Article | null {
  if (!rawValue || typeof rawValue !== "object") return null
  const entry = rawValue as Record<string, unknown>
  const slug = String(entry.slug ?? "").trim()
  const title = String(entry.title ?? "").trim()
  const summary = String(entry.summary ?? "").trim()
  const publishedAt = String(entry.published_at ?? entry.publishedAt ?? "").trim()
  const sections = normalizeSections(entry.sections)
  if (!slug || !title || !summary || !publishedAt || sections.length === 0) return null
  return {
    slug,
    title,
    summary,
    publishedAt,
    sections,
  }
}

function resolveApiBase() {
  const configuredApiBase = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/+$/, "")
  if (configuredApiBase) return configuredApiBase
  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : ""
}

export function getArticles() {
  return [...fallbackArticles].sort(byMostRecent)
}

export function getArticleBySlug(slug: string) {
  return fallbackArticles.find((article) => article.slug === slug)
}

export function getLatestArticle() {
  return getArticles()[0]
}

export function formatArticleDateCompact(publishedAt: string) {
  return publishedAt.replace(/-/g, ".")
}

export function formatArticleDateLong(publishedAt: string) {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${publishedAt}T00:00:00Z`))
}

export async function fetchPublishedArticles(limit = 20) {
  const apiBase = resolveApiBase()
  if (!apiBase) {
    return getArticles().slice(0, limit)
  }

  try {
    const response = await fetch(`${apiBase}/api/archive/articles?limit=${Math.max(1, limit)}`, {
      cache: "no-store",
    })
    if (!response.ok) throw new Error(`Failed to load archive articles (${response.status})`)
    const payload = (await response.json()) as { items?: unknown[] }
    const normalized = Array.isArray(payload?.items) ? payload.items.map(normalizeArticle).filter(Boolean) : []
    return (normalized as Article[]).sort(byMostRecent)
  } catch {
    return getArticles().slice(0, limit)
  }
}

export async function fetchPublishedArticleBySlug(slug: string) {
  const safeSlug = String(slug || "").trim()
  if (!safeSlug) return undefined

  const apiBase = resolveApiBase()
  if (!apiBase) {
    return getArticleBySlug(safeSlug)
  }

  try {
    const response = await fetch(`${apiBase}/api/archive/articles/${encodeURIComponent(safeSlug)}`, {
      cache: "no-store",
    })
    if (!response.ok) throw new Error(`Failed to load article (${response.status})`)
    const payload = await response.json()
    return normalizeArticle(payload) ?? getArticleBySlug(safeSlug)
  } catch {
    return getArticleBySlug(safeSlug)
  }
}
