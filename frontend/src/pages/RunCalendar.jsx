import {
  AlertCircle,
  CalendarDays,
} from 'lucide-react'
import { getLatestCompletedScheduledRun, getNextScheduledRun, getRunSchedule } from '../data/runSchedule'
import GlossaryTooltip from '../components/GlossaryTooltip'
import RunBriefCard from '../components/RunBriefCard'

export default function RunCalendar() {
  const runs = getRunSchedule()
  const nextRun = getNextScheduledRun()
  const latestCompleted = getLatestCompletedScheduledRun()

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
          <span>Next scheduled run</span>
          <strong>{nextRun?.label || 'Not scheduled'}</strong>
          <p>{nextRun?.declaredQuestion || 'No upcoming run has been declared.'}</p>
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
          K11 remains an exploratory public pipeline canary. K12 is the locked next canary; later dates stay tentative until each run condition is ready to launch.
        </p>
      </div>

      <section className="run-calendar-list" aria-label="Scheduled runs">
        {runs.map((run, index) => (
          <RunBriefCard key={run.id} run={run} variant="full" featured={index === 0} actionMode="contextual" />
        ))}
      </section>
    </div>
  )
}
