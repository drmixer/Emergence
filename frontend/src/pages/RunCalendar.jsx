import {
  AlertCircle,
  CalendarDays,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  getCalendarSummaryRuns,
  getRunBriefForArchivedRun,
  getRunBriefForCurrentRun,
  mergeRunScheduleWithRuntime,
} from '../data/runSchedule'
import GlossaryTooltip from '../components/GlossaryTooltip'
import RunBriefCard from '../components/RunBriefCard'
import { api } from '../services/api'
import { trackKpiEventOnce } from '../services/kpiAnalytics'

export default function RunCalendar() {
  const [activeRun, setActiveRun] = useState(null)
  const [completedRuns, setCompletedRuns] = useState([])
  const [runArchiveResolved, setRunArchiveResolved] = useState(false)
  const runtimeScheduleReady = runArchiveResolved || Boolean(activeRun)
  const runs = runtimeScheduleReady ? mergeRunScheduleWithRuntime({ activeRun, completedRuns }) : []
  const { primaryRun, primaryLabel, latestCompleted, nextPlanned } = runtimeScheduleReady
    ? getCalendarSummaryRuns({ activeRun, completedRuns })
    : { primaryRun: null, primaryLabel: 'Resolving run state', latestCompleted: null, nextPlanned: null }

  useEffect(() => {
    let cancelled = false

    async function loadActiveRun() {
      const [overview, archive] = await Promise.all([
        api.getAnalyticsOverview().catch(() => null),
        api.getRunsArchive(12, false).catch(() => null),
      ])
      if (cancelled) return
      const scope = overview?.scope && typeof overview.scope === 'object' ? overview.scope : {}
      const metadata = overview?.run_metadata && typeof overview.run_metadata === 'object' ? overview.run_metadata : {}
      setActiveRun(scope?.simulation_active === true ? getRunBriefForCurrentRun(metadata, scope) : null)
      const archiveItems = Array.isArray(archive?.items) ? archive.items : []
      setCompletedRuns(archiveItems.map(getRunBriefForArchivedRun).filter(Boolean))
      setRunArchiveResolved(true)
    }

    void loadActiveRun()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!runtimeScheduleReady) return
    trackKpiEventOnce('calendar_view', 'run_calendar', {
      surface: 'run_calendar',
      target: 'calendar_page',
      runId: activeRun?.runId || nextPlanned?.runId || nextPlanned?.id || nextPlanned?.label,
      metadata: {
        active_run: activeRun?.label || '',
        next_run: nextPlanned?.label || '',
        latest_completed: latestCompleted?.label || '',
      },
    })
  }, [activeRun, latestCompleted, nextPlanned, runtimeScheduleReady])

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
          <p>{primaryRun?.declaredQuestion || 'Loading live and archived run state before showing the next planned run.'}</p>
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
          {runtimeScheduleReady
            ? 'Calendar status is resolved from live run metadata and archived closeout bundles when available; static schedule entries remain planning context.'
            : 'Resolving archived closeout state before showing scheduled runs.'}
        </p>
      </div>

      <section className="run-calendar-list" aria-label="Scheduled runs">
        {runtimeScheduleReady
          ? runs.map((run, index) => (
            <RunBriefCard key={run.id} run={run} variant="full" featured={index === 0} actionMode="contextual" analyticsSurface="run_calendar" />
          ))
          : (
            <div className="card trust-note-card">
              <div className="card-body trust-note-body">
                <CalendarDays size={16} />
                <p>Loading calendar state from the active run scope and archive.</p>
              </div>
            </div>
          )}
      </section>
    </div>
  )
}
