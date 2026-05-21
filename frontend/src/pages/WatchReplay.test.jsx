import { Suspense } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunsArchive: vi.fn(),
    getRunWatch: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))

import WatchReplay from './WatchReplay'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{location.pathname}{location.search}</div>
}

function renderWatch(initialEntry = '/watch') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
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
  api.getRunWatch.mockResolvedValue({
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
})

afterEach(() => {
  cleanup()
})

describe('WatchReplay', () => {
  it('uses the archive latest completed run for the default watch route', async () => {
    api.getRunsArchive.mockResolvedValue({
      items: [{ run_id: 'real-20990101T000000Z' }],
    })

    renderWatch()

    expect((await screen.findAllByText(/real-20990101T000000Z/i)).length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(api.getRunWatch).toHaveBeenCalledTimes(1)
    })
    expect(api.getRunWatch).toHaveBeenCalledWith('real-20990101T000000Z', 60, 240)
    expect(api.getRunWatch).not.toHaveBeenCalledWith('real-20260519T063000Z', 60, 240)
    expect(screen.getByText(/Completed run map/i)).toBeInTheDocument()
    expect(screen.queryByText(/Do the new viewer\/story\/evidence changes/i)).not.toBeInTheDocument()
  })

  it('defaults to the latest completed run and lets density spikes select a replay window', async () => {
    renderWatch()

    expect(await screen.findByText(/Watch Replay/i)).toBeInTheDocument()
    expect(screen.getAllByText(/real-20260519T063000Z/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Do the new viewer\/story\/evidence changes/i)).toBeInTheDocument()
    expect(await screen.findByText(/15,538/i)).toBeInTheDocument()
    expect(screen.getByText(/7 dormancy events/i)).toBeInTheDocument()

    expect(api.getRunWatch).toHaveBeenCalledWith('real-20260519T063000Z', 60, 240)

    const spike = screen.getAllByRole('button', { name: /Select 1 event timeline bucket/i })[0]
    fireEvent.click(spike)

    expect(spike).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&event=2')
    const selectedWindow = screen.getByLabelText(/Selected window/i)
    expect(within(selectedWindow).getByText(/Dominant lane/i)).toBeInTheDocument()
    expect(within(selectedWindow).getAllByText(/Governance/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getAllByText(/Law Passed/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getByRole('link', { name: /Replay/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=timeline&event=2',
    )
    expect(within(selectedWindow).getByRole('link', { name: /Evidence/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z?event=2',
    )
    expect(screen.getByRole('link', { name: /Brief/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/reports/viewer_brief?format=markdown',
    )

    expect(screen.getByText(/Moments inside the selected window/i)).toBeInTheDocument()
    expect(screen.getAllByText(/0 in selected window \/ 1 total/i).length).toBeGreaterThan(0)

    fireEvent.click(within(selectedWindow).getByRole('button', { name: /Clear selection/i }))
    expect(screen.queryByLabelText(/Selected window/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z')
  })

  it('shows major lanes with replay and evidence links but keeps routine work out', async () => {
    renderWatch()

    const lanes = await screen.findByLabelText(/Major category lanes/i)
    expect(within(lanes).getByText(/Governance/i)).toBeInTheDocument()
    expect(within(lanes).getByText(/Survival/i)).toBeInTheDocument()
    expect(within(lanes).getByText(/Aid \/ Trade/i)).toBeInTheDocument()
    expect(within(lanes).queryByText(/^Work$/i)).not.toBeInTheDocument()
    expect(within(lanes).queryByText(/^Vote$/i)).not.toBeInTheDocument()
    expect(within(lanes).queryByText(/^Direct Message$/i)).not.toBeInTheDocument()

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

  it('uses linked visible moments for density counts and disables true-empty buckets', async () => {
    api.getRunWatch.mockResolvedValue({
      activity: {},
      provenance: {
        time_window: {
          start_utc: '2026-05-19T06:30:00.000Z',
          end_utc: '2026-05-19T12:30:00.000Z',
        },
      },
      items: [
        makeMoment(),
        makeMoment({
          event_id: 9,
          event_type: 'direct_message',
          category: 'cooperation',
          title: 'Direct Message',
          description: 'A generic private message should not become an Aid / Trade watch spike.',
          salience: 39,
          created_at: '2026-05-19T10:30:00.000Z',
        }),
      ],
      buckets: [
        {
          index: 0,
          bucket_start: '2026-05-19T06:30:00.000Z',
          bucket_end: '2026-05-19T09:30:00.000Z',
          event_count: 0,
          dominant_category: null,
        },
        {
          index: 1,
          bucket_start: '2026-05-19T09:30:00.000Z',
          bucket_end: '2026-05-19T12:30:00.000Z',
          event_count: 12,
          dominant_category: 'cooperation',
        },
      ],
    })

    renderWatch()

    const linkedBucket = await screen.findByRole('button', { name: /Select 1 event timeline bucket/i })
    const emptyBuckets = screen.getAllByRole('button', { name: /Select 0 event timeline bucket/i })
    const densityBars = linkedBucket.closest('.watch-density-bars')

    expect(linkedBucket).not.toBeDisabled()
    expect(densityBars).toHaveStyle({ gridTemplateColumns: 'repeat(2, minmax(10px, 1fr))' })
    expect(emptyBuckets[0]).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Select 12 event timeline bucket/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/^Direct Message$/i)).not.toBeInTheDocument()
  })

  it('selects a watch window from an event deep link', async () => {
    renderWatch('/watch?run=real-20260519T063000Z&event=3')

    const selectedWindow = await screen.findByLabelText(/Selected window/i)
    expect(within(selectedWindow).getAllByText(/Aid \/ Trade/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getAllByText(/Aid Requested/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getByRole('link', { name: /Replay/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=timeline&event=3',
    )

    const lanes = screen.getByLabelText(/Major category lanes/i)
    const aidLane = within(lanes).getByText(/Aid \/ Trade/i).closest('.watch-lane')
    expect(within(aidLane).getByText(/1 in selected window \/ 1 total/i)).toBeInTheDocument()
  })

  it('renders selected lane moments even when they fall outside the default lane preview', async () => {
    api.getRunWatch.mockResolvedValue({
      activity: {},
      provenance: {
        time_window: {
          start_utc: '2026-05-19T06:30:00.000Z',
          end_utc: '2026-05-19T12:30:00.000Z',
        },
      },
      items: [
        makeMoment({
          event_id: 30,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Early Aid One',
          description: 'Earlier aid signal.',
          salience: 78,
          created_at: '2026-05-19T07:10:00.000Z',
        }),
        makeMoment({
          event_id: 31,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Early Aid Two',
          description: 'Earlier aid signal.',
          salience: 77,
          created_at: '2026-05-19T07:20:00.000Z',
        }),
        makeMoment({
          event_id: 32,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Early Aid Three',
          description: 'Earlier aid signal.',
          salience: 76,
          created_at: '2026-05-19T07:30:00.000Z',
        }),
        makeMoment({
          event_id: 33,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Early Aid Four',
          description: 'Earlier aid signal.',
          salience: 75,
          created_at: '2026-05-19T07:40:00.000Z',
        }),
        makeMoment({
          event_id: 3,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Late Aid Requested',
          description: 'An agent asked for food support after the early lane preview.',
          salience: 80,
          created_at: '2026-05-19T11:30:00.000Z',
        }),
      ],
      buckets: [
        {
          index: 0,
          bucket_start: '2026-05-19T06:30:00.000Z',
          bucket_end: '2026-05-19T09:30:00.000Z',
          event_count: 4,
          dominant_category: 'cooperation',
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

    renderWatch()

    const buckets = await screen.findAllByRole('button', { name: /Select 1 event timeline bucket/i })
    fireEvent.click(buckets[buckets.length - 1])

    const lanes = screen.getByLabelText(/Major category lanes/i)
    const aidLane = within(lanes).getByText(/Aid \/ Trade/i).closest('.watch-lane')
    expect(within(aidLane).getByText(/1 in selected window \/ 5 total/i)).toBeInTheDocument()
    expect(within(aidLane).getByText(/Late Aid Requested/i)).toBeInTheDocument()
    expect(within(aidLane).queryByText(/No linked moments in the selected window/i)).not.toBeInTheDocument()
  })
})
