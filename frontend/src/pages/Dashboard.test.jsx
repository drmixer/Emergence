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
    expect(within(idleConsole).getByText(/Console idle/i)).toBeInTheDocument()
    expect(within(idleConsole).queryByText(/logged events/i)).not.toBeInTheDocument()
    expect(within(idleConsole).queryByLabelText(/Latest completed run snapshot/i)).not.toBeInTheDocument()
    expect(within(idleConsole).getByRole('link', { name: /^Watch$/i })).toHaveAttribute(
      'href',
      '/watch?run=real-20260522T014909Z',
    )
    expect(within(idleConsole).getByRole('link', { name: /^Replay$/i })).toHaveAttribute(
      'href',
      '/runs/real-20260522T014909Z/replay?mode=story60',
    )
    expect(within(idleConsole).getByRole('link', { name: /^Evidence$/i })).toHaveAttribute(
      'href',
      '/runs/real-20260522T014909Z',
    )
    expect(screen.getByLabelText(/Next declared run/i)).toBeInTheDocument()

    const nextRunCard = screen.getByRole('heading', { name: 'K14' }).closest('article')
    expect(within(nextRunCard).getByText(/Next tentative run/i)).toBeInTheDocument()
    expect(within(nextRunCard).getAllByText(/Tentative/i).length).toBeGreaterThan(0)
    expect(screen.queryByRole('heading', { name: 'K13' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Can proposal discussion, voting, and passed laws stay readable/i)).not.toBeInTheDocument()
    expect(api.getRunDetail).not.toHaveBeenCalled()
    expect(api.getReplayStory).not.toHaveBeenCalled()
    expect(api.getRunReports).not.toHaveBeenCalled()
  })

  it('prioritizes live run state as an operations matrix', async () => {
    api.getAnalyticsOverview.mockResolvedValue({
      scope: {
        simulation_active: true,
        simulation_paused: false,
        active_run_id: 'real-live-run',
      },
      run_metadata: {
        run_id: 'real-live-run',
        run_class: 'special_exploratory',
        condition_name: 'live_readability_canary',
      },
      agents: {
        active: 12,
        dormant: 3,
        dead: 1,
      },
      proposals: {
        active: 2,
      },
      laws: {
        total: 4,
      },
      messages: {
        total: 40,
      },
      resources: {
        capacity_estimate: {
          food: 2000,
          energy: 1200,
          materials: 900,
        },
      },
      events: {},
      critical: {},
      day_number: 2,
    })
    api.getResources.mockResolvedValue({
      totals: {
        food: 1000,
        energy: 400,
        materials: 300,
      },
      common_pool: {
        food: 250,
        energy: 50,
        materials: 25,
      },
    })
    api.fetch.mockImplementation((endpoint) => {
      if (String(endpoint).includes('/api/proposals')) {
        return Promise.resolve([
          {
            id: 'proposal-1',
            title: 'Reserve share vote',
            author: { agent_number: 7, codename: 'Marble', tier: 2 },
            votes_for: 5,
            votes_against: 2,
            status: 'active',
          },
        ])
      }
      if (String(endpoint).includes('/api/analytics/leaderboards/activity')) {
        return Promise.resolve([
          {
            agent_id: 'agent-7',
            agent_number: 7,
            codename: 'Marble',
            tier: 2,
            action_count: 18,
          },
        ])
      }
      return Promise.resolve([])
    })
    api.getCrisisStrip.mockResolvedValue({ items: [] })
    api.getPlotTurns.mockResolvedValue({
      items: [{ title: 'Resource refusal cluster', created_at: '2026-05-22T08:00:00Z' }],
    })
    api.getPredictionMarkets.mockResolvedValue([{ title: 'Will a law pass?', id: 'market-1' }])
    api.getSocialDynamics.mockResolvedValue({
      series: [{ public_order_events: 6 }],
      deltas_vs_prev_day: {
        public_order_events_delta: 2,
        conflict_events_delta: 1,
        alliance_signals_delta: 0,
      },
    })
    api.getClassMobility.mockResolvedValue({
      mobility: {
        upward_signals: 1,
        downward_signals: 2,
        signal_flux_rate: 0.25,
      },
      inequality: {
        gini: 0.42,
      },
    })

    const { container } = renderDashboard()

    const liveConsole = await screen.findByLabelText(/Live operations console/i)
    expect(within(liveConsole).getByText(/Live state ledger/i)).toBeInTheDocument()
    const vitalSigns = within(liveConsole).getByLabelText(/Live run vital signs/i)
    expect(within(vitalSigns).getByText(/^Active$/i)).toBeInTheDocument()
    expect(within(vitalSigns).getByText('12')).toBeInTheDocument()
    expect(within(vitalSigns).getByText(/^Dormant$/i)).toBeInTheDocument()
    expect(within(vitalSigns).getByText('3')).toBeInTheDocument()
    expect(within(liveConsole).getByText(/Resource pressure/i)).toBeInTheDocument()
    expect(within(liveConsole).getByText('1,250 / 2,000')).toBeInTheDocument()
    expect(within(liveConsole).getByText(/Open proposals/i)).toBeInTheDocument()
    expect(await screen.findByText(/Reserve share vote/i)).toBeInTheDocument()
    const proposalsPanel = within(liveConsole).getByLabelText(/Open proposals/i)
    expect(within(proposalsPanel).getByRole('link', { name: /^Governance$/i })).toHaveAttribute(
      'href',
      '/governance?tab=proposals',
    )

    const secondaryTelemetry = screen.getByLabelText(/Secondary live telemetry/i)
    expect(within(secondaryTelemetry).getByText(/Activity leaders/i)).toBeInTheDocument()
    expect(within(secondaryTelemetry).getByText(/Agent #07/i)).toBeInTheDocument()
    expect(within(secondaryTelemetry).getByText(/Run observation signals/i)).toBeInTheDocument()
    expect(within(secondaryTelemetry).getByText(/Resource refusal cluster/i)).toBeInTheDocument()

    expect(container.querySelector('.stats-grid')).toBeNull()
    expect(container.querySelector('.resource-grid')).toBeNull()
    expect(container.querySelector('.content-grid')).toBeNull()
  })
})
