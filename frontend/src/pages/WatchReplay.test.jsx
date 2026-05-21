import { Suspense } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunsArchive: vi.fn(),
    getRunDetail: vi.fn(),
    getRunPlayback: vi.fn(),
    getPlotTurnReplay: vi.fn(),
    getReplayStory: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))

import WatchReplay from './WatchReplay'

function renderWatch(initialEntry = '/watch') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/watch"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <WatchReplay />
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
    title: 'Law Passed',
    description: 'Agents passed a basic needs law.',
    salience: 88,
    created_at: '2026-05-19T08:30:00.000Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRunsArchive.mockResolvedValue({
    items: [{ run_id: 'real-20260519T063000Z' }],
  })
  api.getRunDetail.mockResolvedValue({
    run_id: 'real-20260519T063000Z',
    run_metadata: { run_class: 'special_exploratory' },
    activity: {
      total_events: 15538,
      deaths: 4,
      became_dormant: 7,
      laws_passed: 4,
      proposal_actions: 17,
      aid_requests: 5,
      trade_actions: 3,
      public_order_events: 2,
      conflict_events: 1,
    },
    provenance: {
      time_window: {
        start_utc: '2026-05-19T06:30:00.000Z',
        end_utc: '2026-05-20T04:32:21.000Z',
      },
    },
  })
  api.getRunPlayback.mockResolvedValue({
    items: [
      makeMoment({
        event_id: 1,
        event_type: 'work',
        category: 'notable',
        title: 'Work',
        description: 'Routine work event.',
        salience: 100,
        created_at: '2026-05-19T07:00:00.000Z',
      }),
      makeMoment({
        event_id: 5,
        event_type: 'vote',
        category: 'cooperation',
        title: 'Vote',
        description: 'A routine yes vote should not lead a watch lane.',
        salience: 100,
        created_at: '2026-05-19T07:30:00.000Z',
      }),
      makeMoment(),
    ],
  })
  api.getPlotTurnReplay.mockResolvedValue({
    items: [
      makeMoment(),
      makeMoment({
        event_id: 3,
        event_type: 'request_aid',
        category: 'cooperation',
        title: 'Aid Requested',
        description: 'An agent asked for food support.',
        salience: 80,
        created_at: '2026-05-19T11:30:00.000Z',
      }),
    ],
    buckets: [
      {
        index: 0,
        bucket_start: '2026-05-19T06:30:00.000Z',
        bucket_end: '2026-05-19T09:30:00.000Z',
        event_count: 3,
        dominant_category: 'governance',
      },
      {
        index: 1,
        bucket_start: '2026-05-19T09:30:00.000Z',
        bucket_end: '2026-05-19T12:30:00.000Z',
        event_count: 1,
        dominant_category: 'cooperation',
      },
    ],
  })
  api.getReplayStory.mockResolvedValue({
    items: [
      makeMoment(),
      makeMoment({
        event_id: 4,
        event_type: 'agent_died',
        category: 'crisis',
        title: 'Permanent Death',
        description: 'An agent died after depletion.',
        salience: 95,
        created_at: '2026-05-19T13:30:00.000Z',
      }),
    ],
  })
})

afterEach(() => {
  cleanup()
})

describe('WatchReplay', () => {
  it('defaults to the latest completed run and links density spikes into replay', async () => {
    renderWatch()

    expect(await screen.findByText(/Watch Replay/i)).toBeInTheDocument()
    expect(screen.getAllByText(/real-20260519T063000Z/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Do the new viewer\/story\/evidence changes/i)).toBeInTheDocument()
    expect(screen.getByText(/15,538/i)).toBeInTheDocument()
    expect(screen.getByText(/7 dormancy events/i)).toBeInTheDocument()

    expect(api.getRunDetail).toHaveBeenCalledWith('real-20260519T063000Z', 96, 24, 45)
    expect(api.getPlotTurnReplay).toHaveBeenCalledWith(96, 45, 60, 240, 'real-20260519T063000Z')

    const spike = screen.getByLabelText(/3 event timeline bucket/i)
    expect(spike).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=timeline&event=2',
    )
  })

  it('shows major lanes with replay and evidence links but keeps routine work out', async () => {
    renderWatch()

    const lanes = await screen.findByLabelText(/Major category lanes/i)
    expect(within(lanes).getByText(/Governance/i)).toBeInTheDocument()
    expect(within(lanes).getByText(/Survival/i)).toBeInTheDocument()
    expect(within(lanes).getByText(/Aid \/ Trade/i)).toBeInTheDocument()
    expect(within(lanes).queryByText(/^Work$/i)).not.toBeInTheDocument()
    expect(within(lanes).queryByText(/^Vote$/i)).not.toBeInTheDocument()

    const lawMoment = within(lanes).getByText(/Law Passed/i).closest('.watch-moment')
    expect(within(lawMoment).getByRole('link', { name: /Replay/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=timeline&event=2',
    )
    expect(within(lawMoment).getByRole('link', { name: /Evidence/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z?event=2',
    )
  })
})
