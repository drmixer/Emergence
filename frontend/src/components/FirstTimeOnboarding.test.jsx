import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FirstTimeOnboarding, { shouldAutoOpenOnboarding } from './FirstTimeOnboarding'

vi.mock('../services/kpiAnalytics', () => ({
    trackKpiEvent: vi.fn(),
    trackKpiEventOnce: vi.fn(),
}))

beforeEach(() => {
    const store = new Map()
    vi.stubGlobal('localStorage', {
        getItem: vi.fn((key) => store.get(key) || null),
        setItem: vi.fn((key, value) => store.set(key, String(value))),
    })
})

afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
})

describe('FirstTimeOnboarding', () => {
    it('auto-opens only on main entry surfaces', () => {
        expect(shouldAutoOpenOnboarding('/')).toBe(true)
        expect(shouldAutoOpenOnboarding('/dashboard')).toBe(true)
        expect(shouldAutoOpenOnboarding('/calendar')).toBe(false)
        expect(shouldAutoOpenOnboarding('/archive')).toBe(false)
        expect(shouldAutoOpenOnboarding('/runs/real-20260517t220144z/replay')).toBe(false)
        expect(shouldAutoOpenOnboarding('/runs/real-20260517t220144z/reports/story')).toBe(false)
        expect(shouldAutoOpenOnboarding('/glossary')).toBe(false)
    })

    it('starts viewers with Archive and separates replay from evidence', () => {
        render(
            <MemoryRouter initialEntries={['/dashboard']}>
                <FirstTimeOnboarding />
            </MemoryRouter>
        )

        expect(screen.getByRole('dialog', { name: /How to read Emergence/i })).toBeInTheDocument()
        expect(screen.getByText(/Archive:/i)).toBeInTheDocument()
        expect(screen.getByText(/Watch Map and Replay:/i)).toBeInTheDocument()
        expect(screen.getByText(/Evidence:/i)).toBeInTheDocument()
        expect(screen.getByText(/Calendar and Field Notes:/i)).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /Start with Archive/i })).toBeInTheDocument()
        expect(screen.queryByText(/Current Run:/i)).not.toBeInTheDocument()
    })
})
