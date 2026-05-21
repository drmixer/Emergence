import { Suspense } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, trackKpiEvent, trackKpiEventOnce } = vi.hoisted(() => ({
  api: {
    getRunsArchive: vi.fn(),
    getRunReportDownloadUrl: vi.fn(),
    getRunReportViewUrl: vi.fn(),
  },
  trackKpiEvent: vi.fn(),
  trackKpiEventOnce: vi.fn(),
}))

vi.mock('../services/api', () => ({ api }))
vi.mock('../services/kpiAnalytics', () => ({ trackKpiEvent, trackKpiEventOnce }))

import Reports from './Reports'

function renderArchive() {
  return render(
    <MemoryRouter initialEntries={['/archive']}>
      <Routes>
        <Route
          path="/archive"
          element={(
            <Suspense fallback={<div>loading...</div>}>
              <Reports />
            </Suspense>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRunsArchive.mockResolvedValue({
    stats: {
      completed_runs: 1,
      total_events: 15538,
      llm_calls: 2434,
      deaths: 4,
      estimated_cost_usd: 8.42,
    },
    items: [
      {
        run_id: 'real-20260519T063000Z',
        summary: {
          run_ended_at: '2026-05-20T04:32:21.000Z',
          duration_hours: 22,
          condition_name: 'viewer_canary_v1',
          season_number: 0,
          replicate_count: 1,
          generated_at_utc: '2026-05-21T00:00:00.000Z',
          viewer_brief_headline: 'Deaths, Dormancy, and Four New Laws Closed the K-Series Test',
          viewer_brief_lead: 'Four agents died, several dormancy events accumulated, and the run still produced four laws before closeout.',
          metrics: {
            total_events: 15538,
            llm_calls: 2434,
            deaths: 4,
            estimated_cost_usd: 8.42,
          },
        },
        run_metadata: {
          run_mode: 'real',
          run_class: 'special_exploratory',
          condition_name: 'viewer_canary_v1',
        },
        artifacts: {
          viewer_brief: { available: true, formats: ['markdown'] },
          approachable_report: { available: true, formats: ['markdown'] },
          technical_report: { available: true, formats: ['markdown'] },
        },
      },
    ],
  })
  api.getRunReportDownloadUrl.mockImplementation((runId, artifactType, format) => `/download/${runId}/${artifactType}.${format}`)
  api.getRunReportViewUrl.mockImplementation((runId, artifactType, format) => `/view/${runId}/${artifactType}.${format}`)
})

afterEach(() => {
  cleanup()
})

describe('Reports archive', () => {
  it('promotes the latest viewer brief while keeping recap and evidence actions adjacent', async () => {
    renderArchive()

    const card = (await screen.findByText('real-20260519T063000Z')).closest('.archive-run-card')

    expect(within(card).getByRole('link', { name: /Read The Brief/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/reports/viewer_brief?format=markdown',
    )
    expect(within(card).getByRole('link', { name: /Deaths, Dormancy, and Four New Laws/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/reports/viewer_brief?format=markdown',
    )
    expect(within(card).getByText(/Four agents died, several dormancy events accumulated/i)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /^Replay$/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=story60',
    )
    expect(within(card).getByRole('link', { name: /Latest Run Details/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z',
    )
    expect(within(card).queryAllByRole('link', { name: /Emergence Brief/i })).toHaveLength(0)
    expect(within(card).getByText(/Reports: 3 available/i)).toBeInTheDocument()
  })
})
