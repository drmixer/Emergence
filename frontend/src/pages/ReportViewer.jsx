import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Download, ExternalLink, FileSearch, FileText, TimerReset } from 'lucide-react'
import { api } from '../services/api'
import { trackKpiEventOnce } from '../services/kpiAnalytics'

const REPORT_LABELS = {
  viewer_brief: 'Emergence Brief',
  approachable_report: 'Approachable Story',
  technical_report: 'Technical Report',
  planner_report: 'Next-Run Plan',
  run_summary: 'Run Summary',
}

const REPORT_DESCRIPTIONS = {
  viewer_brief: 'News-style recap for completed-run viewing, bounded to observed evidence and declared run framing.',
  approachable_report: 'Accessible story report with research boundaries and evidence links.',
  technical_report: 'Technical report for audit and implementation review.',
  planner_report: 'Next-run planning report for operators.',
  run_summary: 'Structured summary data for this completed run.',
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function renderInlineMarkdown(text, keyPrefix) {
  const parts = []
  const pattern = /\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    parts.push(
      <a key={`${keyPrefix}-${match.index}`} href={match[2]} target="_blank" rel="noopener noreferrer">
        {match[1]}
      </a>
    )
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }
  return parts.length > 0 ? parts : text
}

function renderMarkdown(markdown) {
  const lines = String(markdown || '').split(/\r?\n/)
  const blocks = []
  let listItems = []

  function flushList() {
    if (listItems.length === 0) return
    const items = listItems
    listItems = []
    blocks.push(
      <ul key={`list-${blocks.length}`}>
        {items.map((item, index) => (
          <li key={`${index}-${item.slice(0, 18)}`}>{renderInlineMarkdown(item, `li-${blocks.length}-${index}`)}</li>
        ))}
      </ul>
    )
  }

  lines.forEach((line, index) => {
    const text = line.trim()
    if (!text) {
      flushList()
      return
    }
    if (text.startsWith('### ')) {
      flushList()
      blocks.push(<h3 key={`h3-${index}`}>{text.slice(4)}</h3>)
      return
    }
    if (text.startsWith('## ')) {
      flushList()
      blocks.push(<h2 key={`h2-${index}`}>{text.slice(3)}</h2>)
      return
    }
    if (text.startsWith('# ')) {
      flushList()
      blocks.push(<h1 key={`h1-${index}`}>{text.slice(2)}</h1>)
      return
    }
    if (text.startsWith('> ')) {
      flushList()
      blocks.push(<blockquote key={`quote-${index}`}>{renderInlineMarkdown(text.slice(2), `quote-${index}`)}</blockquote>)
      return
    }
    if (text.startsWith('- ')) {
      listItems.push(text.slice(2))
      return
    }
    flushList()
    blocks.push(<p key={`p-${index}`}>{renderInlineMarkdown(text, `p-${index}`)}</p>)
  })
  flushList()

  return blocks
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString()
}

function buildApproachableRecap(runDetail, storyPayload) {
  if (!runDetail || typeof runDetail !== 'object') return null
  const activity = runDetail.activity || {}
  const metadata = runDetail.run_metadata || {}
  const storyItems = Array.isArray(storyPayload?.items) ? storyPayload.items : []
  const events = Number(activity.total_events || 0)
  const deaths = Number(activity.deaths || 0)
  const dormant = Number(activity.became_dormant || 0)
  const laws = Number(activity.laws_passed || 0)
  const proposals = Number(activity.proposal_actions || 0)
  const votes = Number(activity.vote_actions || 0)
  const aid = Number(activity.aid_requests || activity.reserve_aid || 0)
  const trades = Number(activity.trade_actions || 0)
  const publicOrder = Number(activity.public_order_events || activity.conflict_events || 0)
  const condition = formatLabel(metadata.condition_name || 'this run')
  const runClass = String(metadata.run_class || '').trim()
  const boundary = runClass === 'special_exploratory'
    ? 'This is an exploratory public canary, so treat it as a public observation rather than finished research.'
    : 'Treat this as a run recap with evidence links, not a standalone proof.'

  return {
    summary: `${condition} produced ${formatNumber(events)} logged events. The visible arc was survival pressure (${formatNumber(deaths)} deaths and ${formatNumber(dormant)} dormancy events), governance (${formatNumber(proposals)} proposals, ${formatNumber(votes)} votes, ${formatNumber(laws)} laws passed), and coordination pressure (${formatNumber(aid)} aid signals, ${formatNumber(trades)} trades, ${formatNumber(publicOrder)} public-order signals).`,
    boundary,
    moments: storyItems.slice(0, 4).map((item) => ({
      id: Number(item?.event_id || item?.id || 0),
      title: String(item?.title || formatLabel(item?.event_type || item?.category || 'Run moment')).trim(),
      description: String(item?.description || item?.why_this_matters || '').trim(),
    })).filter((item) => item.title || item.description),
  }
}

export default function ReportViewer() {
  const { runId, artifactType } = useParams()
  const [searchParams] = useSearchParams()
  const format = searchParams.get('format') || 'markdown'
  const [reportText, setReportText] = useState('')
  const [recap, setRecap] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const cleanRunId = String(runId || '').trim()
  const cleanArtifactType = String(artifactType || '').trim()
  const label = REPORT_LABELS[cleanArtifactType] || formatLabel(cleanArtifactType)
  const description = REPORT_DESCRIPTIONS[cleanArtifactType] || `In-browser report view for completed run ${cleanRunId || 'unknown-run'}.`
  const replayHref = cleanRunId ? `/runs/${encodeURIComponent(cleanRunId)}/replay?tab=overview` : ''
  const evidenceHref = cleanRunId ? `/runs/${encodeURIComponent(cleanRunId)}` : ''
  const showReaderPath = cleanArtifactType === 'viewer_brief' && cleanRunId

  useEffect(() => {
    if (!cleanRunId || !cleanArtifactType) return
    trackKpiEventOnce('report_opened', `report_opened:${cleanRunId}:${cleanArtifactType}:${format}`, {
      runId: cleanRunId,
      surface: 'report_viewer',
      target: cleanArtifactType,
      metadata: {
        format,
        label,
      },
    })
  }, [cleanArtifactType, cleanRunId, format, label])

  useEffect(() => {
    let cancelled = false
    async function loadReport() {
      if (!cleanRunId || !cleanArtifactType) return
      setLoading(true)
      setError('')
      setRecap(null)
      try {
        const [text, recapPayload] = await Promise.all([
          api.getRunReportText(cleanRunId, cleanArtifactType, format),
          cleanArtifactType === 'approachable_report'
            ? Promise.all([
                api.getRunDetail(cleanRunId, 96, 12, 45),
                api.getReplayStory(96, 45, 6, cleanRunId),
              ])
                .then(([detail, story]) => buildApproachableRecap(detail, story))
                .catch(() => null)
            : Promise.resolve(null),
        ])
        if (!cancelled) setReportText(text)
        if (!cancelled) setRecap(recapPayload)
      } catch (loadError) {
        if (!cancelled) setError(loadError?.message || 'Failed to load report')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadReport()
    return () => {
      cancelled = true
    }
  }, [cleanRunId, cleanArtifactType, format])

  const downloadUrl = useMemo(() => {
    if (!cleanRunId || !cleanArtifactType) return ''
    return api.getRunReportDownloadUrl(cleanRunId, cleanArtifactType, format)
  }, [cleanRunId, cleanArtifactType, format])
  const rawUrl = useMemo(() => {
    if (!cleanRunId || !cleanArtifactType) return ''
    return api.getRunReportViewUrl(cleanRunId, cleanArtifactType, format)
  }, [cleanRunId, cleanArtifactType, format])

  return (
    <div className="report-viewer-page">
      <div className="page-header">
        <h1>
          <FileText size={30} />
          {label}
        </h1>
        <p className="page-description">
          {description}
        </p>
      </div>

      <div className="run-detail-topbar">
        <div className="run-id-pill">
          <span>{cleanRunId || 'unknown-run'}</span>
        </div>
        <div className="run-topbar-actions">
          <Link className="btn btn-secondary" to={replayHref}>
            Run Recap
          </Link>
          <Link className="btn btn-secondary" to={evidenceHref}>
            Evidence Detail
          </Link>
          {rawUrl && (
            <a className="btn btn-secondary" href={rawUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink size={14} />
              Raw
            </a>
          )}
          {downloadUrl && (
            <a className="btn btn-secondary" href={downloadUrl}>
              <Download size={14} />
              Download
            </a>
          )}
        </div>
      </div>

      {loading && <div className="empty-state">Loading report...</div>}
      {!loading && error && <div className="feed-notice">{error}</div>}
      {!loading && !error && (
        <article className="card report-viewer-card">
          <div className="card-body report-viewer-body">
            {recap && (
              <section className="report-viewer-recap" aria-label="Plain-English run recap">
                <h2>Plain-English Recap</h2>
                <p>{recap.summary}</p>
                <p>{recap.boundary}</p>
                {recap.moments.length > 0 && (
                  <div className="report-viewer-moments">
                    {recap.moments.map((moment) => (
                      <Link
                        key={`${moment.id || moment.title}-${moment.description}`}
                        className="report-viewer-moment"
                        to={moment.id > 0 ? `/runs/${encodeURIComponent(cleanRunId)}?event=${moment.id}` : `/runs/${encodeURIComponent(cleanRunId)}`}
                      >
                        <strong>{moment.title}</strong>
                        {moment.description && <span>{moment.description}</span>}
                      </Link>
                    ))}
                  </div>
                )}
              </section>
            )}
            {format === 'json' ? (
              <pre>{reportText}</pre>
            ) : (
              renderMarkdown(reportText)
            )}
            {showReaderPath && (
              <nav className="report-viewer-reader-path" aria-label="Brief reader path">
                <span>Next views</span>
                <div>
                  <Link to={replayHref} aria-label="Replay: Selected moments">
                    <TimerReset size={14} />
                    <strong>Replay</strong>
                    <small>Selected moments</small>
                  </Link>
                  <Link to={evidenceHref} aria-label="Evidence: Source trail">
                    <FileSearch size={14} />
                    <strong>Evidence</strong>
                    <small>Source trail</small>
                  </Link>
                </div>
              </nav>
            )}
          </div>
        </article>
      )}
    </div>
  )
}
