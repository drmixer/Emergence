import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
    api: {
        getRunDetail: vi.fn(),
        getReplayStory: vi.fn(),
    },
}))

vi.mock('../services/api', () => ({ api }))

import NoActiveRunNotice from './NoActiveRunNotice'

beforeEach(() => {
    vi.clearAllMocks()
    api.getRunDetail.mockResolvedValue({
        activity: {
            total_events: 11204,
            deaths: 3,
            became_dormant: 8,
            laws_passed: 2,
            proposal_actions: 11,
            aid_requests: 6,
            trade_actions: 4,
            aid_refusals: 2,
            public_order_events: 5,
            conflict_events: 2,
        },
    })
    api.getReplayStory.mockResolvedValue({
        items: [
            {
                event_id: 10,
                chapter: 'Turning Point',
                title: 'Permanent Death',
            },
            {
                event_id: 11,
                chapter: 'Outcome',
                title: 'Proposal Passed',
            },
        ],
    })
})

afterEach(() => {
    cleanup()
})

describe('NoActiveRunNotice', () => {
    it('turns an idle dashboard into a latest-run handoff', async () => {
        render(
            <MemoryRouter>
                <NoActiveRunNotice lastCompletedRunId="real-20260517T220144Z" />
            </MemoryRouter>
        )

        expect(screen.getByText(/Live run ended/i)).toBeInTheDocument()
        expect(screen.getByText(/Latest completed run: real-20260517T220144Z/i)).toBeInTheDocument()
        expect(await screen.findByText(/11,204 logged events/i)).toBeInTheDocument()

        const snapshot = screen.getByLabelText(/Latest completed run snapshot/i)
        expect(within(snapshot).getByText(/Survival/i)).toBeInTheDocument()
        expect(within(snapshot).getByText(/3 deaths/i)).toBeInTheDocument()
        expect(within(snapshot).getByText(/2 laws/i)).toBeInTheDocument()
        expect(within(snapshot).getByText(/6 aid asks/i)).toBeInTheDocument()
        expect(within(snapshot).getByText(/5 signals/i)).toBeInTheDocument()

        const moments = screen.getByLabelText(/Latest completed run moments/i)
        expect(within(moments).getByText(/Permanent Death/i)).toBeInTheDocument()
        expect(within(moments).getByText(/Proposal Passed/i)).toBeInTheDocument()

        expect(screen.getByRole('link', { name: /Run Recap/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z/replay?tab=overview'
        )
        expect(screen.getByRole('link', { name: /^Replay$/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z/replay?mode=story60'
        )
        expect(screen.getByRole('link', { name: /Evidence/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z'
        )
        expect(screen.getByText(/Next scheduled run/i)).toBeInTheDocument()
        expect(screen.getByText(/K12: Do the new viewer\/story\/evidence changes/i)).toBeInTheDocument()
        expect(screen.getByRole('link', { name: /Run Calendar/i })).toHaveAttribute('href', '/calendar')
    })
})
