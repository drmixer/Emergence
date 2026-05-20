import { describe, expect, it } from 'vitest'
import {
  getCalendarSummaryRuns,
  getLatestCompletedScheduledRun,
  getNextScheduledRun,
  getScheduleEntryForRunId,
  getRunSchedule,
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
})
