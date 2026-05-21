import { Suspense } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce, trackShareAction } = vi.hoisted(() => ({
  api: {
    baseUrl: 'https://api.example.test',
    fetch: vi.fn(),
    getRunDetail: vi.fn(),
    getLatestSummary: vi.fn(),
    getEvent: vi.fn(),
    getMessage: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
  trackShareAction: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))
vi.mock('../services/shareAnalytics', () => ({ trackShareAction }))
vi.mock('../components/GlossaryTooltip', () => ({
  default: ({ children }) => <span>{children}</span>,
}))

import RunDetail from './RunDetail'

function renderRunDetail(initialEntry = '/runs/run-1?event=42') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/runs/:runId"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <RunDetail />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetch.mockResolvedValue({
    scope: { last_completed_run_id: 'run-1' },
    agents: { active: 42, dormant: 3, dead: 5 },
  })
  api.getLatestSummary.mockResolvedValue({
    summary: 'A short run summary.',
    source: 'run_summary_fallback',
  })
  api.getRunDetail.mockResolvedValue({
    captured_at: '2026-05-20T05:00:00.000Z',
    run_metadata: {
      condition_name: 'canary_k12',
      run_class: 'special_exploratory',
      ended_at: '2026-05-20T04:32:21.000Z',
    },
    activity: {
      total_events: 100,
      checkpoint_actions: 1,
      deterministic_actions: 2,
      proposal_actions: 3,
      vote_actions: 4,
      forum_actions: 5,
      direct_messages: 6,
      aid_requests: 7,
      trade_actions: 8,
      laws_passed: 9,
      became_dormant: 10,
      agent_revived: 11,
      deaths: 12,
      public_order_events: 13,
      conflict_events: 14,
    },
    llm: { calls: 20, total_tokens: 300, estimated_cost_usd: 0.12 },
    provenance: {
      run_id: 'run-1',
      verification_state: 'verified',
      verification_source: 'run_bundle',
      time_window: {
        start_utc: '2026-05-19T06:30:00.000Z',
        end_utc: '2026-05-20T04:32:21.000Z',
      },
    },
    source_traces: [
      {
        event_id: 42,
        event_type: 'agent_died',
        title: 'Permanent Death',
        description: 'Apex-50 died after running out of food.',
        salience: 95,
        created_at: '2026-05-20T04:00:00.000Z',
        trace_url: '/api/events/42',
      },
    ],
  })
  api.getEvent.mockResolvedValue({
    id: 42,
    event_type: 'agent_died',
    description: 'Apex-50 died after running out of food.',
    created_at: '2026-05-20T04:00:00.000Z',
    metadata: {},
  })
  api.getMessage.mockResolvedValue(null)
})

afterEach(() => {
  cleanup()
})

describe('RunDetail', () => {
  it('links event-scoped evidence back to the matching watch board window', async () => {
    renderRunDetail()

    expect(await screen.findByText(/Run Recap/i)).toBeInTheDocument()
    expect(await screen.findByText(/Focused event #42/i)).toBeInTheDocument()

    expect(screen.getByRole('link', { name: /Back to Watch/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=42',
    )

    const focusedEvent = screen.getByText(/Focused event #42/i).closest('.focused-event-card')
    expect(within(focusedEvent).getByRole('link', { name: /Watch Board/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=42',
    )

    const sourceTrace = screen.getByText(/Permanent Death/i).closest('.run-trace-item')
    expect(within(sourceTrace).getByRole('link', { name: /^Watch$/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=42',
    )
  })
})
