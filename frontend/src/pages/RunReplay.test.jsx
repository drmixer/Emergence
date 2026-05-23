import { Suspense } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEvent, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunDetail: vi.fn(),
    getRunPlayback: vi.fn(),
    getReplayStory: vi.fn(),
    getRunReports: vi.fn(),
    getRunReportDownloadUrl: vi.fn(),
    getRunReportViewUrl: vi.fn(),
  },
  trackKpiEvent: vi.fn(),
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEvent, trackKpiEventOnce }))

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

    const narrativeBeats = screen.getByLabelText(/Replay narrative beats/i)
    expect(within(narrativeBeats).getByText(/Opening Signal/i)).toBeInTheDocument()
    expect(within(narrativeBeats).getByText(/Governance Response/i)).toBeInTheDocument()
    expect(within(narrativeBeats).getByText(/Pressure Point/i)).toBeInTheDocument()
    expect(within(narrativeBeats).queryByText(/^Work$/i)).not.toBeInTheDocument()

    const selectedMoment = screen.getByText('Selected moment', { selector: 'span' }).closest('.run-replay-featured')
    expect(within(selectedMoment).getByRole('link', { name: /Watch Map/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=10',
    )
  })

  it('links event-scoped replay back to the matching watch board window', async () => {
    renderRunReplay('/runs/run-1/replay?mode=timeline&event=12')

    expect(await screen.findByText(/What Happened/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Back to Watch Map/i })).toHaveAttribute(
      'href',
      '/watch?run=run-1&event=12',
    )
  })

  it('does not promote routine playback into replay threads when curated story is empty', async () => {
    api.getReplayStory.mockResolvedValueOnce({ items: [], chapters: [] })
    api.getRunPlayback.mockResolvedValueOnce({
      items: [
        makeMoment({
          event_id: 99,
          event_type: 'work',
          category: 'notable',
          title: 'Work',
          description: 'Apex-50 farmed 1.40 food in 1h',
          salience: 100,
        }),
        makeMoment({
          event_id: 100,
          event_type: 'idle',
          category: 'notable',
          title: 'Idle',
          description: 'Apex-50 waited.',
          salience: 100,
        }),
      ],
      count: 2,
      total_count: 2,
    })

    renderRunReplay()

    expect(await screen.findByText(/No curated replay moments are available yet/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Replay narrative beats/i)).not.toBeInTheDocument()

    const storyThreads = screen.getByText(/Story Threads/i).closest('.card')
    expect(within(storyThreads).queryByText(/^Work$/i)).not.toBeInTheDocument()
    expect(within(storyThreads).queryByText(/^Idle$/i)).not.toBeInTheDocument()
  })

  it('summarizes evidence without turning Replay into the raw evidence browser', async () => {
    api.getRunDetail.mockResolvedValueOnce({
      run_id: 'run-1',
      captured_at: '2026-05-18T05:00:00.000Z',
      run_metadata: { condition_name: 'canary_k11', run_class: 'special_exploratory' },
      activity: { total_events: 4, deaths: 0, became_dormant: 0 },
      llm: { calls: 2 },
      provenance: { verification_state: 'verified' },
      source_traces: [
        {
          event_id: 1,
          event_type: 'work',
          title: 'Work',
          description: 'Apex-50 farmed 1.40 food in 1h',
          salience: 39,
          created_at: '2026-05-18T04:00:00.000Z',
        },
        {
          event_id: 2,
          event_type: 'create_proposal',
          title: 'Create Proposal',
          description: 'Prime-24 created proposal: Active Agent Basic Needs Law',
          salience: 64,
          created_at: '2026-05-18T04:05:00.000Z',
        },
      ],
    })

    renderRunReplay('/runs/run-1/replay?mode=timeline')

    fireEvent.click(await screen.findByRole('button', { name: /Evidence Handoff/i }))

    expect(await screen.findByRole('heading', { name: /Evidence Handoff/i })).toBeInTheDocument()
    expect(screen.queryByText(/^Work$/i)).not.toBeInTheDocument()
    expect(screen.getByText(/routine or low-signal trace/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open Evidence Detail/i })).toHaveAttribute('href', '/runs/run-1')
    expect(screen.getByText(/^All$/i)).toBeInTheDocument()
    expect(screen.getByText(/^Governance$/i)).toBeInTheDocument()
    expect(screen.getByText(/Proposals, voting, laws/i)).toBeInTheDocument()
  })

  it('summarizes evidence categories while handing raw source review to Evidence Detail', async () => {
    api.getRunDetail.mockResolvedValueOnce({
      run_id: 'run-1',
      captured_at: '2026-05-18T05:00:00.000Z',
      run_metadata: { condition_name: 'canary_k11', run_class: 'special_exploratory' },
      activity: { total_events: 4, deaths: 0, became_dormant: 0 },
      llm: { calls: 2 },
      provenance: { verification_state: 'verified' },
      source_traces: [
        {
          event_id: 21,
          event_type: 'request_aid',
          title: 'Request Aid',
          description: 'Beacon-2 requested 2 food from the common pool.',
          salience: 58,
          created_at: '2026-05-18T04:00:00.000Z',
        },
        {
          event_id: 22,
          event_type: 'request_aid',
          title: 'Request Aid',
          description: 'Cipher-3 requested 1 energy from an ally.',
          salience: 82,
          created_at: '2026-05-18T04:05:00.000Z',
        },
        {
          event_id: 23,
          event_type: 'law_passed',
          title: 'Law Passed',
          description: 'Agents passed an aid floor law.',
          salience: 77,
          created_at: '2026-05-18T04:10:00.000Z',
        },
      ],
    })

    renderRunReplay('/runs/run-1/replay?mode=timeline')

    fireEvent.click(await screen.findByRole('button', { name: /Evidence Handoff/i }))

    expect(await screen.findByRole('heading', { name: /Evidence Handoff/i })).toBeInTheDocument()
    expect(screen.getByText(/3 available source traces/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open Evidence Detail/i })).toHaveAttribute('href', '/runs/run-1')
    expect(screen.getByText(/^Aid \/ Trade$/i)).toBeInTheDocument()
    expect(screen.getByText(/^Governance$/i)).toBeInTheDocument()
    expect(screen.getByText(/Aid requests, refusals, rescues/i)).toBeInTheDocument()
  })

  it('shows the viewer brief as a named report artifact', async () => {
    api.getRunReports.mockResolvedValueOnce({
      items: [
        {
          artifact_type: 'viewer_brief',
          artifact_format: 'markdown',
          updated_at: '2026-05-21T00:00:00.000Z',
        },
        {
          artifact_type: 'approachable_report',
          artifact_format: 'markdown',
          updated_at: '2026-05-21T00:00:00.000Z',
        },
      ],
    })

    renderRunReplay('/runs/run-1/replay?tab=reports')

    expect(await screen.findByText(/Report Artifacts/i)).toBeInTheDocument()
    expect(screen.getByText('Emergence Brief')).toBeInTheDocument()
    expect(screen.getByText('Approachable Story')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Open/i })[0]).toHaveAttribute(
      'href',
      '/runs/run-1/reports/viewer_brief?format=markdown',
    )
  })
})
