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
import { trackKpiEvent } from '../services/kpiAnalytics'

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

function getReportLinkLabel(run) {
  const reportHref = String(run?.links?.report || '')
  return reportHref.includes('/viewer_brief') ? 'Emergence Brief' : 'Story Report'
}

function trackRunPathClick(run, surface, target, href) {
  trackKpiEvent('run_path_click', {
    runId: run?.runId || run?.id || run?.label,
    surface,
    target,
    metadata: {
      href,
      label: run?.label || '',
      status: run?.status || '',
      track: run?.track || '',
      run_class: run?.runClass || '',
    },
  })
}

function ScheduleLink({ to, children, primary = false, run = null, surface = 'run_brief_card', target = 'run_link' }) {
  if (!to) return null
  return (
    <Link
      to={to}
      className={`btn ${primary ? 'btn-primary' : 'btn-secondary'}`}
      onClick={() => trackRunPathClick(run, surface, target, to)}
    >
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

function RunBriefActions({ run, mode, analyticsSurface }) {
  if (mode === 'none') return null

  if (mode === 'calendar') {
    return (
      <div className="run-brief-actions">
        <ScheduleLink to="/calendar" run={run} surface={analyticsSurface} target="calendar" primary>
          <CalendarDays size={14} />
          Run Calendar
        </ScheduleLink>
      </div>
    )
  }

  if (run.status === 'Completed') {
    const reportLabel = getReportLinkLabel(run)
    return (
      <div className="run-brief-actions">
        <ScheduleLink to={run.links?.recap} run={run} surface={analyticsSurface} target="recap" primary>
          <TimerReset size={14} />
          Recap
        </ScheduleLink>
        <ScheduleLink to={run.links?.evidence} run={run} surface={analyticsSurface} target="evidence">
          <FileSearch size={14} />
          Evidence
        </ScheduleLink>
        <ScheduleLink to={run.links?.report} run={run} surface={analyticsSurface} target="story_report">
          <FileSearch size={14} />
          {reportLabel}
        </ScheduleLink>
      </div>
    )
  }

  return (
    <div className="run-brief-actions">
      <ScheduleLink to={run.links?.live} run={run} surface={analyticsSurface} target="current_run" primary={run.status === 'Live'}>
        <RadioTower size={14} />
        Current Run
      </ScheduleLink>
      <ScheduleLink to="/calendar" run={run} surface={analyticsSurface} target="calendar" primary={run.status !== 'Live'}>
        <CalendarDays size={14} />
        Run Calendar
      </ScheduleLink>
      <ScheduleLink to={run.links?.archive} run={run} surface={analyticsSurface} target="archive">
        <FileSearch size={14} />
        Archive
      </ScheduleLink>
    </div>
  )
}

function RunViewerPath({ run, analyticsSurface }) {
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
              <Link
                to={step.href}
                onClick={() => trackRunPathClick(run, analyticsSurface, `viewer_path:${step.label}`, step.href)}
              >
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
  analyticsSurface = 'run_brief_card',
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

      <RunViewerPath run={run} analyticsSurface={analyticsSurface} />

      <RunBriefActions run={run} mode={actionMode} analyticsSurface={analyticsSurface} />
    </article>
  )
}
