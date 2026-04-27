import { useEffect, useRef } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { NotificationBell, SubscriptionProvider, useSubscriptions } from './Subscriptions'

const WATCHED_AGENT = {
    id: 6,
    agent_number: 6,
    display_name: 'Sigma-06',
    personality: 'Efficiency',
}

function SeededNotifications({ notifications = [] }) {
    const { subscriptions, subscribe, addNotification } = useSubscriptions()
    const seeded = useRef(false)

    useEffect(() => {
        subscribe(WATCHED_AGENT)
    }, [subscribe])

    useEffect(() => {
        if (seeded.current || subscriptions.length === 0) return
        seeded.current = true
        for (const notification of notifications) {
            addNotification({ agent_number: WATCHED_AGENT.agent_number, ...notification })
        }
    }, [addNotification, notifications, subscriptions.length])

    return <NotificationBell />
}

function renderBell(notifications) {
    return render(
        <SubscriptionProvider>
            <SeededNotifications notifications={notifications} />
        </SubscriptionProvider>
    )
}

function resetStoredSubscriptions() {
    localStorage.removeItem('emergence_subscriptions')
}

beforeEach(() => {
    const store = new Map()
    Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: {
            getItem: (key) => store.get(key) || null,
            setItem: (key, value) => store.set(key, String(value)),
            removeItem: (key) => store.delete(key),
        },
    })
    resetStoredSubscriptions()
})

afterEach(() => {
    cleanup()
    resetStoredSubscriptions()
})

describe('NotificationBell', () => {
    it('explains notification scope when there are no watchlist alerts', () => {
        renderBell([])

        fireEvent.click(screen.getByRole('button', { name: /open watchlist notifications/i }))

        expect(screen.getByRole('heading', { name: /Watchlist Alerts/i })).toBeInTheDocument()
        expect(screen.getByText(/In-app updates for followed agents/i)).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /Messages/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /Governance/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /Status/i })).toBeInTheDocument()
        expect(screen.getByText(/not browser push/i)).toBeInTheDocument()
    })

    it('filters watchlist alerts by operational category', async () => {
        renderBell([
            {
                id: 101,
                type: 'message',
                title: 'Sigma-06 posted',
                text: 'Forum coordination message',
            },
            {
                id: 102,
                type: 'vote',
                title: 'Sigma-06 voted',
                text: 'Voted yes on proposal',
            },
        ])

        await waitFor(() => {
            expect(screen.getByText('2')).toBeInTheDocument()
        })

        fireEvent.click(screen.getByRole('button', { name: /open watchlist notifications/i }))
        expect(screen.getByText(/Sigma-06 posted/i)).toBeInTheDocument()
        expect(screen.getByText(/Sigma-06 voted/i)).toBeInTheDocument()

        fireEvent.click(screen.getByRole('button', { name: /Governance/i }))
        expect(screen.queryByText(/Sigma-06 posted/i)).not.toBeInTheDocument()
        expect(screen.getByText(/Sigma-06 voted/i)).toBeInTheDocument()
    })
})
