import { Link } from 'react-router-dom'
import {
  CalendarDays,
  CheckCircle2,
  Clock,
  FileSearch,
  HelpCircle,
  RadioTower,
  Target,
  TimerReset,
} from 'lucide-react'
import GlossaryTooltip from './GlossaryTooltip'
import { getRunClassTermKey } from '../data/runSchedule'

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

function getCompactRows(run) {
  return [
    ['What to watch for', run.watchFor],
    ['Claim boundary', run.claimBoundary],
    ['Useful evidence', run.usefulEvidence],
  ].filter(([, value]) => String(value || '').trim())
}

function getFullRows(run) {
  return [
    ['Theme', run.theme],
    ['What to watch for', run.watchFor],
    ['Declared condition', run.declaredCondition],
    ['What changes from prior run', run.changeFromPrior],
    ['Useful evidence would be', run.usefulEvidence],
    ['What this will not prove', run.doesNotProve],
    ['Claim boundary', run.claimBoundary],
    ['Result note', run.resultNote],
  ].filter(([, value]) => String(value || '').trim())
}

function RunBriefActions({ run, mode }) {
  if (mode === 'none') return null

  if (mode === 'calendar') {
    return (
      <div className="run-brief-actions">
        <ScheduleLink to="/calendar" primary>
          <CalendarDays size={14} />
          Run Calendar
        </ScheduleLink>
      </div>
    )
  }

  if (run.status === 'Completed') {
    return (
      <div className="run-brief-actions">
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
      </div>
    )
  }

  return (
    <div className="run-brief-actions">
      <ScheduleLink to={run.links?.live} primary={run.status === 'Live'}>
        <RadioTower size={14} />
        Current Run
      </ScheduleLink>
      <ScheduleLink to="/calendar" primary={run.status !== 'Live'}>
        <CalendarDays size={14} />
        Run Calendar
      </ScheduleLink>
      <ScheduleLink to={run.links?.archive}>
        <FileSearch size={14} />
        Archive
      </ScheduleLink>
    </div>
  )
}

function RunViewerPath({ run }) {
  const steps = Array.isArray(run.viewerPath) ? run.viewerPath.filter((step) => String(step?.label || '').trim()) : []
  if (steps.length === 0) return null

  return (
    <div className="run-brief-viewer-path" aria-label={`${run.label} viewer path`}>
      <span>How to follow this run</span>
      <div className="run-brief-viewer-steps">
        {steps.map((step) => (
          <div key={`${step.label}-${step.href || ''}`} className="run-brief-viewer-step">
            <strong>{step.label}</strong>
            <p>{step.detail}</p>
            {step.href && (
              <Link to={step.href}>
                {step.linkLabel || 'Open'}
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function RunBriefCard({
  run,
  variant = 'compact',
  heading = '',
  featured = false,
  actionMode = 'contextual',
}) {
  if (!run) return null

  const full = variant === 'full'
  const rows = full ? getFullRows(run) : getCompactRows(run)

  return (
    <article className={`run-brief-card run-brief-${variant} status-${String(run.status || 'scheduled').toLowerCase()} ${featured ? 'featured' : ''}`}>
      <div className="run-brief-head">
        <div>
          <div className="run-brief-title-row">
            <span className="run-brief-status">
              <RunStatusIcon status={run.status} />
              {run.status}
            </span>
            {heading && <span className="run-brief-heading">{heading}</span>}
            <h2>{run.label}</h2>
          </div>
          <p>
            {run.track} · <GlossaryTooltip termKey={getRunClassTermKey(run.runClass)}>{run.runClass}</GlossaryTooltip> · {run.theme}
          </p>
        </div>
        <div className="run-brief-time">
          <em>{run.planningState}</em>
          <span>{run.plannedStartLabel}</span>
          <strong>{run.expectedDuration}</strong>
        </div>
      </div>

      <div className="run-brief-question">
        <Target size={18} />
        <div>
          <span>Declared question</span>
          <strong>{run.declaredQuestion}</strong>
        </div>
      </div>

      <div className={`run-brief-detail-grid ${full ? 'full' : 'compact'}`}>
        {rows.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <p>{value}</p>
          </div>
        ))}
      </div>

      <RunViewerPath run={run} />

      <RunBriefActions run={run} mode={actionMode} />
    </article>
  )
}
