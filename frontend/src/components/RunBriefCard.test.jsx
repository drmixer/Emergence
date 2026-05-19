import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { RUN_SCHEDULE } from '../data/runSchedule'
import RunBriefCard from './RunBriefCard'

afterEach(() => {
  cleanup()
})

describe('RunBriefCard', () => {
  it('renders an upcoming run from schedule metadata', () => {
    const run = RUN_SCHEDULE.find((entry) => entry.label === 'K12')

    render(
      <MemoryRouter>
        <RunBriefCard run={run} variant="compact" heading="Next scheduled run" actionMode="calendar" />
      </MemoryRouter>
    )

    expect(screen.getByText('Next scheduled run')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'K12' })).toBeInTheDocument()
    expect(screen.getByText(/Do the new viewer\/story\/evidence changes/i)).toBeInTheDocument()
    expect(screen.getByText(/Exploratory public canary; non-claim-bearing/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Run Calendar/i })).toHaveAttribute('href', '/calendar')
  })

  it('uses completed-run actions for archived schedule entries', () => {
    const run = RUN_SCHEDULE.find((entry) => entry.label === 'K11')

    render(
      <MemoryRouter>
        <RunBriefCard run={run} variant="full" actionMode="contextual" />
      </MemoryRouter>
    )

    const actions = screen.getByRole('link', { name: /Recap/i }).closest('.run-brief-actions')
    expect(within(actions).getByRole('link', { name: /Recap/i })).toHaveAttribute(
      'href',
      '/runs/real-20260517T220144Z/replay?tab=overview'
    )
    expect(within(actions).getByRole('link', { name: /Evidence/i })).toHaveAttribute(
      'href',
      '/runs/real-20260517T220144Z'
    )
    expect(screen.getAllByText(/not finished research/i).length).toBeGreaterThan(0)
  })
})
