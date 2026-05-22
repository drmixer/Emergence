import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, subscribeToEvents, trackKpiEvent } = vi.hoisted(() => ({
  api: {
    fetch: vi.fn(),
    getAnalyticsOverview: vi.fn(),
    getResources: vi.fn(),
    getRunsArchive: vi.fn(),
    getCrisisStrip: vi.fn(),
    getPlotTurns: vi.fn(),
    getPredictionMarkets: vi.fn(),
    getSocialDynamics: vi.fn(),
    getClassMobility: vi.fn(),
    getRunDetail: vi.fn(),
    getReplayStory: vi.fn(),
    getRunReports: vi.fn(),
  },
  subscribeToEvents: vi.fn(),
  trackKpiEvent: vi.fn(),
}))

vi.mock('../services/api', () => ({ api, subscribeToEvents }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEvent }))

import Dashboard from './Dashboard'

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

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  subscribeToEvents.mockReturnValue(vi.fn())
  api.getAnalyticsOverview.mockResolvedValue({
    scope: {
      simulation_active: false,
      simulation_paused: true,
      last_completed_run_id: 'real-20260522T014909Z',
    },
    run_metadata: {},
    agents: {},
    proposals: {},
    laws: {},
    messages: {},
    resources: { capacity_estimate: {} },
    events: {},
    critical: {},
  })
  api.getResources.mockResolvedValue({
    totals: {},
    common_pool: {},
  })
  api.getRunsArchive.mockResolvedValue({
    items: [archivedK13()],
  })
  api.fetch.mockResolvedValue([])
  api.getCrisisStrip.mockResolvedValue({ items: [] })
  api.getPlotTurns.mockResolvedValue({ items: [] })
  api.getPredictionMarkets.mockResolvedValue([])
  api.getSocialDynamics.mockResolvedValue({ series: [], deltas_vs_prev_day: {} })
  api.getClassMobility.mockResolvedValue({ tiers: [], mobility: {}, inequality: {} })
  api.getRunDetail.mockResolvedValue({
    activity: {
      total_events: 5424,
      laws_passed: 1,
      aid_requests: 0,
      trade_actions: 2,
      public_order_events: 2,
    },
  })
  api.getReplayStory.mockResolvedValue({ items: [] })
  api.getRunReports.mockResolvedValue({ items: [] })
})

afterEach(() => {
  cleanup()
})

describe('Dashboard', () => {
  it('uses archived closeout state before choosing the next idle-dashboard run', async () => {
    renderDashboard()

    expect(await screen.findByText(/Latest completed run: real-20260522T014909Z/i)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'K14' })).toBeInTheDocument()
    const idleConsole = screen.getByLabelText(/Idle run console/i)
    expect(idleConsole).toBeInTheDocument()
    expect(within(idleConsole).getByText(/^Latest closeout$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Next declared run/i)).toBeInTheDocument()

    const nextRunCard = screen.getByRole('heading', { name: 'K14' }).closest('article')
    expect(within(nextRunCard).getByText(/Next tentative run/i)).toBeInTheDocument()
    expect(within(nextRunCard).getAllByText(/Tentative/i).length).toBeGreaterThan(0)
    expect(screen.queryByRole('heading', { name: 'K13' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Can proposal discussion, voting, and passed laws stay readable/i)).not.toBeInTheDocument()
  })
})
