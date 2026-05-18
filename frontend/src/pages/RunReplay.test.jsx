import { Suspense } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: {
    getRunDetail: vi.fn(),
    getRunPlayback: vi.fn(),
    getReplayStory: vi.fn(),
    getRunReports: vi.fn(),
    getRunReportDownloadUrl: vi.fn(),
    getRunReportViewUrl: vi.fn(),
  },
}))

vi.mock('../services/api', () => ({ api }))

import RunReplay from './RunReplay'

function renderRunReplay(initialEntry = '/runs/run-1/replay?mode=story60') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/runs/:runId/replay"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <RunReplay />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>
  )
}

function makeMoment(overrides = {}) {
  return {
    event_id: 10,
    event_type: 'agent_died',
    category: 'crisis',
    title: 'Permanent Death',
    description: 'Apex-50 died after running out of food.',
    salience: 95,
    created_at: '2026-05-18T04:00:00.000Z',
    why_this_matters: 'A permanent loss narrowed the set of possible outcomes.',
    deltas: [{ label: 'Deaths', value: '+1', tone: 'down' }],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRunDetail.mockResolvedValue({
    run_id: 'run-1',
    captured_at: '2026-05-18T05:00:00.000Z',
    run_metadata: {
      condition_name: 'real_scarcity_executable_governance_20260517_canary_k11_high_floor_pressure_v1',
      run_class: 'special_exploratory',
    },
    activity: {
      total_events: 11204,
      deaths: 3,
      became_dormant: 8,
      agent_revived: 1,
      laws_passed: 2,
      proposal_actions: 11,
      vote_actions: 27,
      aid_requests: 6,
      aid_refusals: 2,
      trade_actions: 4,
      trade_amounts: { food: 3, energy: 2, materials: 0 },
      public_order_events: 5,
      conflict_events: 2,
    },
    llm: { calls: 200, total_tokens: 1000, estimated_cost_usd: 0.42 },
    provenance: {
      verification_state: 'verified',
      time_window: {
        start_utc: '2026-05-17T22:00:00.000Z',
        end_utc: '2026-05-18T05:00:00.000Z',
      },
    },
    source_traces: [],
  })
  api.getRunPlayback.mockResolvedValue({
    items: [
      makeMoment({
        event_id: 99,
        event_type: 'work',
        category: 'notable',
        title: 'Work',
        description: 'Apex-50 farmed 1.40 food in 1h',
        salience: 80,
      }),
    ],
    count: 1,
    total_count: 1,
  })
  api.getReplayStory.mockResolvedValue({
    items: [
      makeMoment(),
      makeMoment({
        event_id: 11,
        event_type: 'proposal_resolved',
        category: 'governance',
        title: 'Proposal Passed',
        description: 'Agents passed an emergency floor proposal.',
        why_this_matters: 'Governance changed the rule set.',
        deltas: [{ label: 'Proposal', value: 'Passed', tone: 'up' }],
      }),
      makeMoment({
        event_id: 12,
        event_type: 'request_aid',
        category: 'cooperation',
        title: 'Aid Requested',
        description: 'A dormant-risk agent asked for food support.',
        why_this_matters: 'Resource coordination became visible.',
        deltas: [],
      }),
    ],
    chapters: [],
  })
  api.getRunReports.mockResolvedValue({ items: [] })
  api.getRunReportDownloadUrl.mockReturnValue('/download')
  api.getRunReportViewUrl.mockReturnValue('/view')
})

afterEach(() => {
  cleanup()
})

describe('RunReplay', () => {
  it('renders a readable recap and hides routine work from story threads', async () => {
    renderRunReplay()

    expect(await screen.findByText(/What Happened/i)).toBeInTheDocument()
    expect(screen.getByText(/11,204 scoped events/i)).toBeInTheDocument()
    expect(screen.getByText(/3 deaths \/ 8 dormant/i)).toBeInTheDocument()
    expect(screen.getAllByText(/2 laws passed/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Resource coordination included 6 aid requests/i)).toBeInTheDocument()

    const storyThreads = screen.getByText(/Story Threads/i).closest('.card')
    expect(within(storyThreads).getByText(/Survival Pressure/i)).toBeInTheDocument()
    expect(within(storyThreads).getByText(/Governance Decisions/i)).toBeInTheDocument()
    expect(within(storyThreads).getByText(/Aid & Trade/i)).toBeInTheDocument()
    expect(within(storyThreads).queryByText(/^Work$/i)).not.toBeInTheDocument()
  })
})
