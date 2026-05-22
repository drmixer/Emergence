import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getAnalyticsOverview: vi.fn(),
    getRunsArchive: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))

import RunCalendar from './RunCalendar'

function createDeferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

function archivedK13() {
  return {
    run_id: 'real-20260522T014909Z',
    summary: {
      run_id: 'real-20260522T014909Z',
      condition_name: 'real_governance_readability_canary_k13',
      run_class: 'special_exploratory',
      run_started_at: '2026-05-22T01:49:10Z',
      run_ended_at: '2026-05-22T09:20:38Z',
      duration_hours: 7.52,
      status_label: 'observational',
    },
    run_metadata: {
      run_id: 'real-20260522T014909Z',
      condition_name: 'real_governance_readability_canary_k13',
      run_class: 'special_exploratory',
      started_at: '2026-05-22T01:49:10Z',
      ended_at: '2026-05-22T09:20:38Z',
    },
    artifacts: {
      approachable_report: { available: true },
      run_summary: { available: true },
    },
  }
}

function renderCalendar() {
  return render(
    <MemoryRouter>
      <RunCalendar />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getAnalyticsOverview.mockResolvedValue({
    scope: {
      simulation_active: false,
      simulation_paused: true,
      last_completed_run_id: 'real-20260522T014909Z',
    },
    run_metadata: {},
  })
  api.getRunsArchive.mockResolvedValue({
    items: [archivedK13()],
  })
})

afterEach(() => {
  cleanup()
})

describe('RunCalendar', () => {
  it('waits for archive state before showing static schedule cards', async () => {
    const archive = createDeferred()
    api.getRunsArchive.mockReturnValue(archive.promise)

    renderCalendar()

    expect(screen.getByText(/Resolving run state/i)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'K13' })).not.toBeInTheDocument()

    archive.resolve({ items: [archivedK13()] })

    expect(await screen.findByRole('heading', { name: 'K13' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'K14' })).toBeInTheDocument()

    const k13Card = screen.getByRole('heading', { name: 'K13' }).closest('article')
    expect(within(k13Card).getAllByText(/Completed/i).length).toBeGreaterThan(0)
    expect(within(k13Card).getByText(/Stopped after 7.5h/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(trackKpiEventOnce).toHaveBeenCalledWith(
        'calendar_view',
        'run_calendar',
        expect.objectContaining({
          runId: 'k14-aid-trade-pressure-canary',
        }),
      )
    })
  })
})
