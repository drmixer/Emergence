import {
  AlertCircle,
  CalendarDays,
} from 'lucide-react'
import { useEffect } from 'react'
import { getCalendarSummaryRuns, getNextScheduledRun, getRunSchedule } from '../data/runSchedule'
import GlossaryTooltip from '../components/GlossaryTooltip'
import RunBriefCard from '../components/RunBriefCard'
import { trackKpiEventOnce } from '../services/kpiAnalytics'

export default function RunCalendar() {
  const runs = getRunSchedule()
  const nextRun = getNextScheduledRun()
  const { primaryRun, primaryLabel, latestCompleted } = getCalendarSummaryRuns()

  useEffect(() => {
    trackKpiEventOnce('calendar_view', 'run_calendar', {
      surface: 'run_calendar',
      target: 'calendar_page',
      runId: nextRun?.runId || nextRun?.id || nextRun?.label,
      metadata: {
        next_run: nextRun?.label || '',
        latest_completed: latestCompleted?.label || '',
      },
    })
  }, [latestCompleted, nextRun])

  return (
    <div className="run-calendar-page">
      <div className="page-header">
        <h1>
          <CalendarDays size={30} />
          Run Calendar
        </h1>
        <p className="page-description">
          Public <GlossaryTooltip termKey="public-canary">canaries</GlossaryTooltip> and <GlossaryTooltip termKey="research-run">research runs</GlossaryTooltip> with declared questions, watch points, and evidence paths.
        </p>
      </div>

      <section className="run-calendar-summary" aria-label="Run schedule summary">
        <div>
          <span>{primaryLabel}</span>
          <strong>{primaryRun?.label || 'Not scheduled'}</strong>
          <p>{primaryRun?.declaredQuestion || 'No upcoming run has been declared.'}</p>
        </div>
        <div>
          <span>Latest completed canary</span>
          <strong>{latestCompleted?.label || 'None'}</strong>
          <p>{latestCompleted?.claimBoundary || 'No completed public canary is scheduled.'}</p>
        </div>
        <div>
          <span>Run discipline</span>
          <strong>Season arc, not episodes</strong>
          <p>Runs are planned as declared variations so repetition becomes comparison instead of another isolated spectacle.</p>
        </div>
      </section>

      <div className="run-calendar-note">
        <AlertCircle size={16} />
        <p>
          K12 is closed as an exploratory viewer-comprehension canary, with the outage treated as a viewer-experience confound. K13 is the next tentative governance-readability canary.
        </p>
      </div>

      <section className="run-calendar-list" aria-label="Scheduled runs">
        {runs.map((run, index) => (
          <RunBriefCard key={run.id} run={run} variant="full" featured={index === 0} actionMode="contextual" analyticsSurface="run_calendar" />
        ))}
      </section>
    </div>
  )
}
