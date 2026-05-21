import { describe, expect, it } from 'vitest'
import {
  buildRunBriefFromMetadata,
  getCalendarSummaryRuns,
  getLatestCompletedScheduledRun,
  getRunBriefForCurrentRun,
  getNextScheduledRun,
  getScheduleEntryForRunId,
  getRunSchedule,
  mergeRunScheduleWithActiveRun,
} from './runSchedule'

describe('run schedule', () => {
  it('declares K13 as the next non-claim-bearing public canary', () => {
    const nextRun = getNextScheduledRun()

    expect(nextRun).toMatchObject({
      label: 'K13',
      theme: 'Governance Readability',
      planningState: 'Upcoming',
      track: 'Public Canary',
      runClass: 'special_exploratory',
      status: 'Upcoming',
      declaredCondition: 'real_governance_readability_canary_k13',
      claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    })
    expect(nextRun.declaredQuestion).toMatch(/proposal discussion/i)
  })

  it('lays out a planned slate with distinct themes before the research baseline candidate', () => {
    const slate = getRunSchedule()

    expect(slate.map((run) => run.label)).toEqual([
      'K13',
      'K14',
      'K15',
      'Season 1 Run 1',
      'K12',
      'K11',
    ])
    expect(slate.map((run) => run.theme)).toEqual([
      'Governance Readability',
      'Aid and Trade Pressure',
      'Public Order',
      'Research Baseline',
      'Viewer Comprehension',
      'Public Pipeline',
    ])
    expect(slate.find((run) => run.label === 'Season 1 Run 1')).toMatchObject({
      track: 'Research',
      runClass: 'standard_72h',
      status: 'Candidate',
    })
  })

  it('keeps K12 framed as the latest completed exploratory viewer canary', () => {
    const k12 = getLatestCompletedScheduledRun()

    expect(k12).toMatchObject({
      label: 'K12',
      status: 'Completed',
      runId: 'real-20260519T063000Z',
      claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    })
    expect(k12.resultNote).toMatch(/Stopped early/i)
  })

  it('derives calendar summary labels from run state', () => {
    const summary = getCalendarSummaryRuns()

    expect(summary.primaryLabel).toBe('Next scheduled run')
    expect(summary.primaryRun?.label).toBe('K13')
    expect(summary.latestCompleted?.label).toBe('K12')
  })

  it('can look up schedule context for archived run cards', () => {
    expect(getScheduleEntryForRunId('real-20260519T063000Z')?.label).toBe('K12')
    expect(getScheduleEntryForRunId('real-20260517T220144Z')?.label).toBe('K11')
    expect(getScheduleEntryForRunId('unknown')).toBeNull()
  })

  it('builds a live run card from backend metadata and declared question', () => {
    const run = buildRunBriefFromMetadata({
      run_id: 'real-20260522T063000Z',
      condition_name: 'real_governance_readability_canary_k13',
      run_class: 'special_exploratory',
      started_at: '2026-05-22T06:30:00Z',
      run_declaration: {
        declared_question: 'Can governance discussion stay readable?',
        watch_for: 'Watch proposal replies for distinct positions.',
        claim_boundary: 'Exploratory public canary; non-claim-bearing.',
      },
    })

    expect(run).toMatchObject({
      label: 'K13',
      status: 'Live',
      runId: 'real-20260522T063000Z',
      track: 'Public Canary',
      runClass: 'special_exploratory',
      declaredQuestion: 'Can governance discussion stay readable?',
      watchFor: 'Watch proposal replies for distinct positions.',
      claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    })
    expect(run.links.evidence).toBe('/runs/real-20260522T063000Z')
    expect(run.links.report).toBe('/runs/real-20260522T063000Z/reports/viewer_brief?format=markdown')
  })

  it('promotes the matching scheduled card when the current run metadata names K13', () => {
    const activeRun = getRunBriefForCurrentRun(
      {
        run_id: 'real-20260522T063000Z',
        condition_name: 'real_governance_readability_canary_k13',
        run_class: 'special_exploratory',
        started_at: '2026-05-22T06:30:00Z',
      },
      { simulation_active: true, active_run_id: 'real-20260522T063000Z' }
    )

    expect(activeRun).toMatchObject({
      label: 'K13',
      status: 'Live',
      planningState: 'Live',
      runId: 'real-20260522T063000Z',
      declaredQuestion: 'Can proposal discussion, voting, and passed laws stay readable without collapsing into agreement pile-on noise?',
    })
    expect(activeRun.links.report).toBe('/runs/real-20260522T063000Z/reports/viewer_brief?format=markdown')

    const summary = getCalendarSummaryRuns({ activeRun })
    expect(summary.primaryLabel).toBe('Current live run')
    expect(summary.primaryRun?.label).toBe('K13')
    expect(mergeRunScheduleWithActiveRun(activeRun).filter((run) => run.label === 'K13')).toHaveLength(1)
  })
})
