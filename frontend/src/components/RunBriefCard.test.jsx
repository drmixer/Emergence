import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RUN_SCHEDULE } from '../data/runSchedule'
import RunBriefCard from './RunBriefCard'

const { trackKpiEvent } = vi.hoisted(() => ({
  trackKpiEvent: vi.fn(),
}))

vi.mock('../services/kpiAnalytics', () => ({ trackKpiEvent }))

afterEach(() => {
  cleanup()
  trackKpiEvent.mockClear()
})

describe('RunBriefCard', () => {
  it('renders an upcoming run from schedule metadata', () => {
    const run = RUN_SCHEDULE.find((entry) => entry.label === 'K13')

    render(
      <MemoryRouter>
        <RunBriefCard run={run} variant="compact" heading="Next scheduled run" actionMode="calendar" />
      </MemoryRouter>
    )

    expect(screen.getByText('Next scheduled run')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'K13' })).toBeInTheDocument()
    expect(screen.getByText(/proposal discussion, voting, and passed laws/i)).toBeInTheDocument()
    expect(screen.getByText(/Exploratory public canary; non-claim-bearing/i)).toBeInTheDocument()
    expect(screen.getByText(/How to follow this run/i)).toBeInTheDocument()
    expect(screen.getByText(/Before launch/i)).toBeInTheDocument()
    expect(screen.getByText(/During live run/i)).toBeInTheDocument()
    expect(screen.getByText(/After closeout/i)).toBeInTheDocument()
    expect(screen.getByText(/Use Run Console for live operations state/i)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Run Console/i }).some((link) => link.getAttribute('href') === '/dashboard')).toBe(true)
    expect(screen.getAllByRole('link', { name: /Run Calendar/i }).some((link) => link.getAttribute('href') === '/calendar')).toBe(true)
  })

  it('uses completed-run actions for archived schedule entries', () => {
    const run = RUN_SCHEDULE.find((entry) => entry.label === 'K11')

    const { container } = render(
      <MemoryRouter>
        <RunBriefCard run={run} variant="full" actionMode="contextual" />
      </MemoryRouter>
    )

    const actions = container.querySelector('.run-brief-actions')
    expect(within(actions).getByRole('link', { name: /Recap/i })).toHaveAttribute(
      'href',
      '/runs/real-20260517T220144Z/replay?tab=overview'
    )
    expect(within(actions).getByRole('link', { name: /Evidence/i })).toHaveAttribute(
      'href',
      '/runs/real-20260517T220144Z'
    )
    expect(screen.getByText(/Start with recap/i)).toBeInTheDocument()
    expect(within(actions).getByRole('link', { name: /Story Report/i })).toHaveAttribute(
      'href',
      '/runs/real-20260517T220144Z/reports/approachable_report?format=markdown'
    )
    expect(screen.getByText(/Read the story report/i)).toBeInTheDocument()
    expect(screen.getAllByText(/not finished research/i).length).toBeGreaterThan(0)
  })

  it('tracks run-path clicks from schedule cards', () => {
    const run = RUN_SCHEDULE.find((entry) => entry.label === 'K13')

    render(
      <MemoryRouter>
        <RunBriefCard run={run} variant="compact" heading="Next scheduled run" actionMode="calendar" analyticsSurface="dashboard_idle" />
      </MemoryRouter>
    )

    fireEvent.click(screen.getAllByRole('link', { name: /Run Calendar/i })[0])

    expect(trackKpiEvent).toHaveBeenCalledWith('run_path_click', expect.objectContaining({
      runId: 'k13-governance-readability-canary',
      surface: 'dashboard_idle',
      target: 'viewer_path:Before launch',
    }))
  })
})
