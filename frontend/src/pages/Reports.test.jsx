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

function archivedK13() {
  return {
    run_id: 'real-20260522T014909Z',
    summary: {
      run_id: 'real-20260522T014909Z',
      condition_name: 'real_governance_readability_canary_k13',
      run_class: 'special_exploratory',
      run_started_at: '2026-05-22T01:49:10Z',
      run_ended_at: '2026-05-22T09:20:38Z',
      duration_hours: 7.52,
      status_label: 'observational',
      metrics: {
        total_events: 5424,
        laws_passed: 1,
        deaths: 0,
      },
    },
    run_metadata: {
      run_id: 'real-20260522T014909Z',
      condition_name: 'real_governance_readability_canary_k13',
      run_class: 'special_exploratory',
      started_at: '2026-05-22T01:49:10Z',
      ended_at: '2026-05-22T09:20:38Z',
    },
    artifacts: {
      approachable_report: { available: true, formats: ['markdown'] },
      run_summary: { available: true, formats: ['markdown'] },
    },
  }
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
  it('uses archived closeout state before choosing the next scheduled run card', async () => {
    api.getRunsArchive.mockResolvedValue({
      stats: {},
      items: [archivedK13()],
    })

    renderArchive()

    expect(await screen.findByRole('heading', { name: 'K14' })).toBeInTheDocument()

    const nextRunCard = screen.getByRole('heading', { name: 'K14' }).closest('article')
    expect(within(nextRunCard).getByText(/Next tentative run/i)).toBeInTheDocument()
    expect(within(nextRunCard).getByText(/Under visible scarcity/i)).toBeInTheDocument()
    expect(screen.queryByText(/NEXT SCHEDULED RUN/i)).not.toBeInTheDocument()
  })

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
    expect(within(card).getByLabelText(/Latest run path/i)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Brief: News recap/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/reports/viewer_brief?format=markdown',
    )
    expect(within(card).getByRole('link', { name: /Highlights: Digest/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/highlights',
    )
    expect(within(card).getByRole('link', { name: /Watch: Largest spike/i })).toHaveAttribute(
      'href',
      '/watch?run=real-20260519T063000Z&focus=largest',
    )
    expect(within(card).getByRole('link', { name: /Replay: Key moments/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z/replay?mode=story60',
    )
    expect(within(card).getByRole('link', { name: /Evidence: Source trail/i })).toHaveAttribute(
      'href',
      '/runs/real-20260519T063000Z',
    )
    expect(within(card).queryAllByRole('link', { name: /Emergence Brief/i })).toHaveLength(0)
    expect(within(card).getByText(/Reports: 3 available/i)).toBeInTheDocument()
  })
})
