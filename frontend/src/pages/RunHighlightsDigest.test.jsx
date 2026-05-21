import { Suspense } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunDetail: vi.fn(),
    getReplayStory: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))

import RunHighlightsDigest from './RunHighlightsDigest'

function renderDigest(initialEntry = '/runs/run-1/highlights') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/runs/:runId/highlights"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <RunHighlightsDigest />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function makeMoment(overrides = {}) {
  return {
    event_id: 2,
    event_type: 'law_passed',
    category: 'governance',
    title: 'Food floor law passed',
    description: 'Agents passed a basic-needs law after scarcity pressure.',
    salience: 92,
    created_at: '2026-05-19T08:30:00.000Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRunDetail.mockResolvedValue({
    run_id: 'run-1',
    run_metadata: {
      run_class: 'special_exploratory',
    },
    activity: {
      total_events: 1200,
      deaths: 4,
      became_dormant: 7,
      agent_revived: 1,
      laws_passed: 3,
      proposal_actions: 11,
      vote_actions: 28,
      aid_requests: 5,
      trade_actions: 2,
      aid_refusals: 1,
      public_order_events: 6,
      conflict_events: 2,
    },
    source_traces: [
      makeMoment({
        event_id: 1,
        event_type: 'work',
        category: 'notable',
        title: 'Routine work',
        salience: 100,
        created_at: '2026-05-19T07:00:00.000Z',
      }),
      makeMoment(),
      makeMoment({
        event_id: 3,
        event_type: 'request_aid',
        category: 'cooperation',
        title: 'Aid requested',
        description: 'An agent asked the group for food support.',
        salience: 80,
        created_at: '2026-05-19T11:30:00.000Z',
      }),
      makeMoment({
        event_id: 4,
        event_type: 'public_accusation',
        category: 'conflict',
        title: 'Public accusation',
        description: 'A public-order dispute became visible.',
        salience: 74,
        created_at: '2026-05-19T12:45:00.000Z',
      }),
    ],
  })
  api.getReplayStory.mockResolvedValue({
    items: [
      makeMoment(),
      makeMoment({
        event_id: 5,
        event_type: 'agent_died',
        category: 'crisis',
        title: 'Permanent death',
        description: 'An agent died after depletion.',
        salience: 96,
        created_at: '2026-05-19T13:30:00.000Z',
      }),
    ],
  })
})

afterEach(() => {
  cleanup()
})

describe('RunHighlightsDigest', () => {
  it('summarizes completed-run highlights with links into Watch, Replay, and Evidence', async () => {
    renderDigest()

    expect(await screen.findByText(/Run Highlights/i)).toBeInTheDocument()
    expect(api.getRunDetail).toHaveBeenCalledWith('run-1', 96, 30, 45)
    expect(api.getReplayStory).toHaveBeenCalledWith(96, 45, 10, 'run-1')

    const topbar = screen.getByText('run-1').closest('.run-detail-topbar')
    expect(within(topbar).getByRole('link', { name: /Watch/i })).toHaveAttribute('href', '/watch?run=run-1')
    expect(within(topbar).getByRole('link', { name: /Replay/i })).toHaveAttribute(
      'href',
      '/runs/run-1/replay?mode=story60',
    )
    expect(within(topbar).getByRole('link', { name: /Evidence/i })).toHaveAttribute('href', '/runs/run-1')

    const highlights = screen.getByLabelText(/Highlights by category/i)
    expect(within(highlights).getByText(/Deaths \/ Dormancy/i)).toBeInTheDocument()
    expect(within(highlights).getByText('4 / 7')).toBeInTheDocument()
    expect(within(highlights).getByText(/Laws \/ Proposals/i)).toBeInTheDocument()
    expect(within(highlights).getByText('3 / 11')).toBeInTheDocument()
    expect(within(highlights).getByText(/Aid \/ Trade/i)).toBeInTheDocument()
    expect(within(highlights).getByText('5 / 2')).toBeInTheDocument()
    expect(within(highlights).getByText(/Public Order/i)).toBeInTheDocument()
    expect(within(highlights).getByText(/6 signals/i)).toBeInTheDocument()

    const lawPanel = within(highlights).getByText(/Food floor law passed/i).closest('.run-highlight-moment')
    expect(within(lawPanel).getByRole('link', { name: /Watch/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=2',
    )
    expect(within(lawPanel).getByRole('link', { name: /Replay/i })).toHaveAttribute(
      'href',
      '/runs/run-1/replay?mode=timeline&event=2',
    )
    expect(within(lawPanel).getByRole('link', { name: /Evidence/i })).toHaveAttribute(
      'href',
      '/runs/run-1?event=2',
    )

    expect(screen.getByText(/Notable decisions/i)).toBeInTheDocument()
    expect(screen.getByText(/Top watch moments/i)).toBeInTheDocument()
    expect(screen.queryByText(/^Routine work$/i)).not.toBeInTheDocument()
    expect(trackKpiEventOnce).toHaveBeenCalledWith(
      'run_highlights_digest_view',
      'run_highlights_digest:run-1',
      expect.objectContaining({
        runId: 'run-1',
        surface: 'run_highlights_digest',
      }),
    )
  })
})
