import { Suspense } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEvent, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getAnalyticsOverview: vi.fn(),
    getRunsArchive: vi.fn(),
    getRunWatch: vi.fn(),
  },
  trackKpiEvent: vi.fn(),
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEvent, trackKpiEventOnce }))

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
        <Route path="/runs/:runId/replay" element={<div>Replay route</div>} />
        <Route path="/runs/:runId" element={<div>Evidence route</div>} />
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
  api.getAnalyticsOverview.mockResolvedValue({
    scope: {
      simulation_active: false,
      simulation_paused: true,
      last_completed_run_id: 'real-20260519T063000Z',
    },
  })
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
  it('uses the active unpaused run for the default watch route', async () => {
    api.getAnalyticsOverview.mockResolvedValue({
      scope: {
        simulation_active: true,
        simulation_paused: false,
        active_run_id: 'real-20260522T014909Z',
        last_completed_run_id: 'real-20260519T063000Z',
      },
      run_metadata: {
        run_id: 'real-20260522T014909Z',
        run_class: 'special_exploratory',
        condition_name: 'real_governance_readability_canary_k13',
        run_declaration: {
          declared_question: 'Can proposal discussion stay readable?',
          claim_boundary: 'Exploratory public canary; non-claim-bearing.',
        },
      },
    })
    api.getRunsArchive.mockResolvedValue({
      items: [{ run_id: 'real-20260519T063000Z' }],
    })
    api.getRunWatch.mockResolvedValue({
      run_id: 'real-20260522T014909Z',
      run_metadata: {
        run_id: 'real-20260522T014909Z',
        run_class: 'special_exploratory',
        condition_name: 'real_governance_readability_canary_k13',
        run_declaration: {
          declared_question: 'Can proposal discussion stay readable?',
          claim_boundary: 'Exploratory public canary; non-claim-bearing.',
        },
      },
      activity: {},
      provenance: {
        time_window: {
          start_utc: '2026-05-22T01:49:10.000Z',
          end_utc: '2026-05-22T02:10:00.000Z',
        },
      },
      items: [
        makeMoment({
          event_id: 40,
          event_type: 'proposal_created',
          category: 'governance',
          title: 'Live Proposal',
          description: 'Agents opened a governance proposal.',
          created_at: '2026-05-22T02:00:00.000Z',
        }),
      ],
      buckets: [
        {
          index: 0,
          bucket_start: '2026-05-22T01:49:10.000Z',
          bucket_end: '2026-05-22T02:49:10.000Z',
          event_count: 1,
          dominant_category: 'governance',
        },
      ],
    })

    renderWatch()

    expect(await screen.findByText(/Live now/i)).toBeInTheDocument()
    expect(screen.getAllByText(/real-20260522T014909Z/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Live window through now/i)).toBeInTheDocument()
    expect(screen.getByText(/Live Proposal/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(api.getRunWatch).toHaveBeenCalledWith('real-20260522T014909Z', 60, 240)
    })
    expect(api.getRunWatch).not.toHaveBeenCalledWith('real-20260519T063000Z', 60, 240)
  })

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
    expect(await screen.findByText(/Do the new viewer\/story\/evidence changes/i)).toBeInTheDocument()
    expect(await screen.findByText(/15,538/i)).toBeInTheDocument()
    expect(screen.getByText(/7 dormancy events/i)).toBeInTheDocument()

    expect(api.getRunWatch).toHaveBeenCalledWith('real-20260519T063000Z', 60, 240)

    const spike = screen.getAllByRole('button', { name: /Select 1 event timeline bucket/i })[0]
    fireEvent.click(spike)

    expect(spike).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&event=2')
    const selectedWindow = screen.getByLabelText(/Selected window/i)
    expect(within(selectedWindow).getByText(/Dominant lane/i)).toBeInTheDocument()
    expect(within(selectedWindow).getByText(/Spike 1 of 2/i)).toBeInTheDocument()
    expect(within(selectedWindow).getAllByText(/Governance/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getAllByText(/Law Passed/i).length).toBeGreaterThan(0)
    expect(within(selectedWindow).getByRole('button', { name: /Previous spike/i })).toBeDisabled()
    expect(within(selectedWindow).getByRole('button', { name: /Next spike/i })).not.toBeDisabled()
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

    fireEvent.click(within(selectedWindow).getByRole('button', { name: /Next spike/i }))
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&event=3')
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_spike_step', expect.objectContaining({
      runId: 'real-20260519T063000Z',
      eventId: 3,
      surface: 'watch_replay',
      target: 'next_spike',
      metadata: expect.objectContaining({
        lane_filter: 'all',
        from_spike_index: 1,
        to_spike_index: 2,
      }),
    }))
    const nextWindow = screen.getByLabelText(/Selected window/i)
    expect(within(nextWindow).getByText(/Spike 2 of 2/i)).toBeInTheDocument()
    expect(within(nextWindow).getAllByText(/Aid Requested/i).length).toBeGreaterThan(0)

    fireEvent.click(within(nextWindow).getByRole('button', { name: /Previous spike/i }))
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&event=2')
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_spike_step', expect.objectContaining({
      target: 'previous_spike',
      eventId: 2,
      metadata: expect.objectContaining({
        from_spike_index: 2,
        to_spike_index: 1,
      }),
    }))

    fireEvent.click(within(screen.getByLabelText(/Selected window/i)).getByRole('button', { name: /Clear selection/i }))
    expect(screen.queryByLabelText(/Selected window/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z')
  })

  it('jumps directly to the largest density spike', async () => {
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
          event_id: 20,
          event_type: 'law_passed',
          category: 'governance',
          title: 'Early Law',
          salience: 82,
          created_at: '2026-05-19T07:00:00.000Z',
        }),
        makeMoment({
          event_id: 21,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Largest Spike Aid',
          salience: 91,
          created_at: '2026-05-19T10:00:00.000Z',
        }),
        makeMoment({
          event_id: 22,
          event_type: 'agent_died',
          category: 'crisis',
          title: 'Largest Spike Death',
          salience: 90,
          created_at: '2026-05-19T10:10:00.000Z',
        }),
      ],
      buckets: [
        {
          index: 0,
          bucket_start: '2026-05-19T06:30:00.000Z',
          bucket_end: '2026-05-19T09:30:00.000Z',
          event_count: 1,
          dominant_category: 'governance',
        },
        {
          index: 1,
          bucket_start: '2026-05-19T09:30:00.000Z',
          bucket_end: '2026-05-19T12:30:00.000Z',
          event_count: 2,
          dominant_category: 'cooperation',
        },
      ],
    })

    renderWatch()

    const jumpButton = await screen.findByRole('button', { name: /Jump to largest spike/i })
    await waitFor(() => {
      expect(jumpButton).not.toBeDisabled()
    })
    fireEvent.click(jumpButton)

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&event=21')
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_spike_jump', expect.objectContaining({
      runId: 'real-20260519T063000Z',
      eventId: 21,
      surface: 'watch_replay',
      target: 'largest_spike',
      metadata: expect.objectContaining({
        lane_filter: 'all',
        bucket_index: 1,
        bucket_moment_count: 2,
      }),
    }))
    const selectedWindow = screen.getByLabelText(/Selected window/i)
    expect(within(selectedWindow).getByText(/Spike 2 of 2/i)).toBeInTheDocument()
    expect(within(selectedWindow).getByText(/Linked moments/i)).toBeInTheDocument()
    expect(within(selectedWindow).getAllByText(/Largest Spike Aid/i).length).toBeGreaterThan(0)
  })

  it('opens the largest spike from an archive focus link without recording a jump click', async () => {
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
          event_id: 20,
          event_type: 'law_passed',
          category: 'governance',
          title: 'Early Law',
          salience: 82,
          created_at: '2026-05-19T07:00:00.000Z',
        }),
        makeMoment({
          event_id: 21,
          event_type: 'request_aid',
          category: 'cooperation',
          title: 'Archive Entry Aid',
          salience: 91,
          created_at: '2026-05-19T10:00:00.000Z',
        }),
        makeMoment({
          event_id: 22,
          event_type: 'agent_died',
          category: 'crisis',
          title: 'Archive Entry Death',
          salience: 90,
          created_at: '2026-05-19T10:10:00.000Z',
        }),
      ],
      buckets: [
        {
          index: 0,
          bucket_start: '2026-05-19T06:30:00.000Z',
          bucket_end: '2026-05-19T09:30:00.000Z',
          event_count: 1,
          dominant_category: 'governance',
        },
        {
          index: 1,
          bucket_start: '2026-05-19T09:30:00.000Z',
          bucket_end: '2026-05-19T12:30:00.000Z',
          event_count: 2,
          dominant_category: 'cooperation',
        },
      ],
    })

    renderWatch('/watch?run=real-20260519T063000Z&focus=largest')

    const selectedWindow = await screen.findByLabelText(/Selected window/i)
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&focus=largest')
    expect(within(selectedWindow).getByText(/Spike 2 of 2/i)).toBeInTheDocument()
    expect(within(selectedWindow).getAllByText(/Archive Entry Aid/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Jump to largest spike/i })).toBeDisabled()
    expect(trackKpiEvent).not.toHaveBeenCalledWith('watch_spike_jump', expect.anything())
  })

  it('focuses the density timeline by lane without hiding lane context', async () => {
    renderWatch()

    await screen.findByText(/Law Passed/i)
    const laneFocus = screen.getByRole('group', { name: /Timeline lane focus/i })
    const aidFocus = within(laneFocus).getByText(/Aid \/ Trade/i).closest('button')
    fireEvent.click(aidFocus)

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&lane=aid_trade')
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_lane_focus', expect.objectContaining({
      runId: 'real-20260519T063000Z',
      surface: 'watch_replay',
      target: 'aid_trade',
      metadata: expect.objectContaining({
        previous_lane_filter: 'all',
        focused_lane: 'aid_trade',
        focused_moments: 1,
      }),
    }))
    expect(aidFocus).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/2 buckets · 1 Aid \/ Trade moments/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Select 0 Aid \/ Trade event timeline bucket/i })).toBeDisabled()

    const jumpButton = screen.getByRole('button', { name: /Jump to largest spike with 1 linked moments/i })
    fireEvent.click(jumpButton)

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z&lane=aid_trade&event=3')
    const selectedWindow = screen.getByLabelText(/Selected window/i)
    expect(within(selectedWindow).getByText(/Spike 1 of 1 · Aid \/ Trade/i)).toBeInTheDocument()
    expect(within(selectedWindow).getAllByText(/Aid Requested/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Timeline focused on Aid \/ Trade; lane rows remain visible for context/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Governance/i).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /^All lanes$/i }))
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/watch?run=real-20260519T063000Z')
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_lane_focus', expect.objectContaining({
      target: 'all_lanes',
      metadata: expect.objectContaining({
        previous_lane_filter: 'aid_trade',
        focused_lane: 'all',
      }),
    }))
  })

  it('shows major lanes with replay and evidence links but keeps routine work out', async () => {
    renderWatch()

    await screen.findByText(/Law Passed/i)
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

  it('tracks Replay and Evidence clicks from selected window moments', async () => {
    renderWatch('/watch?run=real-20260519T063000Z&event=3')

    const selectedWindow = await screen.findByLabelText(/Selected window/i)
    const replayLink = within(selectedWindow).getByRole('link', { name: /Replay/i })

    fireEvent.click(replayLink)
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_selected_moment_click', expect.objectContaining({
      runId: 'real-20260519T063000Z',
      eventId: 3,
      surface: 'watch_replay',
      target: 'replay',
      metadata: expect.objectContaining({
        lane_filter: 'all',
        moment_lane: 'aid_trade',
        moment_title: 'Aid Requested',
      }),
    }))

    cleanup()
    renderWatch('/watch?run=real-20260519T063000Z&event=3')
    const rerenderedWindow = await screen.findByLabelText(/Selected window/i)
    const rerenderedEvidenceLink = within(rerenderedWindow).getByRole('link', { name: /Evidence/i })

    fireEvent.click(rerenderedEvidenceLink)
    expect(trackKpiEvent).toHaveBeenCalledWith('watch_selected_moment_click', expect.objectContaining({
      eventId: 3,
      target: 'evidence',
      metadata: expect.objectContaining({
        moment_lane: 'aid_trade',
      }),
    }))
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
