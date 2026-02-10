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
  contentType: "technical_report" | "approachable_article"
  statusLabel: "observational" | "replicated"
  evidenceCompleteness: "full" | "partial"
  tags: string[]
  linkedRecordIds: number[]
  evidenceRunId?: string | null
}

export type ArticleFilterOptions = {
  limit?: number
  contentType?: "technical_report" | "approachable_article" | "all"
  tag?: string
}

const INITIAL_ARTICLE_SLUG = "before-the-first-full-run"
const ARCHIVE_MODE = process.env.NEXT_PUBLIC_ARCHIVE_MODE === "all" ? "all" : "baseline-only"

const fallbackArticles: Article[] = [
  {
    slug: INITIAL_ARTICLE_SLUG,
    title: "Before the First Full Run",
    summary:
      "Emergence is readying a controlled experiment in AI society formation. This first archive note documents the protocol, constraints, and evidence standards we will use before claiming any empirical findings.",
    publishedAt: "2026-02-08",
    contentType: "approachable_article",
    statusLabel: "observational",
    evidenceCompleteness: "partial",
    tags: [
      "run_id:not-set",
      "season:unknown",
      "condition:baseline-methodology",
      "topic:governance",
      "status:observational",
      "evidence:partial",
    ],
    linkedRecordIds: [],
    sections: [
      {
        heading: "Why This Entry Exists",
        paragraphs: [
          "No full production-valid run has completed yet. Publishing that fact explicitly is important because this archive is meant to be evidence-driven, not narrative-first.",
          "This post is therefore a baseline document: what Emergence is, what we are actually testing, and how claims will be validated once real runs complete.",
          "When empirical posts start, each one will be anchored to specific run IDs, timestamps, and metrics so readers can audit the story against the underlying trace.",
        ],
      },
      {
        heading: "What the Experiment Is Testing",
        paragraphs: [
          "Emergence is a social systems experiment: autonomous agents share an environment with resource scarcity, persistent memory, proposal/voting mechanisms, and permanent death pressure.",
          "The central question is not whether one model can optimize a toy task. It is whether durable social structures form under pressure: cooperation networks, trust regimes, governance norms, conflict cycles, and collapse/recovery patterns.",
          "We are studying adaptive order formation, not marketing benchmark performance.",
        ],
        references: [
          {
            label: "Project Repository",
            href: "https://github.com/drmixer/Emergence",
          },
        ],
      },
      {
        heading: "What Counts as a Real Run",
        paragraphs: [
          "A run is considered valid when it has a stable run ID, continuous progression over meaningful simulation time, complete telemetry capture, and no ad hoc manual steering during active epochs beyond declared guardrails.",
          "Interrupted tests, local smoke checks, and partial burn-ins are useful for engineering, but they are not treated as empirical evidence about emergent social dynamics.",
          "This distinction protects the archive from overinterpreting noisy setup behavior.",
        ],
      },
      {
        heading: "How Findings Will Be Reported",
        paragraphs: [
          "Each future article will separate observations from interpretation. Observation means concrete events and metrics. Interpretation means proposed mechanisms that could explain those events.",
          "Claims will be graded by confidence and updated if later runs contradict earlier patterns. That is expected in a young complex system.",
          "Where possible, posts will link out to the relevant dashboard views, metrics snapshots, and source traces.",
        ],
        references: [
          {
            label: "Methodology Notes",
            href: "https://github.com/drmixer/Emergence/blob/main/README.md",
          },
        ],
      },
      {
        heading: "What Comes Next",
        paragraphs: [
          "The next archive entry should be the first run-backed report, not a prewritten thesis. If coalitions, governance behavior, or trust cascades appear, they will be documented with evidence.",
          "If the first runs are chaotic, inconclusive, or fail in unexpected ways, that will be published too.",
          "The standard is simple: no claims beyond the data.",
        ],
      },
    ],
  },
]

function byMostRecent(a: Article, b: Article) {
  return new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime()
}

function selectPublicArticles(allArticles: Article[]) {
  const sorted = [...allArticles].sort(byMostRecent)
  if (ARCHIVE_MODE === "all") return sorted
  const baseline = sorted.find((article) => article.slug === INITIAL_ARTICLE_SLUG)
  return baseline ? [baseline] : getArticles().filter((article) => article.slug === INITIAL_ARTICLE_SLUG)
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
  const contentTypeRaw = String(entry.content_type ?? entry.contentType ?? "approachable_article").trim().toLowerCase()
  const contentType = contentTypeRaw === "technical_report" ? "technical_report" : "approachable_article"
  const statusLabelRaw = String(entry.status_label ?? entry.statusLabel ?? "observational").trim().toLowerCase()
  const statusLabel = statusLabelRaw === "replicated" ? "replicated" : "observational"
  const evidenceRaw = String(entry.evidence_completeness ?? entry.evidenceCompleteness ?? "partial").trim().toLowerCase()
  const evidenceCompleteness = evidenceRaw === "full" ? "full" : "partial"
  const tags = Array.isArray(entry.tags)
    ? entry.tags
        .map((tag) => String(tag ?? "").trim().toLowerCase())
        .filter(Boolean)
        .filter((tag, index, source) => source.indexOf(tag) === index)
    : []
  const linkedIdsRaw = entry.linked_record_ids ?? entry.linkedRecordIds
  const linkedRecordIds = Array.isArray(linkedIdsRaw)
    ? linkedIdsRaw
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0)
        .filter((value, index, source) => source.indexOf(value) === index)
    : []
  const evidenceRunId = String(entry.evidence_run_id ?? entry.evidenceRunId ?? "").trim() || null
  if (!slug || !title || !summary || !publishedAt || sections.length === 0) return null
  return {
    slug,
    title,
    summary,
    publishedAt,
    sections,
    contentType,
    statusLabel,
    evidenceCompleteness,
    tags,
    linkedRecordIds,
    evidenceRunId,
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

export async function fetchPublishedArticles(options: number | ArticleFilterOptions = 20) {
  const resolvedOptions: ArticleFilterOptions =
    typeof options === "number"
      ? { limit: options }
      : { ...(options || {}) }
  const resolvedLimit = Math.max(1, Number(resolvedOptions.limit ?? 20))
  const resolvedContentType = String(resolvedOptions.contentType || "all").trim().toLowerCase()
  const contentType =
    resolvedContentType === "technical_report" || resolvedContentType === "approachable_article"
      ? resolvedContentType
      : "all"
  const tag = String(resolvedOptions.tag || "").trim().toLowerCase()

  const apiBase = resolveApiBase()
  if (!apiBase) {
    const local = selectPublicArticles(getArticles())
      .filter((article) => (contentType === "all" ? true : article.contentType === contentType))
      .filter((article) => (tag ? article.tags.includes(tag) : true))
    return local.slice(0, resolvedLimit)
  }

  try {
    const params = new URLSearchParams()
    params.append("limit", String(resolvedLimit))
    if (contentType !== "all") params.append("content_type", contentType)
    if (tag) params.append("tag", tag)
    const response = await fetch(`${apiBase}/api/archive/articles?${params.toString()}`, {
      cache: "no-store",
    })
    if (!response.ok) throw new Error(`Failed to load archive articles (${response.status})`)
    const payload = (await response.json()) as { items?: unknown[] }
    const normalized = Array.isArray(payload?.items) ? payload.items.map(normalizeArticle).filter(Boolean) : []
    return selectPublicArticles(normalized as Article[]).slice(0, resolvedLimit)
  } catch {
    const local = selectPublicArticles(getArticles())
      .filter((article) => (contentType === "all" ? true : article.contentType === contentType))
      .filter((article) => (tag ? article.tags.includes(tag) : true))
    return local.slice(0, resolvedLimit)
  }
}

export async function fetchPublishedArticleBySlug(slug: string) {
  const safeSlug = String(slug || "").trim()
  if (!safeSlug) return undefined
  if (ARCHIVE_MODE !== "all" && safeSlug !== INITIAL_ARTICLE_SLUG) return undefined

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
