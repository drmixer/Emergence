import { Suspense } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: {
    getAnalyticsOverview: vi.fn(),
    getBestMoments: vi.fn(),
    getPlotTurns: vi.fn(),
    getLatestSummary: vi.fn(),
    getRunPlayback: vi.fn(),
    getReplayStory: vi.fn(),
    fetch: vi.fn(),
  },
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/shareAnalytics', () => ({
  trackShareAction: vi.fn(),
}))
vi.mock('../services/kpiAnalytics', () => ({
  trackKpiEventOnce: vi.fn(),
}))
vi.mock('../components/Recap', () => ({
  default: ({ runId = '', title = '', scopeLabel = '' }) => (
    <div data-testid="recap">{`${title}|${runId || 'none'}|${scopeLabel}`}</div>
  ),
}))
vi.mock('../components/QuoteCard', () => ({
  default: () => <div data-testid="quote-card">quote-card</div>,
}))

import Highlights from './Highlights'

function renderHighlights(initialEntry = '/highlights') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/highlights"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <Highlights />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>
  )
}

function makePlaybackItem(overrides = {}) {
  return {
    event_id: 11,
    event_type: 'proposal_resolved',
    title: 'Shared Reserve Passes',
    description: 'The reserve proposal passes and becomes the main visible shift.',
    salience: 87,
    category: 'governance',
    created_at: '2026-04-08T03:18:20.000Z',
    metadata: { runtime: { run_id: 'run-archive-1' } },
    run_id: 'run-archive-1',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getAnalyticsOverview.mockResolvedValue({
    scope: {
      active_run_id: null,
      last_completed_run_id: 'last-run-1',
    },
  })
  api.getBestMoments.mockResolvedValue({ items: [] })
  api.getPlotTurns.mockResolvedValue({ items: [] })
  api.getLatestSummary.mockResolvedValue(null)
  api.getRunPlayback.mockResolvedValue({
    items: [],
    time_window: null,
    contract: null,
    total_count: 0,
  })
  api.getReplayStory.mockResolvedValue({ items: [], chapters: [] })
  api.fetch.mockResolvedValue({})
})

afterEach(() => {
  cleanup()
})

describe('Highlights', () => {
  it('renders active-run framing when a live run exists', async () => {
    api.getAnalyticsOverview.mockResolvedValue({
      scope: {
        active_run_id: 'active-run-1',
        last_completed_run_id: 'last-run-1',
      },
    })

    renderHighlights('/highlights')

    expect(await screen.findByText(/Live story desk for the current run/i)).toBeInTheDocument()
    expect(await screen.findByTestId('recap')).toHaveTextContent('RUN SUMMARY SO FAR|active-run-1|Active run')
  })

  it('falls back to the latest completed run when no run is active', async () => {
    renderHighlights('/highlights')

    expect(await screen.findByText(/Recap, key moments, replay, and summary from the latest available run/i)).toBeInTheDocument()
    expect(await screen.findByTestId('recap')).toHaveTextContent('RUN SUMMARY SO FAR|last-run-1|Latest available run')
  })

  it('shows the predictions redirect notice on legacy prediction links', async () => {
    renderHighlights('/highlights?tab=predictions')

    expect(await screen.findByText(/Predictions now live on their own page/i)).toBeInTheDocument()
    expect(await screen.findByTestId('recap')).toBeInTheDocument()
  })

  it('renders archived replay story and canonical timeline states', async () => {
    api.getRunPlayback.mockResolvedValue({
      items: [
        makePlaybackItem(),
        makePlaybackItem({
          event_id: 12,
          title: 'Emergency work response',
          description: 'Agents redirect work to stabilize reserves.',
          event_type: 'work',
          category: 'notable',
          salience: 61,
          created_at: '2026-04-08T03:18:30.000Z',
        }),
      ],
      time_window: {
        start_utc: '2026-04-08T03:18:14.000Z',
        end_utc: '2026-04-08T03:20:22.000Z',
      },
      contract: {
        ordering: 'created_at_asc_id_asc',
      },
      total_count: 2,
    })
    api.getReplayStory.mockResolvedValue({
      items: [
        {
          ...makePlaybackItem(),
          chapter: 'Trigger',
          why_this_matters: 'Governance changed the rule set.',
          deltas: [],
        },
      ],
      chapters: [{ label: 'Trigger', count: 1, lead_event_id: 11 }],
    })

    renderHighlights('/highlights?run=run-archive-1&tab=replay')

    expect(await screen.findByText(/Viewing archived run/i)).toBeInTheDocument()
    expect(await screen.findByText(/Curated story/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Replay Timeline/i }))

    expect(await screen.findByText(/Canonical playback/i)).toBeInTheDocument()
    expect(screen.getByText(/Ordered by created_at then id/i)).toBeInTheDocument()
  })

  it('shows an explicit not-found state for invalid archived runs', async () => {
    const notFoundError = new Error('Run not found')
    notFoundError.status = 404
    api.fetch.mockRejectedValue(notFoundError)

    renderHighlights('/highlights?run=missing-run&tab=replay')

    expect(await screen.findByText(/Requested archived run missing-run could not be found/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Choose a completed run from the archive/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /the runs archive/i })).toBeInTheDocument()
    await waitFor(() => {
      expect(api.getRunPlayback).not.toHaveBeenCalled()
    })
  })
})
