import { Link } from 'react-router-dom'
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Clock,
  FileSearch,
  HelpCircle,
  RadioTower,
  Target,
  TimerReset,
} from 'lucide-react'
import { getLatestCompletedScheduledRun, getNextScheduledRun, getRunSchedule } from '../data/runSchedule'
import GlossaryTooltip from '../components/GlossaryTooltip'

const STATUS_ICONS = {
  Upcoming: Clock,
  Tentative: CalendarDays,
  Candidate: HelpCircle,
  Live: RadioTower,
  Completed: CheckCircle2,
}

function RunStatusIcon({ status }) {
  const Icon = STATUS_ICONS[status] || CalendarDays
  return <Icon size={18} />
}

function ScheduleLink({ to, children, primary = false }) {
  if (!to) return null
  return (
    <Link to={to} className={`btn ${primary ? 'btn-primary' : 'btn-secondary'}`}>
      {children}
    </Link>
  )
}

function getRunClassTermKey(runClass) {
  const normalized = String(runClass || '').trim().toLowerCase()
  if (normalized === 'standard_72h') return 'standard-72h'
  if (normalized === 'deep_96h') return 'deep-96h'
  if (normalized === 'special_exploratory') return 'special-exploratory'
  return 'run-class'
}

function RunScheduleArticle({ run, featured = false }) {
  const isCompleted = run.status === 'Completed'
  return (
    <article className={`run-calendar-item status-${run.status.toLowerCase()} ${featured ? 'featured' : ''}`}>
      <div className="run-calendar-item-head">
        <div>
          <div className="run-calendar-title-row">
            <span className="run-calendar-status">
              <RunStatusIcon status={run.status} />
              {run.status}
            </span>
            <h2>{run.label}</h2>
          </div>
          <p>
            {run.track} · <GlossaryTooltip termKey={getRunClassTermKey(run.runClass)}>{run.runClass}</GlossaryTooltip> · {run.theme}
          </p>
        </div>
        <div className="run-calendar-time">
          <em>{run.planningState}</em>
          <span>{run.plannedStartLabel}</span>
          <strong>{run.expectedDuration}</strong>
        </div>
      </div>

      <div className="run-calendar-question">
        <Target size={18} />
        <div>
          <span>Declared question</span>
          <strong>{run.declaredQuestion}</strong>
        </div>
      </div>

      <div className="run-calendar-detail-grid">
        <div>
          <span>Theme</span>
          <p>{run.theme}</p>
        </div>
        <div>
          <span>What to watch for</span>
          <p>{run.watchFor}</p>
        </div>
        <div>
          <span>Declared condition</span>
          <p>{run.declaredCondition}</p>
        </div>
        <div>
          <span>What changes from prior run</span>
          <p>{run.changeFromPrior}</p>
        </div>
        <div>
          <span>Useful evidence would be</span>
          <p>{run.usefulEvidence}</p>
        </div>
        <div>
          <span>What this will not prove</span>
          <p>{run.doesNotProve}</p>
        </div>
        <div>
          <span>Claim boundary</span>
          <p>{run.claimBoundary}</p>
        </div>
        {run.resultNote && (
          <div>
            <span>Result note</span>
            <p>{run.resultNote}</p>
          </div>
        )}
      </div>

      <div className="run-calendar-actions">
        {isCompleted ? (
          <>
            <ScheduleLink to={run.links?.recap} primary>
              <TimerReset size={14} />
              Recap
            </ScheduleLink>
            <ScheduleLink to={run.links?.evidence}>
              <FileSearch size={14} />
              Evidence
            </ScheduleLink>
            <ScheduleLink to={run.links?.report}>
              <FileSearch size={14} />
              Story Report
            </ScheduleLink>
          </>
        ) : (
          <>
            <ScheduleLink to={run.links?.live} primary>
              <RadioTower size={14} />
              Current Run
            </ScheduleLink>
            <ScheduleLink to={run.links?.archive}>
              <FileSearch size={14} />
              Archive
            </ScheduleLink>
          </>
        )}
      </div>
    </article>
  )
}

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
          <RunScheduleArticle key={run.id} run={run} featured={index === 0} />
        ))}
      </section>
    </div>
  )
}
