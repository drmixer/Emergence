import { Suspense } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunDetail: vi.fn(),
    getReplayStory: vi.fn(),
    getRunReportText: vi.fn(),
    getRunReportDownloadUrl: vi.fn(),
    getRunReportViewUrl: vi.fn(),
  },
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEventOnce }))

import ReportViewer from './ReportViewer'

function renderReportViewer(initialEntry = '/runs/real-1/reports/approachable_report?format=markdown') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/runs/:runId/reports/:artifactType"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <ReportViewer />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRunReportText.mockResolvedValue([
    '# Run real-1 Story Report',
    '',
    '## What Happened',
    '',
    'This run produced a readable story paragraph.',
    '',
    'Evidence:',
    '- [Run Evidence](/runs/real-1)',
  ].join('\n'))
  api.getRunDetail.mockResolvedValue({
    run_metadata: {
      condition_name: 'real_scarcity_executable_governance_20260517_canary_k11_high_floor_pressure_v1',
      run_class: 'special_exploratory',
    },
    activity: {
      total_events: 11204,
      deaths: 3,
      became_dormant: 8,
      laws_passed: 2,
      proposal_actions: 9,
      vote_actions: 415,
      aid_requests: 6,
      trade_actions: 4,
      public_order_events: 5,
    },
  })
  api.getReplayStory.mockResolvedValue({
    items: [
      {
        event_id: 42,
        title: 'Emergency aid floor passed',
        description: 'Agents changed the rules after resource pressure became visible.',
      },
    ],
  })
  api.getRunReportDownloadUrl.mockReturnValue('/download')
  api.getRunReportViewUrl.mockReturnValue('/raw')
})

afterEach(() => {
  cleanup()
})

describe('ReportViewer', () => {
  it('renders the approachable report inside the app with recap and evidence actions', async () => {
    renderReportViewer()

    expect(await screen.findByRole('heading', { name: 'Approachable Story' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Plain-English Recap' })).toBeInTheDocument()
    expect(screen.getByText(/exploratory public canary/i)).toBeInTheDocument()
    expect(screen.getByText(/3 deaths and 8 dormancy events/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Emergency aid floor passed/i })).toHaveAttribute('href', '/runs/real-1?event=42')
    expect(screen.getByRole('heading', { name: 'What Happened' })).toBeInTheDocument()
    expect(screen.getByText(/readable story paragraph/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Run Recap/i })).toHaveAttribute('href', '/runs/real-1/replay?tab=overview')
    expect(screen.getByRole('link', { name: /Evidence Detail/i })).toHaveAttribute('href', '/runs/real-1')
    expect(api.getRunReportText).toHaveBeenCalledWith('real-1', 'approachable_report', 'markdown')
  })

  it('labels the news-style viewer brief without loading the extra story recap', async () => {
    renderReportViewer('/runs/real-1/reports/viewer_brief?format=markdown')

    expect(await screen.findByRole('heading', { name: 'Emergence Brief' })).toBeInTheDocument()
    expect(screen.getByText(/News-style recap/i)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Plain-English Recap' })).not.toBeInTheDocument()
    expect(api.getRunReportText).toHaveBeenCalledWith('real-1', 'viewer_brief', 'markdown')
    expect(api.getRunDetail).not.toHaveBeenCalled()
    expect(api.getReplayStory).not.toHaveBeenCalled()
  })
})
