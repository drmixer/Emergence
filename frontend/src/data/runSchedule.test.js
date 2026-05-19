import { describe, expect, it } from 'vitest'
import {
  getLatestCompletedScheduledRun,
  getNextScheduledRun,
  getScheduleEntryForRunId,
  getRunSchedule,
} from './runSchedule'

describe('run schedule', () => {
  it('declares K12 as the next non-claim-bearing public canary', () => {
    const nextRun = getNextScheduledRun()

    expect(nextRun).toMatchObject({
      label: 'K12',
      theme: 'Viewer Comprehension',
      planningState: 'Live',
      track: 'Public Canary',
      runClass: 'special_exploratory',
      status: 'Live',
      runId: 'real-20260519T063000Z',
      claimBoundary: 'Exploratory public canary; non-claim-bearing.',
    })
    expect(nextRun.declaredQuestion).toMatch(/viewer\/story\/evidence changes/i)
  })

  it('lays out a planned slate with distinct themes before the research baseline candidate', () => {
    const slate = getRunSchedule()

    expect(slate.map((run) => run.label)).toEqual([
      'K12',
      'K13',
      'K14',
      'K15',
      'Season 1 Run 1',
      'K11',
    ])
    expect(slate.map((run) => run.theme)).toEqual([
      'Viewer Comprehension',
      'Governance Readability',
      'Aid and Trade Pressure',
      'Public Order',
      'Research Baseline',
      'Public Pipeline',
    ])
    expect(slate.find((run) => run.label === 'Season 1 Run 1')).toMatchObject({
      track: 'Research',
      runClass: 'standard_72h',
      status: 'Candidate',
    })
  })

  it('keeps K11 framed as a completed exploratory pipeline canary', () => {
    const k11 = getLatestCompletedScheduledRun()

    expect(k11).toMatchObject({
      label: 'K11',
      status: 'Completed',
      runId: 'real-20260517T220144Z',
      claimBoundary: 'Exploratory public canary; not finished research.',
    })
    expect(k11.resultNote).toMatch(/viewer experience required/i)
  })

  it('can look up schedule context for archived run cards', () => {
    expect(getScheduleEntryForRunId('real-20260519T063000Z')?.label).toBe('K12')
    expect(getScheduleEntryForRunId('real-20260517T220144Z')?.label).toBe('K11')
    expect(getScheduleEntryForRunId('unknown')).toBeNull()
  })
})
