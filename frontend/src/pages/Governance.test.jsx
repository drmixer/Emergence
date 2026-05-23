import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: {
    fetch: vi.fn(),
    getProposalDuplicateWaves: vi.fn(),
  },
}))

vi.mock('../services/api', () => ({ api }))

import Governance from './Governance'

function renderGovernance(initialEntries = ['/governance']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Governance />
    </MemoryRouter>,
  )
}

const activeProposal = {
  id: 101,
  status: 'active',
  proposal_type: 'law',
  title: 'Reserve share vote',
  description: 'Keep reserve access visible.',
  votes_for: 4,
  votes_against: 1,
  votes_abstain: 0,
  voting_closes_at: '2099-01-01T00:00:00Z',
  author: { agent_number: 7, codename: 'Marble', tier: 2 },
}

const activeLaw = {
  id: 5,
  active: true,
  title: 'Reserve Law',
  description: 'Maintain shared reserves.',
  passed_at: '2026-05-22T04:00:00Z',
  author: { agent_number: 7, codename: 'Marble', tier: 2 },
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetch.mockImplementation((endpoint) => {
    if (endpoint === '/api/analytics/overview') {
      return Promise.resolve({
        scope: {
          simulation_active: true,
          simulation_paused: false,
          active_run_id: 'real-live-run',
        },
      })
    }
    if (endpoint === '/api/proposals?limit=200') {
      return Promise.resolve([activeProposal])
    }
    if (endpoint === '/api/laws?limit=500') {
      return Promise.resolve([activeLaw])
    }
    return Promise.resolve([])
  })
  api.getProposalDuplicateWaves.mockResolvedValue({
    summary: { wave_count: 1, proposal_wave_count: 1, clustered_item_count: 2 },
    waves: [
      {
        id: 'wave-1',
        source: 'proposal',
        count: 2,
        actor_count: 2,
        representative: { id: 101, title: 'Reserve share vote' },
      },
    ],
  })
})

afterEach(() => {
  cleanup()
})

describe('Governance', () => {
  it('hides the live governance workspace when no run is active', async () => {
    api.fetch.mockImplementation((endpoint) => {
      if (endpoint === '/api/analytics/overview') {
        return Promise.resolve({
          scope: {
            simulation_active: false,
            simulation_paused: true,
            last_completed_run_id: 'real-20260522T014909Z',
          },
        })
      }
      if (endpoint === '/api/proposals?limit=200') {
        return Promise.resolve([activeProposal])
      }
      if (endpoint === '/api/laws?limit=500') {
        return Promise.resolve([activeLaw])
      }
      return Promise.resolve([])
    })

    renderGovernance()

    expect(await screen.findByText(/No live governance workspace/i)).toBeInTheDocument()
    expect(screen.getByText(/Latest completed run: real-20260522T014909Z/i)).toBeInTheDocument()
    expect(screen.queryByText(/^Active Proposals$/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Active Laws$/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /Proposals/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Repeated Proposal Waves/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Reserve share vote/i)).not.toBeInTheDocument()
  })

  it('keeps the live proposal and law workspace visible during an active run', async () => {
    renderGovernance()

    expect(await screen.findByText(/^Active Proposals$/i)).toBeInTheDocument()
    expect(screen.getByText(/^Active Laws$/i)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Proposals\s*1/i })).toBeInTheDocument()
    expect(screen.getByText(/Repeated Proposal Waves/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Reserve share vote/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/No live governance workspace/i)).not.toBeInTheDocument()
  })
})
