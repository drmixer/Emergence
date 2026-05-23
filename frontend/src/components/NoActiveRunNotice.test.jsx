import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
    api: {
        getRunDetail: vi.fn(),
        getReplayStory: vi.fn(),
        getRunReports: vi.fn(),
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
    api.getRunReports.mockResolvedValue({
        items: [
            {
                artifact_type: 'viewer_brief',
                artifact_format: 'markdown',
                status: 'completed',
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

        expect(screen.getByRole('link', { name: /Latest Emergence Brief/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z/reports/viewer_brief?format=markdown'
        )
        expect(screen.getByRole('link', { name: /Read The Brief/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z/reports/viewer_brief?format=markdown'
        )
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
        expect(screen.getByRole('link', { name: /Run Calendar/i })).toHaveAttribute('href', '/calendar')
    })

    it('can show a plain no-active-run state without completed-run stats', () => {
        render(
            <MemoryRouter>
                <NoActiveRunNotice
                    title="No active run"
                    message="Check the run calendar for upcoming runs."
                    lastCompletedRunId="real-20260517T220144Z"
                    showCompletedRunHandoff={false}
                />
            </MemoryRouter>
        )

        expect(screen.getByText(/No active run/i)).toBeInTheDocument()
        expect(screen.getByText(/Check the run calendar/i)).toBeInTheDocument()
        expect(screen.queryByText(/Latest completed run:/i)).not.toBeInTheDocument()
        expect(screen.queryByLabelText(/Latest completed run snapshot/i)).not.toBeInTheDocument()
        expect(screen.getByRole('link', { name: /Run Calendar/i })).toHaveAttribute('href', '/calendar')
        expect(api.getRunDetail).not.toHaveBeenCalled()
        expect(api.getReplayStory).not.toHaveBeenCalled()
        expect(api.getRunReports).not.toHaveBeenCalled()
    })

    it('can render an ops handoff without recap details', () => {
        render(
            <MemoryRouter>
                <NoActiveRunNotice
                    title="Console idle"
                    message="Open the latest completed run in Watch, Replay, Evidence, or the full Archive."
                    lastCompletedRunId="real-20260517T220144Z"
                    handoffMode="ops"
                />
            </MemoryRouter>
        )

        expect(screen.getByText(/Console idle/i)).toBeInTheDocument()
        expect(screen.getByText(/Latest completed run: real-20260517T220144Z/i)).toBeInTheDocument()
        expect(screen.queryByText(/11,204 logged events/i)).not.toBeInTheDocument()
        expect(screen.queryByLabelText(/Latest completed run snapshot/i)).not.toBeInTheDocument()
        expect(screen.queryByLabelText(/Latest completed run moments/i)).not.toBeInTheDocument()
        expect(screen.queryByRole('link', { name: /Latest Emergence Brief/i })).not.toBeInTheDocument()
        expect(screen.getByRole('link', { name: /^Watch$/i })).toHaveAttribute(
            'href',
            '/watch?run=real-20260517T220144Z'
        )
        expect(screen.getByRole('link', { name: /^Replay$/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z/replay?mode=story60'
        )
        expect(screen.getByRole('link', { name: /^Evidence$/i })).toHaveAttribute(
            'href',
            '/runs/real-20260517T220144Z'
        )
        expect(screen.getByRole('link', { name: /^Archive$/i })).toHaveAttribute('href', '/archive')
        expect(screen.getByRole('link', { name: /Run Calendar/i })).toHaveAttribute('href', '/calendar')
        expect(api.getRunDetail).not.toHaveBeenCalled()
        expect(api.getReplayStory).not.toHaveBeenCalled()
        expect(api.getRunReports).not.toHaveBeenCalled()
    })
})
