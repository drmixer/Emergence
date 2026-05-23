import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { FileSearch, TimerReset } from 'lucide-react'
import { getStoryReplayHref, getTimelineReplayHref } from '../utils/bestMoments'

export default function HighlightsCompatibility() {
  const [searchParams] = useSearchParams()
  const runId = String(searchParams.get('run') || '').trim()
  const tab = String(searchParams.get('tab') || '').trim()
  const mode = String(searchParams.get('mode') || '').trim()
  const eventId = String(searchParams.get('event') || '').trim()

  if (runId) {
    const target = mode === 'timeline' || tab === 'timeline'
      ? getTimelineReplayHref(runId)
      : getStoryReplayHref(runId)
    const separator = target.includes('?') ? '&' : '?'
    const eventQuery = eventId ? `${separator}event=${encodeURIComponent(eventId)}` : ''
    return <Navigate to={`${target}${eventQuery}`} replace />
  }

  if (tab === 'predictions') {
    return <Navigate to="/predictions" replace />
  }

  return (
    <div className="highlights-compat-page">
      <div className="page-header">
        <h1>
          <TimerReset size={32} />
          Highlights moved into Run Replay
        </h1>
        <p className="page-description">
          Run Console owns live and idle operations state. Archive and Run Replay own completed-run review.
        </p>
      </div>

      <div className="card legacy-route-card">
        <div className="card-body legacy-route-body">
          <FileSearch size={22} />
          <div>
            <strong>This route is kept for old links.</strong>
            <p>
              Pick Run Console for live state, or Archive to open a completed run replay with evidence and reports.
            </p>
          </div>
          <div className="legacy-route-actions">
            <Link to="/dashboard" className="btn btn-primary">Run Console</Link>
            <Link to="/archive" className="btn btn-secondary">Archive</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
